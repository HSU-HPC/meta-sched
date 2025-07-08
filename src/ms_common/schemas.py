"""Module containing schemas shared by the Meta Scheduler client and server components."""

import time
from typing import Any, Dict, List, Literal, NamedTuple, Optional, Self, Union

from pydantic import BaseModel, TypeAdapter, model_validator
from ms_common import utils
from ms_common.utils import eprint, time_to_seconds

class JobStatus(BaseModel):
    """
    Class representing the status of a job on a target.

    Attributes
    ----------
    nodes : int
        The number of nodes requested by the job
    time_limit : int
        The walltime in seconds requested by the job
    is_using_nodes : bool
        True, if the job is currently occupying the requested number of nodes (running vs. queued)
    time_ramining : int
        The remaining walltime in seconds for this job
    """
    nodes: int
    time_limit: int
    is_using_nodes: bool
    time_remaining: int

class TargetStatus(BaseModel):
    """
    Class representing the status of a target.

    Attributes
    ----------
    timestamp : int
        The unix timestamp (seconds since epoch) for the target status
    nodes_in_use : int
        The number of nodes which are currently used to run jobs
    nodes_available : int
        The number of nodes which are available for running jobs
    nodes_unavailable : int
        The number of nodes which are not in used but are not available for running jobs (e.g. due to maintenance)
    jobs_status : List[JobStatus]
        Information about the jobs currently running or scheduled on the target's local batch system
    """
    timestamp: int
    nodes_in_use: int
    nodes_available:int
    nodes_unavailable: int
    jobs_status: List[JobStatus]

class Target(BaseModel):
    """
    Base class representing a target system for job execution.

    Attributes
    ----------
    id : str
        The unique identifier of the target also used as its SSH alias
    batch_system : str
        The batch system used by the target, e.g. "slurm", "pbs", "none" (default, direct execution)
    queue : Optional[str]
        The name of the queue/partition used by the target (if applicable, e.g. for Slurm or PBS)
    host : str
        The hostname used to connect to the target
    nodes : int
        The number of compute nodes associated with this target
    cores_per_node : int
        The number of CPU cores per compute node for this target
    port : int
        The port used to connect to the target (defaults to default SSH port)
    max_time : Optional[str]
        The maximum time for which a job may run on this target formatted as "d-hh:MM:ss"
    max_nodes : Optional[int]
        The maximum number of compute nodes which may be allocated to a job
    source_scripts : List[str]
        A list of files which should be sourced after connecting to the target before running any commands
    module_map : Dict[str, str]
        A mapping of abstract environment modules such as "MPI" to concrete ones such as "mpi/openmpi",
        which should be loaded after connecting to the target
    tags : List[str]
        A list of tags for the target such as "gpu", "x86", "green", etc.
    """
    id: str
    batch_system: str = "none"
    queue: Optional[str] = None
    host: str
    nodes: int
    cores_per_node: int
    port: int = utils.DEFAULT_SSH_PORT
    max_time: Optional[str] = None
    max_nodes: Optional[int] = None
    source_scripts: List[str] = []
    module_map: Dict[str, str] = {}
    tags: List[str] = []

    @model_validator(mode="after")
    def validate_attributes(cls, target: Any) -> Any:
        """
        Validates an adjusts (!) target attributes. (Is idempotent.)

        Parameters
        ----------
        target : Any
            The target to validate and update

        Returns
        -------
        Any
            The validated and updated target
        """
        if target.batch_system not in ["none", "slurm", "pbs"]:
            raise ValueError(
                f"Invalid batch system {target.batch_system} for target {target.id}"
            )
        if target.batch_system == "none":
            if target.nodes != 1 or target.max_nodes is not None:
                raise ValueError(
                    f"Target {target.id} of type {target.__class__.__name__} does not support multiple nodes"
                )
            if target.queue is not None:
                eprint(
                    f"Warning: Target {target.id} of type {target.__class__.__name__} does not support queues. (Ignoring.)"
                )
            if target.max_time is not None:
                eprint(
                    f"Warning: Target {target.id} of type {target.__class__.__name__} does not support maximum job time. (Ignoring.)"
                )
        return target


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
    seconds : Optional[int]
        The amount of time in seconds that the job may run for (Alternative to parameter "time")
    cmd_setup : Optional[str] = None
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
    time: Optional[str] = None
    seconds: int = 0
    cmd_setup: Optional[str] = None
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
    array_id : int
        The ID of the job array
    array_size : int
        The number of jobs in the array (Matches request)
    token : str
        The random string required to look up the jobs in the array
    """
    array_id: int
    array_size: int
    token: str


class JobKey(NamedTuple):
    """
    Class representing the identifier of a job at the server.

    Attributes
    ----------
    token : str
        The random string used to look up jobs in an array
    array_id : int
        The ID of the job array this job belongs to
    array_idx : int
        The index of the job within its array
    """
    token: str
    array_id: int
    array_idx: int

    def __str__(self: Self) -> str:
        return f"{self.token}_{self.array_id}_{self.array_idx}"

class Impossible(BaseModel):
    """Scheduling decision indicating that a job cannot be scheduled (as requested).
    
    Attributes
    ----------
    type : str
        The type of the scheduling decision ("impossible")
    reason : Optional[str]
        An optional reason of why the job could not be scheduled
    """
    type: Literal["impossible"] = "impossible"
    reason: Optional[str] = None


class Assigned(BaseModel):
    """Scheduling decision indicating an assignment to a target for execution of the job.
        
    Attributes
    ----------
    type : str
        The type of the scheduling decision ("assigned")
    target_id : str
        The ID of the target on which the job should be run
    timestamp_start : int
        The timestamp when the job may be started (unix epoch in seconds)
    """
    type: Literal["assigned"] = "assigned"
    target_id: str
    timestamp_start: int = int(time.time())



SchedulingDecisionType = Union[Impossible, Assigned]


class SchedulingDecision:
    """Utility class for scheduling decisions."""

    def __init__(self: Self) -> None:
        """SchedulingDecision is not meant to be instantiated."""
        raise NotImplementedError("SchedulingDecision is a type alias, not a class.")

    @staticmethod
    def parse(data: Dict[str, Any]) -> SchedulingDecisionType:
        """Parse a scheduling decision from a dictionary.

        Parameters
        ----------
        data : Dict[str, Any]
            The dictionary containing the scheduling decision data

        Returns
        -------
        SchedulingDecisionType
            The parsed scheduling decision object
        """
        adapter: TypeAdapter[SchedulingDecisionType] = TypeAdapter(SchedulingDecisionType)
        return adapter.validate_python(data)
