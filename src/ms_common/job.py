"""Module containing functions and classes related to the jobs executed by the Meta Scheduler."""

from typing import Any, List, Set, Tuple

from pydantic import BaseModel, model_validator
from ms_common.utils import time_to_seconds

class Spec(BaseModel):
    """
    Class representing a job specification.

    Attributes
    ----------
    name : str
        The name of the job specification corresponding to the containing folder
    cmd_main : str
        The main shell command to be executed as the jobs on the batch system of the target
    time : str
        The maximum runtime as a formatted duration ("d-hh:MM:SS") of a job in the array or unrestricted if None (default)
    seconds : int | None
        The amount of time in seconds that the job may run for (Alternative to parameter "time")
    cmd_setup : str | None = None
        The shell command to run before the execution of the main command without using a batch system
    array_size : int
        The number of jobs in the array (defaults to 1)
    nodes : int
        The number of nodes required (defaults to 1)
    ranks_per_node : int
        The number of ranks required per node (defaults to 1)
    cores_per_rank : int
        The number of cores required per rank (defaults to 1)
    required_modules : List[str]
        The list of required abstract environment modules (e.g. "MPI" instead of "openmpi" or "mpi/openmpi")
    required_tags : List[str]
        The list of required tags (e.g. "x86", "gpu", "green")
    exclusive : bool
        If true, the allocated nodes should only be used by this job
    """

    name: str
    cmd_main: str
    time: str | None = None
    seconds: int = 0
    cmd_setup: str | None = None
    array_size: int = 1
    nodes: int = 1
    ranks_per_node: int = 1
    cores_per_rank: int = 1
    required_modules: List[str] = []
    required_tags: List[str] = []
    exclusive: bool = False

    @model_validator(mode="after")
    def validate_attributes(cls, spec: Any) -> Any:
        """
        Validates an adjusts (!) job attributes. (Is idempotent.)

        Parameters
        ----------
        spec : Any
            The job spec to validate and update

        Returns
        -------
        Any
            The validated and updated job spec
        """
        if any(not (c.isalnum() or c in "-_") for c in spec.name):
            raise ValueError("Job spec name contains illegal characters")
        if spec.array_size < 0:
            raise ValueError('"array_size" must be at least 1')
        if (spec.time is None and spec.seconds == 0) or (
            spec.time is not None and spec.seconds != 0
        ):
            raise ValueError('Either "time" or "seconds" must be provided')
        if spec.time is not None:
            spec.seconds = time_to_seconds(spec.time)
        spec.time = None
        if spec.seconds <= 0:
            raise ValueError('Duration ("time" or "seconds") must be a positive value')
        return spec

class ScheduleRequest(BaseModel):
    """
    Class representing the request to schedule a new job array.

    Attributes
    ----------
    available_targets : List[str]
        The target identifiers of all targets which the jobs may be scheduled on
    job_spec : JobSpec
        The specification of the job array
    """

    available_targets: List[str]
    job_spec: Spec

class ScheduleResponse(BaseModel):
    """
    Class representing the response to schedule a job array scheduling request.

    Attributes
    ----------
    array_id : str
        The ID of the job array
    array_size : int
        The number of jobs in the array (Matches request)
    token : str
        The random string required to look up the jobs in the array
    """
    array_id: str
    array_size: int
    token: str

JobKey = Tuple[str, str, int] # (token, array_id, array_idx)
