"""Module containing scheduling policy implementations which use randomness."""

import random
from typing import List, Self

from ms_common.schemas import Assigned

from ms_server.model import Job, TargetsStatus
from ms_server.scheduling import GreedyPolicy


class Uniform(GreedyPolicy):
    """
    This scheduling policy assigns jobs using a uniform random distribution per scheduling request.
    (Note that this may result in a non-uniform distribution across all targets depending on the available ones.)
    """

    async def schedule_job(
        self: Self, job: Job, decided_jobs: List[Job], targets_status: TargetsStatus
    ) -> None:
        """
        Schedule a job by assigning it to a random target from the available ones.

        Parameters
        ----------
        job : Job
            The job to be scheduled
        decided_jobs : List[Job]
            The jobs for which are scheduling decision has already been made
        targets_status : TargetsStatus
            A mapping from target IDs to the corresponding status if available
        """
        available_targets = list(job.available_targets)  # Make an orderable copy
        random.shuffle(available_targets)
        decision = Assigned(target_id=available_targets[0])
        await self.on_schedule_job(job.key, decision)


class WeightedByCores(GreedyPolicy):
    """
    This scheduling policy assigns jobs randomly per scheduling request proportional to the core count of each target.
    (Note that this may result in disproportionate distribution across all targets depending on the available ones.)
    """

    async def schedule_job(
        self: Self, job: Job, decided_jobs: List[Job], targets_status: TargetsStatus
    ) -> None:
        """
        Schedule a job by assigning it to a target using a weighted random selection based on core count.

        Parameters
        ----------
        job : Job
            The job to be scheduled
        decided_jobs : List[Job]
            The jobs for which are scheduling decision has already been made
        targets_status : TargetsStatus
            A mapping from target IDs to the corresponding status if available
        """
        targets_weights = {t.id: t.nodes * t.cores_per_node for t in targets_status}
        weights = [targets_weights[t] for t in job.available_targets]
        target_id = random.choices(job.available_targets, weights, k=1)[0]
        decision = Assigned(target_id=target_id)
        await self.on_schedule_job(job.key, decision)
