"""Module containing the interface for the scheduling policy."""

import abc
from typing import List, Self, Set

from ms_common.job import Spec
from ms_common.scheduling_decision import SchedulingDecisionType
from ms_common.target import Target


class SchedulerClientInterface(abc.ABC):
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
            Must be implemented in concrete client"
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def submit_job_array(
        self: Self, job_spec: Spec, available_targets: Set[str]
    ) -> str:
        """
        Create a new unique identifier for a new job array and schedule the corresponding jobs.

        Parameters
        ----------
        job_spec : Spec
            The job specification
        available_targets : List[str]
            List of identifiers of targets available to the client for job submission

        Returns
        -------
        str
            The array ID of the new job array

        Raises
        ------
        NotImplementedError
            Must be implemented in concrete client"
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def poll_scheduling_decision(
        self: Self, array_id: str, array_idx: int
    ) -> SchedulingDecisionType:
        """
        Await the final decision of the scheduler (may block for very long.)

        Parameters
        ----------
        array_id : str
            The unique identifier of the job array
        array_idx : int
            The index of the job in the job array

        Returns
        -------
        SchedulingDecision
            The scheduling decision based on the policy

        Raises
        ------
        NotImplementedError
            Must be implemented in concrete client
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def cancel_job(self: Self, array_id: str, array_idx: int) -> None:
        """
        Cancel a job.

        Parameters
        ----------
        array_id : str
            The unique identifier of the job array
        array_idx : int
            The index of the job in the job array

        Raises
        ------
        NotImplementedError
            Must be implemented in concrete client
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def update_job_started(
        self: Self, array_id: str, array_idx: int, timestamp: int
    ) -> None:
        """
        Set the timestamp when a job was started.

        Parameters
        ----------
        array_id : str
            The unique identifier of the job array
        array_idx : int
            The index of the job in the job array
        timestamp : int
            The start time of the job as a unix timestamp (seconds since epoch)

        Raises
        ------
        NotImplementedError
            Must be implemented in concrete client
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def update_job_ended(
        self: Self, array_id: str, array_idx: int, timestamp: int
    ) -> None:
        """
        Set the timestamp when a job was ended.

        Parameters
        ----------
        array_id : str
            The unique identifier of the job array
        array_idx : int
            The index of the job in the job array
        timestamp : int
            The end time of the job as a unix timestamp (seconds since epoch)

        Raises
        ------
        NotImplementedError
            Must be implemented in concrete client
        """
        raise NotImplementedError()
