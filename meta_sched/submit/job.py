import tomllib
from pathlib import Path
from typing import Any, List, Self

from meta_sched.submit.utils import InstantiationException


class JobSpec(dict[str, Any]):
    __create_key = object()

    def __init__(self: Self, create_key: object, path: Path) -> None:
        if create_key != JobSpec.__create_key:
            raise InstantiationException(self)
        if path.is_dir():
            path /= "job.toml"
        kvs = tomllib.loads(path.read_text())
        for k, v in kvs.items():
            self[k] = v
        self["path"] = path

    @property
    def is_valid(self: Self) -> bool:
        raise NotImplementedError()

    @property
    def output_dir(self: Self) -> Path | None:
        if "local_array_id" not in self or "array_idx" not in self:
            return None
        return Path(
            self["path"].parent
            / "output"
            / f"{self['local_array_id']}-{self['array_idx']}"
        )

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
