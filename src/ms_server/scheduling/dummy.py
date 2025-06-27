"""Module containing a dummy scheduling policy for testing and development."""

from typing import List, Self

from ms_common.scheduling_decision import (Assigned, Impossible,
                                           SchedulingDecisionType)
from ms_common.target import Target

from ms_server.job import Job
from ms_server.scheduling import GreedyPolicy


class Dummy(GreedyPolicy):
    """Dummy scheduling policy which always assigns the same target."""

    def __init__(self: Self, targets: List[Target] = []) -> None:
        """
        Create a new instance of the scheduling policy

        Parameters
        ----------
        targets : List[Target]
            The list of targets (only the first is used)
        """
        super().__init__(
            targets[:1]
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
                decision = Assigned(wait_seconds=0, target=target)
                break
        await job.make_scheduling_decision(decision)
