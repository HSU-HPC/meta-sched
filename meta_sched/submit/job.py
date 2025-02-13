import tomllib
from pathlib import Path
from typing import Any, List, Self

from meta_sched.submit.utils import InstantiationException


class JobSpec(dict[str, Any]):
    __create_key = object()

    def __init__(self: Self, create_key: object, path: Path) -> None:
        if create_key != JobSpec.__create_key:
            raise InstantiationException(self)
        if not path.is_dir():
            raise ValueError("Job spec path must be a directory")
        self.__name = path.name
        kvs = tomllib.loads((path / "job.toml").read_text())
        for k, v in kvs.items():
            self[k] = v
        self["path"] = path

    @property
    def name(self: Self) -> str:
        return self.__name

    @property
    def is_valid(self: Self) -> bool:
        raise NotImplementedError()

    @property
    def output(self: Self) -> Path | None:
        if "local_array_id" not in self or "array_idx" not in self:
            return None
        return Path(self.name) / f"output-{self['local_array_id']}-{self['array_idx']}"

    @property
    def input(self: Self) -> Path:
        return Path(self.name) / "input"

    @staticmethod
    def get_user_jobs_dir() -> Path:
        return Path.home() / "meta-sched" / "jobs"

    @staticmethod
    def list() -> List[str]:
        return [p.name for p in JobSpec.get_user_jobs_dir().iterdir() if p.is_dir()]

    @classmethod
    def load(cls, spec: str) -> Self:
        job_path = JobSpec.get_user_jobs_dir() / spec
        return cls(cls.__create_key, job_path)
