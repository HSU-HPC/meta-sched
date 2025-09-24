"""Module containing schemas shared by the Meta Scheduler client and server components."""

import math
import time
from typing import Any, Dict, List, Literal, NamedTuple, Optional, Tuple, Union

from dataclasses import dataclass
import sympy
from sympy import Float
from sympy import Integer
from sympy.parsing import sympy_parser

from frozendict import frozendict
from pydantic import BaseModel, TypeAdapter, field_validator, model_validator, computed_field
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
    source_scripts : Tuple[str, ...]
        A list of files which should be sourced after connecting to the target before running any commands
    module_map : Dict[str, str]
        A mapping of abstract environment modules such as "MPI" to concrete ones such as "mpi/openmpi",
        which should be loaded after connecting to the target
    tags : Tuple[str, ...]
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
    source_scripts: Tuple[str, ...] = ()
    _module_map: frozendict[str, str] = frozendict[str, str]()

    @computed_field(return_type=Dict[str, str])
    def module_map(self) -> Dict[str, str]:
        """
        Target module mapping (e.g. MPI -> OpenMPI).
        
        Returns
        -------
        Dict[str, str]
            The mapping from abstract to concrete environment modules provided by the target
        """
        return dict(self._module_map)

    tags: Tuple[str, ...] = ()

    model_config = dict(frozen=True, arbitrary_types_allowed=True)

    @field_validator("module_map", mode="before")
    def convert_module_map(cls, v: Any) -> frozendict[str,str]:
        """
        Validates "module_map" attribute of the target.

        Parameters
        ----------
        v : Any
            The value assigned to the attribute "module_map" of the target before validation

        Returns
        -------
        frozendict[str,str]
            The validated value of the attribute "module_map" assigned to the target
        """
        is_valid = True
        if isinstance(v, frozendict) or isinstance(v, dict):
            for k, val in v.items():
                if not isinstance(k, str) or not isinstance(val, str):
                    is_valid = False
                    break
        else:
            is_valid = False
        if not is_valid:
            raise TypeError("\"module_map\" must be a dict or frozendict with keys and values only of type str")
        return frozendict(v)

    def __init__(self: "Target", **data: Any) -> None:
        """Create a new instance of the target objects.
        
        Parameters
        ----------
        data : Any
            Fields of the object to be created (Must contain "module_map")
        """
        # Convert module_map to frozendict during initialization
        module_map = data.pop('module_map', {})
        super().__init__(**data)
        object.__setattr__(self, '_module_map', frozendict(module_map))

    @model_validator(mode="after")
    def validate_attributes(cls, target: Any) -> Any:
        """
        Validates target attributes.

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
        The maximum runtime of a job in the array or unrestricted if None (default)
        May be given as formatted duration ("d-hh:MM:SS") or SymPy expression for seconds starting with "=" where p is the total number of cores
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
    ranks_per_node: Optional[int] = None
    cores_per_rank: int = 1
    required_modules: List[str] = []
    required_tags: List[str] = []
    exclusive: bool = False

    
    def get_target_seconds(self: "Spec", target: Target, array_idx: int) -> int:
        """
        Get the requested seconds based on a concrete target. 
        (Evaluates expression if applicable.)

        Parameters
        ----------
        target : Target
            The target for which the seconds of the job should be returned
        array_idx : int
            The index of the job in the corresponding job array

        Returns
        -------
        int
            The duration in seconds
        """
        if self.seconds > 0:
            return self.seconds # Fixed value
        else:
            # Expression based value
            assert self.time is not None
            total_cores, idx = sympy.symbols("p,i")
            substitutions = {
                total_cores: self.nodes * (self.ranks_per_node if self.ranks_per_node else target.cores_per_node),
                idx: array_idx,
            }
            try:
                expression = sympy_parser.parse_expr(self.time[1:].strip()).subs(substitutions)
            except SyntaxError as e:
                assert False, f"Could not parse expression: {e.msg} in \"{e.text}\" at {e.offset}"
            assert type(expression) in [Integer, Float], "Time expression must evaluate to a number"
            seconds = int(math.ceil(expression.evalf()))
            return seconds

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
        if spec.time is not None and not spec.time.startswith("="):
            spec.seconds = time_to_seconds(spec.time)
            spec.time = None
        if spec.seconds < 0:
            raise ValueError('Duration ("time" or "seconds") must be a positive value')
        @dataclass
        class MockTarget:
            """
            Stand in for target objects used to resolve the job seconds to request.
            (Only used here for validation.)
            """
            nodes=1
            cores_per_node=1
        # Evaluate expression (force potential expression error)
        spec.get_target_seconds(MockTarget, 0)
        for k,v in {
            spec.array_size: "Array size",
            spec.nodes: "Node count",
            spec.ranks_per_node: "Ranks per node",
            spec.cores_per_rank: "Cores per rank",
        }.items():
            if k is not None and k < 1:
                raise ValueError(f"{v} must be positive")
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

    def __str__(self: "JobKey") -> str:
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

    def __init__(self: "SchedulingDecision") -> None:
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
