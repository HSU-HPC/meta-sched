"""
Module containing stateful scheduling policies which update and use information across scheduling requests.
"""

from typing import List, Self

from ms_common.schemas import Assigned, Impossible, Target

from ms_server.model import Job
from ms_server.scheduling import GreedyPolicy, ScheduleJobCallback


class LeastUsed(GreedyPolicy):
    """
    This scheduling policy assigns jobs uniformly by assigning the least used target next.
    (Note that this may result in a non-uniform distribution across all targets depending on the available ones.)
    """

    def __init__(
        self: Self, targets: List[Target], on_schedule_job: ScheduleJobCallback
    ) -> None:
        """
        Create a new instance of the scheduling policy

        Parameters
        ----------
        targets : List[Target]
            The list of targets for which to count assignments
        on_schedule_job : ScheduleJobCallback
            Callback to apply scheduling decision to a job
        """
        super().__init__(targets, on_schedule_job)
        self.__job_count = {t.id: 0 for t in targets}

    async def schedule_job(self: Self, job: Job) -> None:
        """
        Schedule a job by assigning it to the least used target.

        Parameters
        ----------
        job : Job
            The job to be scheduled
        """
        available_targets = sorted(list(job.available_targets))
        target_ids = [t for t in available_targets if t in self.__job_count]
        if len(target_ids) == 0:
            await self.on_schedule_job(job.key, Impossible())
            return
        selected = 0
        for i in range(len(target_ids)):
            if self.__job_count[target_ids[selected]] > self.__job_count[target_ids[i]]:
                selected = i
        self.__job_count[target_ids[selected]] += 1
        target = self._targets[target_ids[selected]]
        decision = Assigned(target_id=target.id)
        await self.on_schedule_job(job.key, decision)
