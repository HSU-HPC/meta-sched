import enum
import sys
from os import PathLike
from pathlib import Path
from typing import Any, Dict, Self, Tuple

import invoke
from fabric import Connection
from fabric.config import Config

from meta_sched.common.defaults import SSH_PORT
from meta_sched.common.job import Instance as Job
from meta_sched.common.job import Spec
from meta_sched.common.serialization import Serializable
from meta_sched.common.utils import seconds_to_time, time_to_seconds
from meta_sched.common import ssh


class Target(Serializable):
    def __init__(
        self: Self,
        id: str,
        host: str,
        nodes: int,
        cores_per_node: int,
        port: int = SSH_PORT,
        max_time: str | int | None = None,
        max_nodes: int | None = None,
        module_map: Dict[str, str] = {},
        **kwargs: Any,
    ) -> None:
        if self.__class__ == Target:
            raise NotImplementedError()
        self.__dict = locals() | kwargs
        del self.__dict["self"]
        del self.__dict["kwargs"]
        self.__id = id
        self.__host = host
        self.__port = port
        self.__nodes = nodes
        self.__cores_per_node = cores_per_node
        self.__max_time = None if max_time is None else time_to_seconds(max_time)
        self.__max_nodes = max_nodes
        self.__module_map = module_map
        print(__file__, "Got unused kwargs", kwargs, file=sys.stderr)  # TODO

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

    def is_suitable(self: Self, job_spec: Spec) -> Tuple[bool, str]:
        if not self.has_user:
            return False, "Credentials missing"
        if self.__max_time is not None and job_spec.time > self.__max_time:
            return False, "Too much time required"
        max_nodes = (
            min(self.__nodes, self.__max_nodes) if self.__max_nodes else self.__nodes
        )
        if job_spec.nodes > max_nodes:
            return False, "Too many nodes required"
        cores = job_spec.ranks * job_spec.cores_per_rank
        if cores > self.__cores_per_node:
            return False, "Too many cores required"
        if any(m not in self.__module_map for m in job_spec.required_modules):
            return False, "Required module missing"
        return True, "OK"

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

    def clean_up(self: Self, job: Job) -> int:
        with self._connect() as connection:
            assert job.output
            status: int = connection.run(f"rm -rf {job.output}").exited
            return status

    def _connect(self: Self) -> Connection:
        connect_kwargs = dict(allow_agent=False, look_for_keys=False)
        ssh_config = ssh.get_config()
        target_ssh_config = ssh_config.lookup(self.id)
        host = (
            target_ssh_config["hostname"] if "hostname" in target_ssh_config else None
        )
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

    def _execute_batch_system(
        self: Self, connection: Connection, job_spec: Spec, env: Dict[str, Any] = {}
    ) -> int:
        raise NotImplementedError()

    def execute(self: Self, job: Job) -> int:
        with self._connect() as connection:
            assert job.output
            connection.run(f"mkdir -p {job.output}")
            env = dict(
                MS_ARRAY_ID=job.array_id,
                MS_ARRAY_IDX=job.array_idx,
                MS_INPUT=f"~/{job.input}",
                MS_OUTPUT=f"~/{job.output}",
            )
            for module in job.spec.required_modules:
                module = self.__module_map[module]
                status: int = connection.run(f"ml {module}").exited
                if 0 != status:
                    return status
            with connection.cd(job.output):
                return self._execute_batch_system(connection, job.spec, env)


class SlurmTarget(Target):
    def __init__(self: Self, partition: str | None = None, **kwargs: Any) -> None:
        self.partition = partition
        super().__init__(**kwargs)

    @property
    def batch_system(self: Self) -> str:
        return "slurm"

    def _execute_batch_system(
        self: Self, connection: Connection, job_spec: Spec, env: Dict[str, Any] = {}
    ) -> int:
        argv = ["srun"]
        if self.partition:
            argv.append(f"--partition={self.partition}")
        argv.append(f"--time={seconds_to_time(job_spec.time)}")
        argv.append(job_spec.executable)
        status: int = connection.run(" ".join(argv), warn=True, env=env).exited
        return status


class TargetFactory:
    @staticmethod
    def create(batch_system: str, **kwargs: Any) -> Target:
        target_cls = dict(
            slurm=SlurmTarget,
        )[batch_system]
        return target_cls(**kwargs)
