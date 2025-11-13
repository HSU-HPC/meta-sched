"""Module containing the interface for the scheduling policy."""

import abc
from typing import List, Set

from ms_common.schemas import (
    JobKey,
    ScheduleResponse,
    SchedulingDecisionType,
    Spec,
    Target,
)


class SchedulerClientInterface(abc.ABC):
    """Base class for scheduling policies."""

    @property
    @abc.abstractmethod
    def targets(self: "SchedulerClientInterface") -> List[Target]:
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
        self: "SchedulerClientInterface", job_spec: Spec, available_targets: Set[str]
    ) -> ScheduleResponse:
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
        ScheduleResponse
            The response from the scheduler containing information to look up the jobs that were created

        Raises
        ------
        NotImplementedError
            Must be implemented in concrete client"
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def poll_scheduling_decision(
        self: "SchedulerClientInterface",
        job_key: JobKey,
    ) -> SchedulingDecisionType:
        """
        Await the final decision of the scheduler (may block for very long.)

        Parameters
        ----------
        job_key : JobKey
            The token, array id, and array index required to look up the job

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
    def cancel_job(self: "SchedulerClientInterface", job_key: JobKey) -> None:
        """
        Cancel a job.

        Parameters
        ----------
        job_key : JobKey
            The token, array id, and array index required to look up the job

        Raises
        ------
        NotImplementedError
            Must be implemented in concrete client
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def update_job_started(
        self: "SchedulerClientInterface", job_key: JobKey, timestamp: int
    ) -> None:
        """
        Set the timestamp when a job was started.

        Parameters
        ----------
        job_key : JobKey
            The token, array id, and array index required to look up the job
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
        self: "SchedulerClientInterface", job_key: JobKey, timestamp: int
    ) -> None:
        """
        Set the timestamp when a job was ended.

        Parameters
        ----------
        job_key : JobKey
            The token, array id, and array index required to look up the job
        timestamp : int
            The end time of the job as a unix timestamp (seconds since epoch)

        Raises
        ------
        NotImplementedError
            Must be implemented in concrete client
        """
        raise NotImplementedError()
