"""Module containing classes for managing data transfer and command execution for target systems."""

import abc
import enum
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
    """
    Base class representing a target system for job execution.
    """

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
        """
        Create a new instance representing a target system.

        Parameters
        ----------
        id : str
            The unique identifier of the target also used as its SSH alias
        host : str
            The hostname used to connect to the target
        nodes : int
            The number of compute nodes associated with this target
        cores_per_node : int
            The number of CPU cores per compute node for this target
        port : int
            The port used to connect to the target (defaults to default SSH port)
        max_time : str
            The maximum time for which a job may run on this target formatted as "d-hh:MM:ss"
        max_nodes : int
            The maximum number of compute nodes which may be allocated to a job
        source_scripts : List[str]
            A list of files which should be sourced after connecting to the target before running any commands
        module_map : Dict[str, str]
            A mapping of abstract environment modules such as "MPI" to concrete ones such as "mpi/openmpi",
            which should be loaded after connecting to the target
        **kwargs : Any
            Additional arguments which are not used
        """
        if self.__class__ == Target:
            raise NotImplementedError()
        self.__dict = locals() | kwargs
        del self.__dict["self"]
        del self.__dict["kwargs"]
        self.__id = id
        self.__host = host
        self.__port = port
        self._nodes = nodes
        self._cores_per_node = cores_per_node
        self.__max_time = None if max_time is None else time_to_seconds(max_time)
        self.__max_nodes = max_nodes
        self.__source_scripts = source_scripts
        self.__module_map = module_map
        if len(kwargs) > 0:
            eprint(__file__, "Got unused kwargs", kwargs)  # TODO

    def to_dict(self: Self) -> Dict[str, Any]:
        """
        Create a dictionary representation of the target.

        Returns
        -------
        Dict[str, Any]
            The dictionary representing the target
        """
        return self.__dict | {"batch_system": self.get_batch_system()}

    @property
    def id(self: Self) -> str:
        """
        Get the identifier of the target which is also used as its SSH alias.

        Returns
        -------
        str
            The identifier of the target
        """
        return self.__id

    @property
    def host(self: Self) -> str:
        """
        Get the hostname of the target.

        Returns
        -------
        str
            The hostname of the target
        """
        return self.__host

    @staticmethod
    def get_batch_system() -> str:
        """
        Get the batch system type of the target.

        Returns
        -------
        str
            The batch system type of the target

        Raises
        ------
        NotImplementedError
            Must be implemented by the concrete target class
        """
        raise NotImplementedError()

    @property
    def has_user(self: Self) -> bool:
        """
        Check if the current user can use this target system.

        Returns
        -------
        bool
            True, if the the current user has SSH credentials for this target
        """
        config = ssh.get_config()
        return str(self.id) in config.get_hostnames() and "user" in config.lookup(
            str(self.id)
        )

    class TransferMode(enum.Enum):
        """
        Type (direction) of data transfer between submit host and target.
        """

        UPLOAD = 0
        DOWNLOAD = 1

    def is_suitable(self: Self, job_spec: Spec) -> Tuple[bool, str]:
        """
        Check if the target is suitable for executing a specific job.

        Parameters
        ----------
        job_spec : Spec
            The specification of the job considered for execution on the target

        Returns
        -------
        Tuple[bool, str]
            Suitability of the target for executing the job and reason
        """
        if not self.has_user:
            return False, "Credentials missing"
        if self.__max_time is not None and job_spec.seconds > self.__max_time:
            return False, "Too much time required"
        max_nodes = (
            min(self._nodes, self.__max_nodes) if self.__max_nodes else self._nodes
        )
        if job_spec.nodes > max_nodes:
            return False, "Too many nodes required"
        cores = job_spec.ranks * job_spec.cores_per_rank
        if cores > self._cores_per_node:
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
        """
        Transfer data between the submit host and the target

        Parameters
        ----------
        src : str | PathLike[Any]
            Source directory
        std : str | PathLike[Any]
            Destination directory
        mode : TransferMode
            Direction in which data is transferred between submit host and target
        """
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
        """
        Clean up job related files on the target.

        Parameters
        ----------
        job : Job
            The job of which related files should be deleted on the target
        """
        with self._connect() as connection:
            expect_ok(connection.run(f"rm -rf {job.remote_output}", warn=True).exited)

    def _connect(self: Self) -> Connection:
        """
        Connect to the target over SSH.

        Returns
        -------
        Connection
            The paramiko SSH connection

        Raises
        ------
        RuntimeError
            The port must match the port in the corresponding SSH configuration entry
        """
        connect_kwargs = dict(allow_agent=False, look_for_keys=False)
        ssh_config = ssh.get_config()
        target_ssh_config = ssh_config.lookup(self.id)
        host = (
            target_ssh_config["hostname"] if "hostname" in target_ssh_config else None
        )
        if host != self.__host:
            eprint(
                f"Warning: HostName mismatch for {self.id}:", host, "!=", self.__host
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
        """
        Execute the job using the batch system on the target.

        Parameters
        ----------
        connection : Connection
            The paramiko SSH connection object
        job : Job
            The job to be executed on the target
        env : Dict[str, Any]
            Optional environment variables to be injected on the target before executing the job

        Raises
        ------
        NotImplementedError
            The execution of the job must be implemented by the concrete target class
        """
        raise NotImplementedError()

    def _prefix_cmd(self: Self, cmd: str, modules: List[str] = []) -> str:
        """
        Prefix a shell command with commands to source target shell scripts and load environment modules.

        Parameters
        ----------
        cmd : str
            The command to be prefixed
        modules : List[str]
            Optional environment modules to be loaded before executing the command

        Returns
        -------
        str
            The prefixed command
        """
        specific_modules = [self.__module_map[m] for m in modules]
        cmd = " && ".join(
            [f"source {script}" for script in self.__source_scripts]
            + [f"module load {module}" for module in specific_modules]
            + [cmd]
        )
        return cmd

    @staticmethod
    def __get_env(job: Job) -> Dict[str, Any]:
        """
        Get the environment variables for a job to be set on the target.

        Parameters
        ----------
        job : Job
            The corresponding job

        Returns
        -------
        Dict[str, Any]
            Environment variables for the job to be set on the target
        """
        env = dict(
            MS_ARRAY_ID=job.array_id,
            MS_ARRAY_IDX=job.array_idx,
            MS_INPUT=f"~/{job.remote_input}",
            MS_OUTPUT=f"~/{job.remote_output}",
            TERM="dumb",  # See man "term(7)"
        )
        return env

    def setup(self: Self, job: Job) -> None:
        """
        Run the set up command of the job files on the target.

        Parameters
        ----------
        job : Job
            The job which to set up on the target
        """
        with self._connect() as connection:
            expect_ok(connection.run(f"mkdir -p {job.remote_output}", warn=True).exited)
            with connection.cd(job.remote_output):
                if job.spec.cmd_setup:
                    cmd = self._prefix_cmd(
                        job.spec.cmd_setup, job.spec.required_modules
                    )
                    result = connection.run(cmd, warn=True, env=Target.__get_env(job))
                    expect_ok(result.exited)

    def execute(self: Self, job: Job) -> None:
        """
        Execute the job on the target.

        Parameters
        ----------
        job : Job
            The job which to execute on the target
        """
        with self._connect() as connection:
            expect_ok(connection.run(f"mkdir -p {job.remote_output}", warn=True).exited)
            with connection.cd(job.remote_output):
                self._execute_batch_system(connection, job, Target.__get_env(job))


class DirectTarget(Target):
    """
    Class for target without a batch system.
    (Jobs are executed directly on the remote shell.)
    """

    def __init__(self: Self, **kwargs: Any) -> None:
        """
        Create a new instance of a target for direct command execution.

        Parameters
        ----------
        **kwargs : Any
            Parameters to be passed to the parent constructor of the target
        """
        if "nodes" in kwargs and kwargs["nodes"] != 1:
            eprint(
                f"Target {self.id} of type {self.__class__.__name__} does not support multiple nodes"
            )
        super().__init__(**kwargs | {"nodes": 1})

    @staticmethod
    def get_batch_system() -> str:
        """
        Get the batch system type of the target.

        Returns
        -------
        str
            "none"
        """
        return "none"

    def _execute_batch_system(
        self: Self,
        connection: Connection,
        job: Job,
        env: Dict[str, Any] = {},
    ) -> None:
        """
        Execute the job directly on the target.

        Parameters
        ----------
        connection : Connection
            The paramiko SSH connection object
        job : Job
            The job to be executed on the target
        env : Dict[str, Any]
            Optional environment variables to be injected on the target before executing the job
        """
        job.set_status(JobStatus.Running(self.id))
        cmd = self._prefix_cmd(job.spec.cmd_main, job.spec.required_modules)
        expect_ok(connection.run(cmd, warn=True, env=env).exited)


class SlurmTarget(Target):
    """
    Class for target running the Slurm batch system.
    """

    def __init__(self: Self, partition: str | None = None, **kwargs: Any) -> None:
        """
        Create a new instance of a target for executing jobs through Slurm.

        Parameters
        ----------
        partition : str | None
            Optional name of the Slurm partition to be used when executing jobs
        **kwargs : Any
            Parameters to be passed to the parent constructor of the target
        """
        self.partition = partition
        super().__init__(**kwargs)

    @staticmethod
    def get_batch_system() -> str:
        """
        Get the batch system type of the target.

        Returns
        -------
        str
            "slurm"
        """
        return "slurm"

    def _execute_batch_system(
        self: Self,
        connection: Connection,
        job: Job,
        env: Dict[str, Any] = {},
    ) -> None:
        """
        Execute the job on the target using Slurm.

        Parameters
        ----------
        connection : Connection
            The paramiko SSH connection object
        job : Job
            The job to be executed on the target
        env : Dict[str, Any]
            Optional environment variables to be injected on the target before executing the job
        """
        eprint("--- a. Creating and watching output/error files ---")
        # TODO consider NOT streaming the output/error files
        output_files = dict(output=sys.stdout, error=sys.stderr)
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
        if job.spec.exclusive:
            argv.append("--exclusive")
            # FIXME: What about using multiple tasks for MPI?
            argv.append(f"--cpus-per-task={self._cores_per_node}")
        argv.append(f"--time={seconds_to_time(job.spec.seconds)}")
        argv.append("--output=output")
        argv.append("--error=error")
        argv.append(f"--wrap='{job.spec.cmd_main}'")
        argv.append(f"--job-name={job.spec.name}")
        cmd = self._prefix_cmd(" ".join(argv), job.spec.required_modules)
        result = connection.run(cmd, warn=True, env=env, out_stream=sys.stderr)
        expect_ok(result.exited)
        slurm_job_id = result.stdout.strip().split()[-1]

        backoff_count = 0
        interrupted_error: InterruptedError | None = None

        def sleep_or_cancel(seconds: float) -> None:
            """
            Sleep some time or, if receiving a SIGINT, cancel the Slurm job.

            Parameters
            ----------
            seconds : float
                The time to sleep for in seconds
            """
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
            if len(result.stdout.strip()) == 0 or result.stdout.strip() == "RUNNING":
                break  # Job no longer in queue or has started
            sleep_or_cancel(exponential_backoff(backoff_count))
            backoff_count += 1
        eprint("--- d. Awaiting job completion ---")
        if interrupted_error is None:
            backoff_count = 0
            job.set_status(JobStatus.Running(self.id))
            # Do not wait requested time in case job completes earlier
            # sleep_or_cancel(job.spec.seconds)
        exit_code = 0
        while True:
            result = connection.run(
                f"squeue -j {slurm_job_id} --noheader", warn=True, hide=True
            )
            if len(result.stdout.strip()) == 0:
                break  # Job no longer in queue
            sleep_or_cancel(exponential_backoff(backoff_count))
            backoff_count += 1
        eprint("--- e. Obtaining exit code and cleaning up output/error files ---")
        time.sleep(1)  # Wait a bit for the output/error to be received
        exit_code = -1
        result = connection.run(
            f'sacct -j {slurm_job_id} --format "State,ExitCode" --noheader',
            warn=True,
            hide=True,
        )
        try:
            expect_ok(result.exited)
            sacct_state, sacct_exit_code = result.stdout.splitlines()[0].split()
            exit_code = int(sacct_exit_code.split(":")[0])
        except Exception:
            eprint("Job completed, but could not determine exit code:")
        sys.stdout.flush()
        sys.stderr.flush()
        expect_ok(
            connection.run(f"rm -f {' '.join(output_files.keys())}", warn=True).exited
        )
        if interrupted_error is not None:
            raise interrupted_error
        expect_ok(exit_code)


class TargetFactory:
    """
    A class for creating instances of targets
    """

    @staticmethod
    def create(batch_system: str, **kwargs: Any) -> Target:
        """
        Create a new target instance

        Parameters
        ----------
        batch_system : str
            The type of target which should be created

        **kwargs : Any
            The parameters which should be passed to the constructor of the specific target

        Returns
        -------
        Target
            The new target instance
        """
        target_classes = [SlurmTarget, DirectTarget]
        target_class: abc.ABCMeta = {
            cls.get_batch_system(): cls
            for cls in target_classes
            if issubclass(cls, Target)
        }[batch_system]
        assert issubclass(target_class, Target)
        return target_class(**kwargs)
