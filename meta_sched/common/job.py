"""Module containing functions and classes related to the jobs executed by the meta-scheduler."""

import abc
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Self

import pandas as pd

from meta_sched.common.utils import eprint, time_to_seconds


def get_jobs_dir(hidden: bool = False) -> Path:
    """
    Get the directory containing the job specifications for the current user in the current folder.

    Parameters
    ----------
    hidden : bool
        If true, the top-level directory is hidden (starts with ".")

    Returns
    -------
    Path
        The relative path to the directory containing the job specifications
    """
    return Path(("." if hidden else "") + "meta-sched/jobs")


def _get_job_output(
    job_spec: str, array_id: str, array_idx: int, hidden: bool = False
) -> Path:
    """
    Get the output path for a given job.

    Parameters
    ----------
    job_spec : str
        The name of the job specification corresponding to its folder name
    array_id : str
        The identifier of the job array
    array_idx : int
        The index of the job withing the array starting at 1
    hidden : bool
        If true, the top-level directory is hidden (starts with ".")

    Returns
    -------
    Path
        The relative path to the directory containing the job output
    """
    return get_jobs_dir(hidden=hidden) / f"{job_spec}/output/{array_id}/{array_idx}"


def get_job_outputs() -> pd.DataFrame:
    """
    Get a table of all jobs on the submit host for the current user.

    Returns
    -------
    pd.DataFrame
        The table of jobs
    """

    _columns = ["job_spec", "array_id", "array_idx"]
    df = eval("pd.DataFrame(columns=_columns)")  # Workaround pyright argument type

    def get_pid(job_output_path: Path) -> int | None:
        """
        Get the PID for the process executing a job on the submit host.

        Parameters
        ----------
        job_output_path : Path
            The path to the job output on the submit host containing the file ".pid"

        Returns
        -------
        int | None
            The PID if the job is running or None
        """
        pid_file = job_output_path / ".pid"
        if not pid_file.exists():
            return None
        try:
            return int(pid_file.read_text())
        except Exception:
            return None

    def get_status(job_output_path: Path) -> str | None:
        """
        Get the status of the job on the submit host.

        Parameters
        ----------
        job_output_path : Path
            The path to the job output on the submit host containing the file ".status"

        Returns
        -------
        str | None
            The status of the job or None if unknown
        """
        status_file = job_output_path / ".status"
        if not status_file.exists():
            return None
        return status_file.read_text().strip()

    if get_jobs_dir().is_dir():
        for p_job in get_jobs_dir().iterdir():
            if not p_job.is_dir():
                continue
            job_spec = p_job.name
            output_base_path = p_job / "output"
            if not output_base_path.is_dir():
                continue
            for p_array in output_base_path.iterdir():
                if not p_array.is_dir():
                    continue
                array_id = p_array.name
                for p_job in p_array.iterdir():
                    if not p_job.is_dir():
                        continue
                    try:
                        array_idx = int(p_job.name)
                    except ValueError:
                        continue
                    df.loc[len(df)] = [job_spec, array_id, array_idx]
    df["path"] = df.apply(lambda r: _get_job_output(*r), axis=1)
    df["pid"] = df["path"].apply(get_pid).astype(float)
    df["status"] = df["path"].apply(get_status).astype(str)
    # Try to interpret array_id as int to allow for correct sorting
    try:
        df["array_id"] = df["array_id"].astype(int)
    except Exception:
        eprint("Non integer array_id may result in incorrect sorting")
    df.set_index(["array_id", "array_idx"], inplace=True)
    df.insert(0, "job_id", [f"{i[0]}.{i[1]}" for i in df.index.values])
    df.sort_index(inplace=True)
    return df


