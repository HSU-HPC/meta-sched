import abc
import enum
from os import PathLike
from pathlib import Path
from typing import Any, Dict, Self, Tuple

import invoke
from fabric import Connection
from fabric.config import Config

from meta_sched.common import ssh
from meta_sched.common.job import Instance as Job
from meta_sched.common.job import Spec
from meta_sched.common.serialization import Serializable
from meta_sched.common.utils import (
    EX_BASH_COMMAND_NOT_FOUND,
    eprint,
    expect_ok,
    seconds_to_time,
    time_to_seconds,
)


class Target(Serializable):
    def __init__(
        self: Self,
        id: str,
        host: str,
        nodes: int,
        cores_per_node: int,
        port: int = ssh.DEFAULT_PORT,
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
        eprint(__file__, "Got unused kwargs", kwargs)  # TODO

    def to_dict(self: Self) -> Dict[str, Any]:
        return self.__dict | {"batch_system": self.get_batch_system()}

    @property
    def id(self: Self) -> str:
        return self.__id

    @property
    def host(self: Self) -> str:
        return self.__host

    @staticmethod
    def get_batch_system() -> str:
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
    ) -> None:
        match mode:
            case self.TransferMode.UPLOAD:
                with self._connect() as connection:
                    expect_ok(
                        connection.run(f"mkdir -p $(dirname {dst})", warn=True).exited
                    )
                dst = f"{str(self.id)}:{dst}"
            case self.TransferMode.DOWNLOAD:
                Path(dst).parent.mkdir(parents=True, exist_ok=True)
                src = f"{str(self.id)}:{src}"
        ssh_options = ["StrictHostKeyChecking=no"]
        ssh_options_str = " ".join(f"-o {o}" for o in ssh_options)
        rsync_flags = [
            "--archive",
            "--progress",
            "--verbose",
            f'-e "ssh -p {self.__port} {ssh_options_str}"',
        ]
        cmd = f"rsync {' '.join(rsync_flags)} {src} {dst} 1>&2"
        result = invoke.run(cmd, warn=True)
        status = -1 if result is None else result.exited
        if status == EX_BASH_COMMAND_NOT_FOUND:
            eprint(
                "rsync is not installed locally or on the target. (Falling back on scp.)"
            )
            scp_flags = [
                "-P",
                str(self.__port),
                "-p",
                "-r",
                "-O",
            ]
            cmd = f"scp {' '.join(scp_flags)} {src} {dst} 1>&2"
            result = invoke.run(cmd, warn=True, pty=False)
        status = -1 if result is None else result.exited
        expect_ok(status)

    def clean_up(self: Self, job: Job) -> None:
        with self._connect() as connection:
            assert job.output
            expect_ok(connection.run(f"rm -rf {job.output}", warn=True).exited)

    def _connect(self: Self) -> Connection:
        connect_kwargs = dict(allow_agent=False, look_for_keys=False)
        ssh_config = ssh.get_config()
        target_ssh_config = ssh_config.lookup(self.id)
        host = (
            target_ssh_config["hostname"] if "hostname" in target_ssh_config else None
        )
        if host != self.__host:
            eprint(
                f"Warning: HostName missmatch for {self.id}:", host, "!=", self.__host
            )
        if self.__port != ssh.DEFAULT_PORT and (
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
    ) -> None:
        raise NotImplementedError()

    def execute(self: Self, job: Job) -> None:
        with self._connect() as connection:
            assert job.output
            expect_ok(connection.run(f"mkdir -p {job.output}", warn=True).exited)
            env = dict(
                MS_ARRAY_ID=job.array_id,
                MS_ARRAY_IDX=job.array_idx,
                MS_INPUT=f"~/{job.input}",
                MS_OUTPUT=f"~/{job.output}",
            )
            for module in job.spec.required_modules:
                module = self.__module_map[module]
                expect_ok(connection.run(f"ml {module}", warn=True).exited)
            with connection.cd(job.output):
                self._execute_batch_system(connection, job.spec, env)


class DirectTarget(Target):
    def __init__(self: Self, **kwargs: Any) -> None:
        if "nodes" in kwargs and kwargs["nodes"] != 1:
            eprint(
                f"Target {self.id} of type {self.__class__.__name__} does not support multiple nodes"
            )
        super().__init__(**kwargs | {"nodes": 1})

    @staticmethod
    def get_batch_system() -> str:
        return "none"

    def _execute_batch_system(
        self: Self, connection: Connection, job_spec: Spec, env: Dict[str, Any] = {}
    ) -> None:
        argv = [job_spec.executable]
        expect_ok(connection.run(" ".join(argv), warn=True, env=env).exited)


class SlurmTarget(Target):
    def __init__(self: Self, partition: str | None = None, **kwargs: Any) -> None:
        self.partition = partition
        super().__init__(**kwargs)

    @staticmethod
    def get_batch_system() -> str:
        return "slurm"

    def _execute_batch_system(
        self: Self, connection: Connection, job_spec: Spec, env: Dict[str, Any] = {}
    ) -> None:
        argv = ["srun"]
        if self.partition:
            argv.append(f"--partition={self.partition}")
        argv.append(f"--time={seconds_to_time(job_spec.time)}")
        argv.append(job_spec.executable)
        expect_ok(connection.run(" ".join(argv), warn=True, env=env).exited)


class TargetFactory:
    @staticmethod
    def create(batch_system: str, **kwargs: Any) -> Target:
        target_classes = [SlurmTarget, DirectTarget]
        target_class: abc.ABCMeta = {
            cls.get_batch_system(): cls
            for cls in target_classes
            if issubclass(cls, Target)
        }[batch_system]
        assert issubclass(target_class, Target)
        return target_class(**kwargs)
