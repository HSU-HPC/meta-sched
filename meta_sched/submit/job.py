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
        self.__path = self.get_jobs_dir() / self.__name

    @property
    def is_valid(self: Self) -> bool:
        raise NotImplementedError()

    @property
    def name(self: Self) -> str:
        return self.__name

    @property
    def output(self: Self) -> Path | None:
        if "array_id" not in self or "array_idx" not in self:
            return None
        return self.__path / f"{self['array_id']}-{self['array_idx']}"

    @property
    def input(self: Self) -> Path:
        return self.__path / "input"

    @staticmethod
    def get_jobs_dir() -> Path:
        return Path("meta-sched/jobs")

    @staticmethod
    def list() -> List[str]:
        return [p.name for p in JobSpec.get_jobs_dir().iterdir() if p.is_dir()]

    @classmethod
    def load(cls, spec: str) -> Self:
        job_path = cls.get_jobs_dir() / spec
        return cls(cls.__create_key, job_path)
