"""
Module containing stateful scheduling policies which update and use information across scheduling requests.
"""

from typing import List, Self

from ms_common.scheduling_decision import Assigned, Impossible
from ms_common.target import Target

from ms_server.job import Job
from ms_server.scheduling import GreedyPolicy


class LeastUsed(GreedyPolicy):
    """
    This scheduling policy assigns jobs uniformly by assigning the least used target next.
    (Note that this may result in a non-uniform distribution across all targets depending on the available ones.)
    """

    def __init__(self: Self, targets: List[Target]) -> None:
        """
        Create a new instance of the scheduling policy

        Parameters
        ----------
        targets : List[Target]
            The list of targets for which to count assignments
        """
        super().__init__(targets)
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
            await job.make_scheduling_decision(Impossible())
            return
        selected = 0
        for i in range(len(target_ids)):
            if self.__job_count[target_ids[selected]] > self.__job_count[target_ids[i]]:
                selected = i
        self.__job_count[target_ids[selected]] += 1
        target = self._targets[target_ids[selected]]
        decision = Assigned(wait_seconds=0, target=target)
        await job.make_scheduling_decision(decision)
