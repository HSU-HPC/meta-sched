"""Module containing scheduling policy implementations which use randomness."""

import random
from typing import List, Self

from ms_common.scheduling_decision import (Assigned, Impossible,
                                           SchedulingDecisionType)
from ms_common.target import Target

from ms_server.job import Job
from ms_server.scheduling import GreedyPolicy


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
                decision = Assigned(wait_seconds=0, target=target)
                break
        await job.make_scheduling_decision(decision)


class WeightedByCores(GreedyPolicy):
    """
    This scheduling policy assigns jobs randomly per scheduling request proportional to the core count of each target.
    (Note that this may result in disproportionate distribution across all targets depending on the available ones.)
    """

    def __init__(self: Self, targets: List[Target]) -> None:
        """
        Create a new instance of the scheduling policy

        Parameters
        ----------
        targets : List[Target]
            The list of targets used to determine the weighting by core count when applying the scheduling policy
        """
        super().__init__(targets)
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
            decision = Assigned(wait_seconds=0, target=target)
        await job.make_scheduling_decision(decision)