class Spec:
    """Class representing a job specification."""

    def __init__(
        self: Self,
        name: str,
        cmd_main: str,
        time: str | None = None,
        seconds: int | None = None,
        cmd_setup: str | None = None,
        array_size: int = 1,
        nodes: int = 1,
        ranks: int = 1,
        cores_per_rank: int = 1,
        required_modules: List[str] = [],
        exclusive: bool = False,
        **kwargs: Any,
    ) -> None:
        """
        Create a new instance of a job specification.

        Parameters
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
        ranks : int
            The number of ranks required (defaults to 1)
        cores_per_rank : int
            The number of cores required (defaults to 1)
        required_modules : List[str]
            The list of required abstract environment modules (e.g. "MPI" instead of "openmpi" or "mpi/openmpi")
        exclusive : bool
            If true, the allocated nodes should only be used by this job
        **kwargs : Any
            Any additional parameters that are not implemented yet
        """
        if any(not (c.isalnum() or c in "-_") for c in name):
            raise ValueError("Job spec name contains illegal characters")
        self.name = name
        self.cmd_setup = cmd_setup
        self.cmd_main = cmd_main
        self.array_size = array_size
        self.nodes = nodes
        self.ranks = ranks
        self.cores_per_rank = cores_per_rank
        self.required_modules = required_modules
        self.exclusive = exclusive
        if array_size < 0:
            raise ValueError('"array_size" must be at least 1')
        if (time is None and seconds is None) or (
            time is not None and seconds is not None
        ):
            raise ValueError('Either "time" or "seconds" must be provided')
        if seconds is None:
            assert time is not None
            self.seconds = time_to_seconds(time)
        else:
            self.seconds = seconds
        eprint(__file__, "Got unused kwargs", kwargs)  # TODO

    @staticmethod
    def list() -> List[str]:
        """
        List all available job specifications for the current user.

        Returns
        -------
        List[str]
            A list of job specification names
        """
        if not get_jobs_dir().is_dir():
            return []
        return [p.name for p in get_jobs_dir().iterdir() if p.is_dir()]

    @classmethod
    def load(cls, name: str) -> Self:
        """
        Load a job specification.

        Parameters
        ----------
        name : str
            The name of the job specification to be loaded

        Returns
        -------
        Self
            The loaded job specification
        """
        path = get_jobs_dir() / name
        if not path.is_dir():
            raise ValueError("Job spec path must be a directory")
        kwargs = tomllib.loads((path / "spec.toml").read_text())
        return cls(name=name, **kwargs)


class Status(abc.ABC):
    """The class containing the classes for the status of a job."""

    class _Enum:
        """The base class for the status of a job."""

        def __init__(self: Self) -> None:
            """
            Create a new instance of a job status.

            Raises
            ------
            NotImplementedError
                The base class may not be instantiated
            """
            if self.__class__ == Status._Enum:
                raise NotImplementedError()
            self._data: Any = []

        def __str__(self: Self) -> str:
            return " ".join(
                [self.__class__.__name__.lower()] + [str(x) for x in self._data]
            )

    class Scheduled(_Enum):
        """State representing a job that has been assigned to a target but is not yet running."""

        def __init__(self: Self, target_id: str) -> None:
            """
            Create a new instance of a state representing a scheduled job.

            Parameters
            ----------
            target_id : str
                The identifier of the target on which the job should be executed
            """
            self._data = [target_id]

    class Running(_Enum):
        """Class representing a job that is currently running on a target."""

        def __init__(self: Self, target_id: str) -> None:
            """
            Create a new instance of a state representing a running job.

            Parameters
            ----------
            target_id : str
                The identifier of the target on which the job should be executed
            """
            self._data = [target_id]

    class Completed(_Enum):
        """Class representing a job that has successfully exited."""

        pass

    class Pending(_Enum):
        """Class representing a job that has been submitted but not yet assigned to a target."""

        pass

    class Failed(_Enum):
        """Class representing a job that was started on a target but has exited unsuccessfully."""

        def __init__(self: Self, status: int) -> None:
            """
            Create a new instance of a state representing a failed job.

            Parameters
            ----------
            status : int
                The exit code of the job
            """
            self._data = [status]

    class Canceled(_Enum):
        """Class representing a job that was cancelled by the user."""

        pass


@dataclass(frozen=True)
class Instance:
    """Class representing the instance of a single job within an array corresponding to a job specification."""

    spec: Spec
    array_id: str
    array_idx: int

    @property
    def local_output(self: Self) -> Path:
        """
        Get the relative path to the output files of the job on the submit host.

        Returns
        -------
        Path
            The path to the output files of the job on the submit host
        """
        return _get_job_output(
            self.spec.name, self.array_id, self.array_idx, hidden=False
        )

    @property
    def local_input(self: Self) -> Path:
        """
        Get the relative path to the input files of the job on the submit host.

        Returns
        -------
        Path
            The path to the input files of the job on the submit host
        """
        return get_jobs_dir(hidden=False) / self.spec.name / "input"

    @property
    def remote_output(self: Self) -> Path:
        """
        Get the relative path to the output files of the job on the target.

        Returns
        -------
        Path
            The path to the output files of the job on the target
        """
        return _get_job_output(
            self.spec.name, self.array_id, self.array_idx, hidden=True
        )

    @property
    def remote_input(self: Self) -> Path:
        """
        Get the relative path to the input files of the job on the target.

        Returns
        -------
        Path
            The path to the input files of the job on the target
        """
        return get_jobs_dir(hidden=True) / self.spec.name / "input"

    def set_status(self: Self, status: Status._Enum) -> None:
        """
        Update the status of the job on the submit host.

        Parameters
        ----------
        status : Status._Enum
            The new status of the job to be written to the ".status" file
        """
        (self.local_output / ".status").write_text(str(status))
