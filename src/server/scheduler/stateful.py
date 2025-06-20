"""
Module containing stateful scheduling policies which update and use information across scheduling requests.
"""

from typing import List, Self

from common.job import Spec
from common.scheduling_decision import Assigned, Impossible, SchedulingDecision
from common.target import Target

from server.scheduler import Scheduler


class LeastUsed(Scheduler):
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

    def request_schedule(
        self: Self, job_spec: Spec, available_targets: List[str]
    ) -> SchedulingDecision:
        """
        Apply scheduling policy, assigning the job to the least used available target.

        Parameters
        ----------
        job_spec : Spec
            The job specification (Unused)
        available_targets : List[str]
            List of identifiers of targets available to the client for job submission

        Returns
        -------
        SchedulingDecision
            The scheduling decision based on the policy (assigned to least used target or impossible)
        """
        available_targets.sort()
        target_ids = [t for t in available_targets if t in self.__job_count]
        if len(target_ids) == 0:
            return Impossible()
        selected = 0
        for i in range(len(target_ids)):
            if self.__job_count[target_ids[selected]] > self.__job_count[target_ids[i]]:
                selected = i
        self.__job_count[target_ids[selected]] += 1
        return Assigned(wait_seconds=0, target_id=target_ids[selected])
