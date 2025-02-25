import abc
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Self

import pandas as pd

from meta_sched.common.utils import eprint, time_to_seconds


def get_jobs_dir() -> Path:
    return Path("meta-sched/jobs")


def _get_job_output(job_spec: str, array_id: str, array_idx: int) -> Path:
    return get_jobs_dir() / f"{job_spec}/output/{array_id}/{array_idx}"


def get_job_outputs() -> pd.DataFrame:
    _columns = ["job_spec", "array_id", "array_idx"]
    df = eval("pd.DataFrame(columns=_columns)")  # Workaround pyright argument type

    def get_pid(job_output_path: Path) -> int | None:
        pid_file = job_output_path / ".pid"
        if not pid_file.exists():
            return None
        try:
            return int(pid_file.read_text())
        except Exception:
            return None

    def get_status(job_output_path: Path) -> str | None:
        status_file = job_output_path / ".status"
        if not status_file.exists():
            return None
        return status_file.read_text().strip()

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
        **kwargs: Any,
    ) -> None:
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
        if not get_jobs_dir().is_dir():
            return []
        return [p.name for p in get_jobs_dir().iterdir() if p.is_dir()]

    @classmethod
    def load(cls, name: str) -> Self:
        path = get_jobs_dir() / name
        if not path.is_dir():
            raise ValueError("Job spec path must be a directory")
        kwargs = tomllib.loads((path / "spec.toml").read_text())
        return cls(name=name, **kwargs)


class Status(abc.ABC):
    class _Enum:
        def __init__(self: Self) -> None:
            if self.__class__ == Status._Enum:
                raise NotImplementedError()
            self._data: Any = []

        def __str__(self: Self) -> str:
            return " ".join(
                [self.__class__.__name__.lower()] + [str(x) for x in self._data]
            )

    class Scheduled(_Enum):
        def __init__(self: Self, target_id: str) -> None:
            self._data = [target_id]

    class Running(_Enum):
        def __init__(self: Self, target_id: str) -> None:
            self._data = [target_id]

    class Completed(_Enum):
        pass

    class Pending(_Enum):
        pass

    class Failed(_Enum):
        def __init__(self: Self, status: int) -> None:
            self._data = [status]

    class Canceled(_Enum):
        pass


@dataclass(frozen=True)
class Instance:
    spec: Spec
    array_id: str
    array_idx: int

    @property
    def output(self: Self) -> Path:
        return _get_job_output(self.spec.name, self.array_id, self.array_idx)

    @property
    def input(self: Self) -> Path:
        return get_jobs_dir() / self.spec.name / "input"

    def set_status(self: Self, status: Status._Enum) -> None:
        (self.output / ".status").write_text(str(status))
