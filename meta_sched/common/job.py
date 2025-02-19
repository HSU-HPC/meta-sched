import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Self

from meta_sched.common.utils import time_to_seconds


def _get_jobs_dir() -> Path:
    return Path("meta-sched/jobs")


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
        print(__file__, "Got unused kwargs", kwargs, file=sys.stderr)  # TODO

    @staticmethod
    def list() -> List[str]:
        return [p.name for p in _get_jobs_dir().iterdir() if p.is_dir()]

    @classmethod
    def load(cls, name: str) -> Self:
        path = _get_jobs_dir() / name
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
        return self.__local_path / f"output/{self.array_id}/{self.array_idx}"

    @property
    def input(self: Self) -> Path:
        return self.__local_path / "input"

    @property
    def __local_path(self: Self) -> Path:
        return _get_jobs_dir() / self.spec.name
