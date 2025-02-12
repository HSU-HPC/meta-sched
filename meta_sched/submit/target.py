import abc
import uuid
from typing import Self

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

    def _connect(self: Self) -> Connection:
        connect_kwargs = dict(allow_agent=False, look_for_keys=False)
        config = Config(ssh_config=ssh.get_config())
        return Connection(str(self.id), config=config, connect_kwargs=connect_kwargs)

    def execute(self: Self, job_spec: JobSpec) -> None:
        raise NotImplementedError()


class SlurmTarget(Target):
    def execute(self: Self, job_spec: JobSpec) -> None:
        with self._connect() as connection:
            # TODO execution of job
            connection.run("echo Hello from $(hostname)!")
