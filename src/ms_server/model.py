"""Module containing the model for the Meta Scheduler server component."""

import abc
from typing import Any, Dict, List, Optional, Set

from ms_common.schemas import JobKey, SchedulingDecisionType
from ms_common.schemas import Spec as JobSpec
from ms_common.schemas import Target, TargetStatus
from pydantic import BaseModel, ConfigDict


class Job(BaseModel):
    """
    Class representing a job for the scheduler.

    Attributes
    ----------
    token : str
        The random string required to look up the job
    array_id : int
        The job array identifier
    array_idx : int
        The index of the job in the job array
    spec : JobSpec
        The specification of the job to be scheduled
    available_targets : List[str]
        The set of target IDs which this job may be assigned to
    scheduling_decision : Optional[SchedulingDecisionType]
        The decision by the scheduling policy regarding this job or None, if the job has not yet been scheduled
    timestamp_start : Optional[int]
        The unix timestamp (seconds since epoch) of the job start or None, if the job has not yet started
    timestamp_end : Optional[int]
        The unix timestamp (seconds since epoch) of the job end or None, if the job has not yet ended
    """

    token: str
    array_id: int
    array_idx: int
    spec: JobSpec
    available_targets: List[str]
    scheduling_decision: Optional[SchedulingDecisionType]
    timestamp_start: Optional[int] = None
    timestamp_end: Optional[int] = None

    # Used by pydantic to allow instantiation from SQLAlchemy model
    model_config = ConfigDict(from_attributes=True)

    @property
    def key(self: "Job") -> JobKey:
        """
        Get the key of the job.

        Returns
        -------
        JobKey
            The key which uniquely identifies the job (includes token required to look it up)
        """
        return JobKey(self.token, self.array_id, self.array_idx)


TargetsStatus = Dict[Target, Optional[TargetStatus]]


class Model(abc.ABC):
    """
    Model interface for accessing and modifying the state of the Meta Scheduler server component.
    """

    async def create_job_array(
        self: "Model", spec: JobSpec, available_targets: Set[str], token: str
    ) -> int:
        """
        Create a new array of jobs for scheduling.

        Parameters
        ----------
        spec : job.Spec
            The job specification (also determines the number of jobs in the array)
        available_targets: Set[str]
            The set of targets on which the jobs may be executed
        token: str
            The token to associate with the jobs (required to look them up in the database)

        Raises
        ------
        NotImplementedError
            Must be implemented by the concrete model
        """
        raise NotImplementedError()

    async def get_pending_jobs(self: "Model") -> List[Job]:
        """
        Get a list of jobs which are pending scheduling.

        Returns
        -------
        List[Job]
            The list of pending jobs

        Raises
        ------
        NotImplementedError
            Must be implemented by the concrete model
        """
        raise NotImplementedError()

    async def get_decided_jobs(self: "Model") -> List[Job]:
        """
        Get a list of jobs for which a scheduling decision has been made.

        Returns
        -------
        List[Job]
            The list of scheduled jobs

        Raises
        ------
        NotImplementedError
            Must be implemented by the concrete model
        """
        raise NotImplementedError()

    async def update_job(self: "Model", job_key: JobKey, data: Dict[str, Any]) -> None:
        """
        Update an existing job.

        Parameters
        ----------
        job_key : JobKey
            The key of the job to be updated
        data : Dict[str, Any]
            The keys and corresponding values which should be updated at the job

        Raises
        ------
        KeyError
            If the job with the corresponding key does not exist
        NotImplementedError
            Must be implemented by the concrete model
        """
        raise NotImplementedError()

    async def remove_job(self: "Model", job_key: JobKey) -> None:
        """
        Remove a job.

        Parameters
        ----------
        job_key : JobKey
            The key of the job to be deleted

        Raises
        ------
        KeyError
            If the job with the corresponding key does not exist
        NotImplementedError
            Must be implemented by the concrete model
        """
        raise NotImplementedError()

    async def await_scheduling_decision(
        self: "Model", job_key: JobKey
    ) -> SchedulingDecisionType:
        """
        Await a scheduling decision for a specific job.

        Parameters
        ----------
        job_key : JobKey
            The key of the job for which to await scheduling

        Raises
        ------
        KeyError
            If the job with the corresponding key does not exist
        NotImplementedError
            Must be implemented by the concrete model
        """
        raise NotImplementedError()

    async def update_targets_status(
        self: "Model", target_id: str, status: TargetStatus
    ) -> None:
        """
        Update the status of a target.

        Parameters
        ----------
        target_id : str
            The ID of the target for which to update the status
        status : TargetStatus
            The new last known status of the target

        Raises
        ------
        NotImplementedError
            Must be implemented by the concrete model
        """
        raise NotImplementedError()

    async def get_targets_status(
        self: "Model",
    ) -> TargetsStatus:
        """
        Get all targets and their last known status.

        Returns
        -------
        TargetsStatus
            A mapping from target to last known status

        Raises
        ------
        NotImplementedError
            Must be implemented by the concrete model
        """
        raise NotImplementedError()
