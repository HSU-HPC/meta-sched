"""Module containing functions and classes related to the jobs executed by the Meta Scheduler client component."""

import abc
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

import pandas as pd
import tomli
from ms_common.schemas import Spec
from ms_common.utils import eprint


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


def list_job_spec_names() -> List[str]:
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


def load_job_spec(name: str) -> Spec:
    """
    Load a job specification.

    Parameters
    ----------
    name : str
        The name of the job specification to be loaded

    Returns
    -------
    Spec
        The loaded job specification
    """
    path = get_jobs_dir() / name
    if not path.is_dir():
        raise ValueError("Job spec path must be a directory")
    kwargs = tomli.loads((path / "spec.toml").read_text())
    return Spec(name=name, **kwargs)


def _get_job_output(
    job_spec: str, array_id: int, array_idx: int, hidden: bool = False
) -> Path:
    """
    Get the output path for a given job.

    Parameters
    ----------
    job_spec : str
        The name of the job specification corresponding to its folder name
    array_id : int
        The identifier of the job array
    array_idx : int
        The index of the job withing the array
    hidden : bool
        If true, the top-level directory is hidden (starts with ".")

    Returns
    -------
    Path
        The relative path to the directory containing the job output
    """
    return get_jobs_dir(hidden=hidden) / f"{job_spec}/output/{array_id}_{array_idx}"


def get_job_outputs() -> pd.DataFrame:
    """
    Get a table of all jobs on the submit host for the current user.

    Returns
    -------
    pd.DataFrame
        The table of jobs
    """

    rows = []

    def get_pid(job_output_path: Path) -> Optional[int]:
        """
        Get the PID for the process executing a job on the submit host.

        Parameters
        ----------
        job_output_path : Path
            The path to the job output on the submit host containing the file ".pid"

        Returns
        -------
        Optional[int]
            The PID if the job is running or None
        """
        pid_file = job_output_path / ".pid"
        if not pid_file.exists():
            return None
        try:
            return int(pid_file.read_text())
        except Exception:
            return None

    def get_status(job_output_path: Path) -> Optional[str]:
        """
        Get the status of the job on the submit host.

        Parameters
        ----------
        job_output_path : Path
            The path to the job output on the submit host containing the file ".status"

        Returns
        -------
        Optional[str]
            The status of the job or None if unknown
        """
        status_file = job_output_path / ".status"
        if not status_file.exists():
            return "unknown"
        return status_file.read_text().strip()

    if get_jobs_dir().is_dir():
        for p_job in get_jobs_dir().iterdir():
            if not p_job.is_dir():
                continue
            job_spec = p_job.name
            output_base_path = p_job / "output"
            if not output_base_path.is_dir():
                continue
            for job_output_dir in output_base_path.iterdir():
                if not job_output_dir.is_dir():
                    continue
                array_id = "_".join(job_output_dir.name.split("_")[:-1])
                try:
                    array_idx = int(job_output_dir.name.split("_")[-1])
                except ValueError:
                    continue
                rows.append(
                    dict(
                        job_spec=job_spec,
                        array_id=array_id,
                        array_idx=array_idx,
                    )
                )

    column_types = dict(job_spec=str, array_id=int, array_idx=int)
    df = pd.DataFrame(rows).astype(column_types)

    def get_job_output(row: pd.Series) -> Path:  # type: ignore[type-arg]
        """Wrapper for _get_job_output(...) for use with df.apply"""
        return _get_job_output(*row)

    df["path"] = df.apply(lambda r: get_job_output(r), axis=1)  # type: ignore[call-overload, unused-ignore]
    df["pid"] = df["path"].apply(get_pid).astype(float)
    df["status"] = df["path"].apply(get_status).astype(str)
    # Try to interpret array_id as int to allow for correct sorting
    try:
        df["array_id"] = df["array_id"].astype(int)
    except Exception:
        eprint("Non integer array_id may result in incorrect sorting")
    df.set_index(["array_id", "array_idx"], inplace=True)
    job_ids = pd.Series([f"{i[0]}_{i[1]}" for i in df.index.values], index=df.index)
    df.insert(0, "job_id", job_ids)
    df.sort_index(inplace=True)
    return df


class Status(abc.ABC):
    """The class containing the classes for the status of a job."""

    class _Enum:
        """The base class for the status of a job."""

        def __init__(self: "Status._Enum") -> None:
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

        def __str__(self: "Status._Enum") -> str:
            return " ".join(
                [self.__class__.__name__.lower()] + [str(x) for x in self._data]
            )

    class Unknown(_Enum):
        """Class representing a job that has an unknown state (which should only be temporary)."""

        pass

    class Scheduled(_Enum):
        """State representing a job that has been assigned to a target but is not yet running."""

        def __init__(self: "Status._Enum", target_id: str) -> None:
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

        def __init__(self: "Status._Enum", target_id: str) -> None:
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

        def __init__(self: "Status._Enum", status: int = 0) -> None:
            """
            Create a new instance of a state representing a failed job.

            Parameters
            ----------
            status : int
                The exit code of the job
            """
            self._data = [status]

        def __str__(self: "Status._Enum") -> str:
            return f"completed ({'?' if self._data[0] == -1 else self._data[0]})"

    class Completing(_Enum):
        """Class representing a job that has successfully finished executing with some pending operations (e.g. downloading results)."""

        pass

    class Pending(_Enum):
        """Class representing a job that has been submitted but not yet assigned to a target."""

        pass

    class Failed(_Enum):
        """Class representing a job that was started on a target but has exited unsuccessfully."""

        def __init__(self: "Status._Enum", status: int) -> None:
            """
            Create a new instance of a state representing a failed job.

            Parameters
            ----------
            status : int
                The exit code of the job
            """
            self._data = [status]

        def __str__(self: "Status._Enum") -> str:
            return f"failed ({self._data[0]})"

    class Canceled(_Enum):
        """Class representing a job that was cancelled by the user."""

        pass


@dataclass(frozen=True)
class Instance:
    """
    Class representing the instance of a single job within an array corresponding to a job specification.

    Attributes
    ----------
    spec : Spec
        The job spec
    array_id : int
        The id of the job array
    array_idx : int
        The index of the job within the array
    """

    spec: Spec
    array_id: int
    array_idx: int

    @property
    def local_output(self: "Instance") -> Path:
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
    def local_dir(self: "Instance") -> Path:
        """
        Get the relative path to the directory containing the files of the job on the submit host.

        Returns
        -------
        Path
            The path to the input files of the job on the submit host
        """
        return get_jobs_dir(hidden=False) / self.spec.name

    @property
    def local_input(self: "Instance") -> Path:
        """
        Get the relative path to the input files of the job on the submit host.

        Returns
        -------
        Path
            The path to the input files of the job on the submit host
        """
        return self.local_dir / "input"

    @property
    def remote_output(self: "Instance") -> Path:
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
    def remote_input(self: "Instance") -> Path:
        """
        Get the relative path to the input files of the job on the target.

        Returns
        -------
        Path
            The path to the input files of the job on the target
        """
        return get_jobs_dir(hidden=True) / self.spec.name / "input"

    def set_status(self: "Instance", status: Status._Enum) -> None:
        """
        Update the status of the job on the submit host.

        Parameters
        ----------
        status : Status._Enum
            The new status of the job to be written to the ".status" file
        """
        (self.local_output / ".status").write_text(str(status))
