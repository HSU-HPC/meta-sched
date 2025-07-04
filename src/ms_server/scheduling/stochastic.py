"""Module containing scheduling policy implementations which use randomness."""

import random
from typing import List, Self

from ms_common.schemas import (Assigned, Impossible, SchedulingDecisionType,
                               Target)

from ms_server.model import Job
from ms_server.scheduling import GreedyPolicy, ScheduleJobCallback


class Uniform(GreedyPolicy):
    """
    This scheduling policy assigns jobs using a uniform random distribution per scheduling request.
    (Note that this may result in a non-uniform distribution across all targets depending on the available ones.)
    """

    async def schedule_job(self: Self, job: Job) -> None:
        """
        Schedule a job by assigning it to a random target from the available ones.

        Parameters
        ----------
        job : Job
            The job to be scheduled
        """
        available_targets = list(job.available_targets)
        random.shuffle(available_targets)
        decision: SchedulingDecisionType = Impossible()
        for target_id in available_targets:
            if target_id in self._targets:
                target = self._targets[target_id]
                decision = Assigned(target_id=target.id)
                break
        await self.on_schedule_job(job.key, decision)


class WeightedByCores(GreedyPolicy):
    """
    This scheduling policy assigns jobs randomly per scheduling request proportional to the core count of each target.
    (Note that this may result in disproportionate distribution across all targets depending on the available ones.)
    """

    def __init__(
        self: Self, targets: List[Target], on_schedule_job: ScheduleJobCallback
    ) -> None:
        """
        Create a new instance of the scheduling policy

        Parameters
        ----------
        targets : List[Target]
            The list of targets used to determine the weighting by core count when applying the scheduling policy
        on_schedule_job : ScheduleJobCallback
            Callback to apply scheduling decision to a job
        """
        super().__init__(targets, on_schedule_job)
        self.__weights = {t.id: t.nodes * t.cores_per_node for t in targets}

    async def schedule_job(self: Self, job: Job) -> None:
        """
        Schedule a job by assigning it to a target using a weighted random selection based on core count.

        Parameters
        ----------
        job : Job
            The job to be scheduled
        """
        decision: SchedulingDecisionType = Impossible()
        available_targets = [t for t in job.available_targets if t in self._targets]
        if len(available_targets) > 0:
            weights = [self.__weights[t] for t in available_targets]
            target_id = random.choices(available_targets, weights, k=1)[0]
            target = self._targets[target_id]
            decision = Assigned(target_id=target.id)
        await self.on_schedule_job(job.key, decision)
