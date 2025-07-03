"""Module containing a dummy scheduling policy for testing and development."""

from typing import List, Self

from ms_common.schemas import (Assigned, Impossible, SchedulingDecisionType,
                               Target)

from ms_server.model import Job
from ms_server.scheduling import GreedyPolicy, ScheduleJobCallback


class Dummy(GreedyPolicy):
    """Dummy scheduling policy which always assigns the same target."""

    def __init__(
        self: Self, targets: List[Target], on_schedule_job: ScheduleJobCallback
    ) -> None:
        """
        Create a new instance of the scheduling policy

        Parameters
        ----------
        targets : List[Target]
            The list of targets (only the first is used)
        on_schedule_job : ScheduleJobCallback
            Callback to apply scheduling decision to a job
        """
        super().__init__(
            targets[:1], on_schedule_job
        )  # Always only the first target (Good for debugging)

    async def schedule_job(self: Self, job: Job) -> None:
        """
        Schedule a job by assigning it to the only available target.

        Parameters
        ----------
        job : Job
            The job to be scheduled
        """
        decision: SchedulingDecisionType = Impossible()
        for target_id in job.available_targets:
            if target_id in self._targets:
                target = self._targets[target_id]
                decision = Assigned(wait_seconds=0, target_id=target.id)
                break
        await self.on_schedule_job(job.key, decision)
