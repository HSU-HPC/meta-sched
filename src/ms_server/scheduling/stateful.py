"""
Module containing stateful scheduling policies which update and use information across scheduling requests.
"""

from typing import Dict, List, Self

from ms_common.schemas import Assigned

from ms_server.model import Job, TargetsStatus
from ms_server.scheduling import GreedyPolicy, ScheduleJobCallback


class LeastUsed(GreedyPolicy):
    """
    This scheduling policy assigns jobs uniformly by assigning the least used target next.
    (Note that this may result in a non-uniform distribution across all targets depending on the available ones.)
    """

    def __init__(self: Self, on_schedule_job: ScheduleJobCallback) -> None:
        """
        Create a new instance of the scheduling policy

        Parameters
        ----------
        on_schedule_job : ScheduleJobCallback
            Callback to apply scheduling decision to a job
        """
        super().__init__(on_schedule_job)
        self.__job_count: Dict[str, int] = dict()

    async def schedule_job(
        self: Self,
        job: Job,
        decided_jobs: List[Job],
        targets_status: TargetsStatus,
    ) -> None:
        """
        Schedule a job by assigning it to the least used target.

        Parameters
        ----------
        job : Job
            The job to be scheduled
        decided_jobs : List[Job]
            The jobs for which are scheduling decision has already been made
        targets_status : TargetsStatus
            A mapping from target IDs to the corresponding status if available
        """
        # Update state first
        for target in targets_status:
            if target.id not in self.__job_count:
                self.__job_count[target.id] = 0
        # Select least used available
        available_targets = sorted(list(job.available_targets))
        target_ids = available_targets
        selected_idx = 0
        for i in range(len(target_ids)):
            if (
                self.__job_count[target_ids[selected_idx]]
                > self.__job_count[target_ids[i]]
            ):
                selected_idx = i
        selected_id = target_ids[selected_idx]
        decision = Assigned(target_id=selected_id)
        await self.on_schedule_job(job.key, decision)
