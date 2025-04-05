"""Module containing the interface for the scheduling policy."""

import abc
from typing import List, Self

from meta_sched.common.job import Spec
from meta_sched.common.scheduling_decision import SchedulingDecision
from meta_sched.common.target import Target


class SchedulerInterface(abc.ABC):
    """Base class for scheduling policies."""

    @property
    @abc.abstractmethod
    def targets(self: Self) -> List[Target]:
        """
        Get all targets which jobs may be assigned to.

        Returns
        -------
        List[Target]
            The list of all targets which jobs may be assigned to

        Raises
        ------
        NotImplementedError
            May be implemented in concrete scheduling policy"
        """
        raise NotImplementedError()

    @abc.abstractmethod
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
            May be implemented in concrete scheduling policy"
        """
        raise NotImplementedError()

    @abc.abstractmethod
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
