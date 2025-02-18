import enum
import sys
from os import PathLike
from pathlib import Path
from typing import Any, Dict, Self

import invoke
from fabric import Connection
from fabric.config import Config

from meta_sched.common.defaults import SSH_PORT
from meta_sched.common.job import Spec
from meta_sched.common.serialization import Serializable
from meta_sched.submit import ssh  # TODO package


class Target(Serializable):
    def __init__(
        self: Self, id: str, host: str, port: int = SSH_PORT, **kwargs: Any
    ) -> None:
        if self.__class__ == Target:
            raise NotImplementedError()
        self.__dict = locals() | kwargs
        del self.__dict["self"]
        del self.__dict["kwargs"]
        self.__id = id
        self.__host = host
        self.__port = port
        print("Got unused kwargs", kwargs)  # TODO

    def to_dict(self: Self) -> Dict[str, Any]:
        return self.__dict | {"batch_system": self.batch_system}

    @property
    def id(self: Self) -> str:
        return self.__id

    @property
    def batch_system(self: Self) -> str:
        raise NotImplementedError()

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
        cmd = f"rsync {' '.join(rsync_flags)} {src} {dst} 1>&2"
        result = invoke.run(cmd)
        assert result
        return result.exited

    def clean_up(self: Self, job_spec: Spec) -> int:
        with self._connect() as connection:
            assert job_spec.output
            status: int = connection.run(f"rm -rf {job_spec.output}").exited
            return status

    def _connect(self: Self) -> Connection:
        connect_kwargs = dict(allow_agent=False, look_for_keys=False)
        ssh_config = ssh.get_config()
        target_ssh_config = ssh_config.lookup(self.id)
        host = target_ssh_config["host"] if "host" in target_ssh_config else None
        if host != self.__host:
            print(
                f"Warning: Host missmatch for {self.id}:",
                host,
                "!=",
                self.__host,
                file=sys.stderr,
            )
        if self.__port != SSH_PORT and (
            "port" not in target_ssh_config
            or int(target_ssh_config["port"]) != self.__port
        ):
            raise RuntimeError(
                f"Cannot connect to target {self.id} (Non-default Port missing in SSH config)"
            )
        config = Config(ssh_config=ssh_config)
        return Connection(str(self.id), config=config, connect_kwargs=connect_kwargs)

    def execute(self: Self, job_spec: Spec) -> int:
        raise NotImplementedError()


class SlurmTarget(Target):
    @property
    def batch_system(self: Self) -> str:
        return "slurm"

    def execute(self: Self, job_spec: Spec) -> int:
        with self._connect() as connection:
            assert job_spec.output
            connection.run(f"mkdir -p {job_spec.output}")
            with connection.cd(job_spec.output):
                status: int = connection.run(f"srun {job_spec['executable']}").exited
                return status


class TargetFactory:
    @staticmethod
    def create(batch_system: str, **kwargs: Any) -> Target:
        target_cls = dict(
            slurm=SlurmTarget,
        )[batch_system]
        return target_cls(**kwargs)
