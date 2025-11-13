"""Module containing code for instantiating remote target classes."""

from ms_common.schemas import Target

from ms_client.remote_target import RemoteTarget
from ms_client.remote_target.direct_execution import DirectExecutionRemoteTarget
from ms_client.remote_target.pbs import PBSRemoteTarget
from ms_client.remote_target.slurm import SlurmRemoteTarget


def remote_target_from_target(target: Target) -> RemoteTarget:
    """
    Create an instance of the corresponding child class for a given target.
    NOTE: Remote targets are context managers. (Usage: `with remote_target_from_target(...) as remote_target:`)

    Parameters
    ----------
    target : Target
        The target for which to create an instance of RemoteTarget

    Returns
    -------
    RemoteTarget
        An instance of the child class matching the batch system of the target
    """
    sentinel = RemoteTarget._FactoryAccessToken()
    if target.batch_system == "slurm":
        return SlurmRemoteTarget(sentinel, target)
    elif target.batch_system == "pbs":
        return PBSRemoteTarget(sentinel, target)
    elif target.batch_system == "none":
        return DirectExecutionRemoteTarget(sentinel, target)
    else:
        raise ValueError(f'Unknown batch system "{target.batch_system}"')
