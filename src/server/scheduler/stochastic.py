"""Module containing scheduling policy implementations which use randomness."""

import random
from typing import List, Self

from common.job import Spec
from common.scheduling_decision import Assigned, Impossible, SchedulingDecision
from common.target import Target

from server.scheduler import Scheduler


class Uniform(Scheduler):
    """
    This scheduling policy assigns jobs using a uniform random distribution per scheduling request.
    (Note that this may result in a non-uniform distribution across all targets depending on the available ones.)
    """

    def request_schedule(
        self, job_spec: Spec, available_targets: List[str]
    ) -> SchedulingDecision:
        """
        Apply uniform random scheduling policy.

        Parameters
        ----------
        job_spec : Spec
            The job specification (Unused)
        available_targets : List[str]
            List of identifiers of targets available to the client for job submission

        Returns
        -------
        SchedulingDecision
            The scheduling decision based on the policy (assigned to random target or impossible)
        """
        random.shuffle(available_targets)
        for target_id in available_targets:
            if target_id in self._targets:
                return Assigned(wait_seconds=0, target_id=target_id)
        return Impossible()


class WeightedByCores(Scheduler):
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
        self.__weights = {t.id: t._nodes * t._cores_per_node for t in targets}

    def request_schedule(
        self, job_spec: Spec, available_targets: List[str]
    ) -> SchedulingDecision:
        """
        Apply random scheduling policy where the weight of each target is determined by its number of cores.

        Parameters
        ----------
        job_spec : Spec
            The job specification (Unused)
        available_targets : List[str]
            List of identifiers of targets available to the client for job submission

        Returns
        -------
        SchedulingDecision
            The scheduling decision based on the policy (assigned to random target weighted by cores or impossible)
        """
        available_targets = [t for t in available_targets if t in self._targets]
        if len(available_targets) == 0:
            return Impossible()
        weights = [self.__weights[t] for t in available_targets]
        selected = random.choices(available_targets, weights, k=1)[0]
        return Assigned(wait_seconds=0, target_id=selected)
