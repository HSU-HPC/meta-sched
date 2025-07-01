"""Module containing classes for managing data transfer and command execution for target systems."""

from typing import Any, Dict, List

from pydantic import BaseModel, model_validator
from ms_common import utils
from ms_common.utils import eprint

class Target(BaseModel):
    """
    Base class representing a target system for job execution.

    Attributes
    ----------
    id : str
        The unique identifier of the target also used as its SSH alias
    batch_system : str
        The batch system used by the target, e.g. "slurm", "pbs", "none" (default, direct execution)
    queue : str | None
        The name of the queue/partition used by the target (if applicable, e.g. for Slurm or PBS)
    host : str
        The hostname used to connect to the target
    nodes : int
        The number of compute nodes associated with this target
    cores_per_node : int
        The number of CPU cores per compute node for this target
    port : int
        The port used to connect to the target (defaults to default SSH port)
    max_time : str
        The maximum time for which a job may run on this target formatted as "d-hh:MM:ss"
    max_nodes : int
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
    queue: str | None = None
    host: str
    nodes: int
    cores_per_node: int
    port: int = utils.DEFAULT_SSH_PORT
    max_time: str | None = None
    max_nodes: int | None = None
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
