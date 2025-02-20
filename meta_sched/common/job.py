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
    df.set_index(["array_id", "array_idx"], inplace=True)
    df.sort_index(inplace=True)
    return df


class Spec:
    def __init__(
        self: Self,
        name: str,
        executable: str,
        time: str | int,
        array_size: int = 1,
        nodes: int = 1,
        ranks: int = 1,
        cores_per_rank: int = 1,
        required_modules: List[str] = [],
        **kwargs: Any,
    ) -> None:
        self.name = name
        self.executable = executable
        self.array_size = array_size
        self.nodes = nodes
        self.ranks = ranks
        self.cores_per_rank = cores_per_rank
        self.required_modules = required_modules
        if array_size < 0:
            raise ValueError('"array_size" must be at least 1')
        self.time = time_to_seconds(time)
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
