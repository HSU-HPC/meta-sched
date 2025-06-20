"""Module containing the base class for implementing scheduling policies."""

from typing import List, Self

from common.job import Spec
from common.scheduler_interface import SchedulerInterface
from common.scheduling_decision import SchedulingDecision
from common.target import Target


class Scheduler(SchedulerInterface):
    """
    Base class for scheduling policies.
    """

    def __init__(self: Self, targets: List[Target]):
        """
        Create a new instance of the scheduling policy

        Parameters
        ----------
        targets : List[Target]
            The list of targets which jobs may be assigned to
        """
        if self.__class__ == Scheduler:
            raise NotImplementedError()
        self._targets = {t.id: t for t in targets}

    @property
    def targets(self: Self) -> List[Target]:
        """
        Get all targets which jobs may be assigned to.

        Returns
        -------
        List[Target]
            The list of all targets which jobs may be assigned to
        """
        return list(self._targets.values())

    def create_array_id(self: Self) -> str:
        """
        Create a new unique identifier for a new job array.

        Returns
        -------
        str
            A new unique identifier for a job array

        Raises
        ------
        NotImplementedError
            May be implemented in concrete scheduling policy
        """
        raise NotImplementedError()

    def request_schedule(
        self: Self, job_spec: Spec, available_targets: List[str]
    ) -> SchedulingDecision:
        """
        Apply scheduling policy.

        Parameters
        ----------
        job_spec : Spec
            The job specification
        available_targets : List[str]
            List of identifiers of targets available to the client for job submission

        Returns
        -------
        SchedulingDecision
            The scheduling decision based on the policy

        Raises
        ------
        NotImplementedError
            Must be implemented in concrete scheduling policy
        """
        raise NotImplementedError()
