import abc
import enum
import os
import sys
import time
from os import PathLike
from pathlib import Path
from typing import Any, Dict, List, Self, Tuple

import invoke
from fabric import Connection
from fabric.config import Config

from meta_sched.common import ssh
from meta_sched.common.job import Instance as Job
from meta_sched.common.job import Spec
from meta_sched.common.job import Status as JobStatus
from meta_sched.common.serialization import Serializable
from meta_sched.common.utils import (
    EX_BASH_COMMAND_NOT_FOUND,
    eprint,
    expect_ok,
    exponential_backoff,
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
        source_scripts: List[str] = [],
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
        self.__source_scripts = source_scripts
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
        if self.__max_time is not None and job_spec.seconds > self.__max_time:
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
            # TODO this may cause issues when another job is currently reading existing input files!
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
            # scp uses src = A:/path/to/dir/* dst = B:/path/to/dir so dir is in path/to/
            dst = Path(dst) / Path(src).name
            src = f"{str(src)}/*"
            with self._connect() as connection:
                remote_dst = str(dst).split(":")[-1]
                expect_ok(connection.run(f"mkdir -p {remote_dst}", warn=True).exited)
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
        connection = Connection(
            str(self.id), config=config, connect_kwargs=connect_kwargs
        )
        return connection

    def _execute_batch_system(
        self: Self,
        connection: Connection,
        job: Job,
        env: Dict[str, Any] = {},
    ) -> None:
        raise NotImplementedError()

    def _prefix_cmd(self: Self, cmd: str, modules: List[str] = []) -> str:
        specific_modules = [self.__module_map[m] for m in modules]
        cmd = " && ".join(
            [f"source {script}" for script in self.__source_scripts]
            + [f"module load {module}" for module in specific_modules]
            + [cmd]
        )
        return cmd

    def execute(self: Self, job: Job) -> None:
        with self._connect() as connection:
            assert job.output
            expect_ok(connection.run(f"mkdir -p {job.output}", warn=True).exited)
            env = dict(
                MS_ARRAY_ID=job.array_id,
                MS_ARRAY_IDX=job.array_idx,
                MS_INPUT=f"~/{job.input}",
                MS_OUTPUT=f"~/{job.output}",
                TERM="dumb",  # See man "term(7)"
            )
            with connection.cd(job.output):
                if job.spec.cmd_setup:
                    cmd = self._prefix_cmd(
                        job.spec.cmd_setup, job.spec.required_modules
                    )
                    result = connection.run(cmd, warn=True, env=env)
                    expect_ok(result.exited)
                self._execute_batch_system(connection, job, env)


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
        self: Self,
        connection: Connection,
        job: Job,
        env: Dict[str, Any] = {},
    ) -> None:
        job.set_status(JobStatus.Running(self.id))
        cmd = self._prefix_cmd(job.spec.cmd_main, job.spec.required_modules)
        expect_ok(connection.run(cmd, warn=True, env=env).exited)


class SlurmTarget(Target):
    def __init__(self: Self, partition: str | None = None, **kwargs: Any) -> None:
        self.partition = partition
        super().__init__(**kwargs)

    @staticmethod
    def get_batch_system() -> str:
        return "slurm"

    def _execute_batch_system(
        self: Self,
        connection: Connection,
        job: Job,
        env: Dict[str, Any] = {},
    ) -> None:
        eprint("--- a. Creating and watching output/error files ---")
        output_files = dict(stdout=sys.stdout, stderr=sys.stderr)
        for k, v in output_files.items():
            connection.run(
                f"touch {k} && tail -f {k} &",
                warn=True,
                asynchronous=True,
                out_stream=v,
            )
        eprint("--- b. Submitting job ---")
        argv = ["sbatch"]
        if self.partition:
            argv.append(f"--partition={self.partition}")
        argv.append(f"--time={seconds_to_time(job.spec.seconds)}")
        argv.append("--output=stdout")
        argv.append("--error=stderr")
        argv.append(f"--wrap='{job.spec.cmd_main}'")
        argv.append(f"--job-name={job.spec.name}")
        cmd = self._prefix_cmd(" ".join(argv), job.spec.required_modules)
        result = connection.run(cmd, warn=True, env=env, out_stream=sys.stderr)
        expect_ok(result.exited)
        slurm_job_id = result.stdout.strip().split()[-1]

        backoff_count = 0
        interrupted_error: InterruptedError | None = None

        def sleep_or_cancel(seconds: float) -> None:
            try:
                time.sleep(seconds)
            except InterruptedError as e:
                nonlocal backoff_count, interrupted_error
                if interrupted_error is not None:
                    eprint("Job was already canceled. (Nothing to do.)")
                    return
                # Defer handling until Slurm job has been canceled completely
                eprint(f"Canceling slurm job {slurm_job_id}.")
                expect_ok(connection.run(f"scancel {slurm_job_id}", warn=True).exited)
                job.set_status(JobStatus.Canceled())
                backoff_count = 0
                interrupted_error = e

        eprint("--- c. Awaiting job start ---")
        while True:
            result = connection.run(
                f"squeue -j {slurm_job_id} --format %T --noheader", warn=True, hide=True
            )
            if result.exited != os.EX_OK or result.stdout.strip() == "RUNNING":
                break  # Job no longer in queue has started
            sleep_or_cancel(exponential_backoff(backoff_count))
            backoff_count += 1
        eprint("--- d. Awaiting job completion ---")
        if interrupted_error is None:
            backoff_count = 0
            job.set_status(JobStatus.Running(self.id))
            sleep_or_cancel(job.spec.seconds)
        exit_code = 0
        while True:
            result = connection.run(
                f"squeue -j {slurm_job_id} --noheader", warn=True, hide=True
            )
            if result.exited != os.EX_OK or len(result.stdout.strip()) == 0:
                break  # Job no longer in queue
            sleep_or_cancel(exponential_backoff(backoff_count))
            backoff_count += 1
        eprint("--- e. Obtaining exit code and cleaning up output/error files ---")
        time.sleep(1)  # Wait a bit for the output/error to be received
        sys.stdout.flush()
        sys.stderr.flush()
        result = connection.run(
            f'sacct -j {slurm_job_id} --format "State,ExitCode" --noheader',
            warn=True,
            hide=True,
        )
        expect_ok(result.exited)
        sacct_state, sacct_exit_code = result.stdout.splitlines()[0].split()
        exit_code = int(sacct_exit_code.split(":")[0])
        expect_ok(
            connection.run(f"rm -f {' '.join(output_files.keys())}", warn=True).exited
        )
        if interrupted_error is not None:
            raise interrupted_error
        expect_ok(exit_code)


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
