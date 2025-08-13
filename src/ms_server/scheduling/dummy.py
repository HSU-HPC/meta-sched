"""Module containing a dummy scheduling policy for testing and development."""

from typing import List

from ms_common.schemas import Assigned, Impossible, SchedulingDecisionType

from ms_server.model import Job, TargetsStatus
from ms_server.scheduling import GreedyPolicy


class Dummy(GreedyPolicy):
    """Dummy scheduling policy which always assigns the same target."""

    async def schedule_job(
        self: "Dummy",
        job: Job,
        decided_jobs: List[Job],
        targets_status: TargetsStatus,
    ) -> None:
        """
        Schedule a job by always assigning it to the first available target.

        Parameters
        ----------
        job : Job
            The job to schedule
        decided_jobs : List[Job]
            The jobs for which are scheduling decision has already been made
        targets_status : TargetsStatus
            A mapping from target IDs to the corresponding status if available
        """
        decision: SchedulingDecisionType = Impossible()
        for target in targets_status:
            if target.id in job.available_targets:
                decision = Assigned(target_id=target.id)
                break
        await self.on_schedule_job(job.key, decision)
