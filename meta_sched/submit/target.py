import abc
import enum
import uuid
from os import PathLike
from pathlib import Path
from typing import Any, Self

import invoke
from fabric import Connection
from fabric.config import Config

from meta_sched.submit import ssh
from meta_sched.submit.job import JobSpec


class Target(abc.ABC):
    def __init__(self: Self, id: str | uuid.UUID, host: str, port: int = 22) -> None:
        self.__id = id if isinstance(id, uuid.UUID) else uuid.UUID(id)
        self.__host = host
        self.__port = port

    @property
    def id(self: Self) -> uuid.UUID:
        return self.__id

    @property
    def has_user(self: Self) -> bool:
        config = ssh.get_config()
        return str(self.id) in config.get_hostnames() and "user" in config.lookup(
            str(self.id)
        )

    class TransferMode(enum.Enum):
        UPLOAD = 0
        DOWNLOAD = 1

    def transfer(
        self: Self,
        src: str | PathLike[Any],
        dst: str | PathLike[Any],
        mode: TransferMode,
    ) -> int:
        match mode:
            case self.TransferMode.UPLOAD:
                with self._connect() as connection:
                    status: int = connection.run(f"mkdir -p $(dirname {dst})").exited
                    if 0 != status:
                        return status
                dst = f"{str(self.id)}:{dst}"
            case self.TransferMode.DOWNLOAD:
                Path(dst).parent.mkdir(parents=True, exist_ok=True)
                src = f"{str(self.id)}:{src}"
        rsync_flags = ["--archive", "--progress", "--verbose"]
        cmd = f"rsync {' '.join(rsync_flags)} {src} {dst}"
        result = invoke.run(cmd)
        assert result
        return result.exited

    def clean_up(self: Self, job_spec: JobSpec) -> int:
        with self._connect() as connection:
            output_name = job_spec.output
            assert output_name
            output_dir = Path("meta-sched/jobs") / output_name
            status: int = connection.run(f"rm -rf {output_dir}").exited
            return status

    def _connect(self: Self) -> Connection:
        connect_kwargs = dict(allow_agent=False, look_for_keys=False)
        config = Config(ssh_config=ssh.get_config())
        return Connection(str(self.id), config=config, connect_kwargs=connect_kwargs)

    def execute(self: Self, job_spec: JobSpec) -> int:
        raise NotImplementedError()


class SlurmTarget(Target):
    def execute(self: Self, job_spec: JobSpec) -> int:
        with self._connect() as connection:
            output_name = job_spec.output
            assert output_name
            output_dir = Path("meta-sched/jobs") / output_name
            connection.run(f"mkdir -p {output_dir}")
            with connection.cd(output_dir):
                status: int = connection.run(f"srun {job_spec['executable']}").exited
                return status
