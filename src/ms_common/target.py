"""Module containing classes for managing data transfer and command execution for target systems."""

import abc
import enum
import sys
import time
from os import PathLike
from pathlib import Path
from typing import Any, Dict, List, Self, Tuple

# FIXME Fabric related code should not be in a common module
import invoke
from fabric import Connection # type: ignore[attr-defined]
from fabric.config import Config
from pydantic import BaseModel, model_validator
from ms_common import ssh
from ms_common.job import Instance as Job
from ms_common.job import Spec
from ms_common.job import Status as JobStatus
from ms_common.utils import (EX_BASH_COMMAND_NOT_FOUND,
                                     enforce_type_annotations, eprint,
                                     expect_ok, exponential_backoff,
                                     seconds_to_time, time_to_seconds)

# TODO base on pydantic's BaseModel instead (see job.Spec)
class Target(BaseModel):
    """
    Base class representing a target system for job execution.

    Attributes
    ----------
    id : str
        The unique identifier of the target also used as its SSH alias
    batch_system : str
        The batch system used by the target, e.g. "slurm", "pbs", "none" (default, direct execution)
    queue : str | None
        The name of the queue/partition used by the target (if applicable, e.g. for Slurm or PBS)
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
    tags : List[str]
        A list of tags for the target such as "gpu", "x86", "green", etc.
    """
    id: str
    batch_system: str = "none"
    queue: str | None = None
    host: str
    nodes: int
    cores_per_node: int
    port: int = ssh.DEFAULT_PORT
    max_time: str | None = None
    max_nodes: int | None = None
    source_scripts: List[str] = []
    module_map: Dict[str, str] = {}
    tags: List[str] = []

    @model_validator(mode="after")
    def validate_attributes(cls, target: Any) -> Any:
        """
        Validates an adjusts (!) target attributes. (Is idempotent.)
        """
        if target.batch_system not in ["none", "slurm", "pbs"]:
            raise ValueError(
                f"Invalid batch system {target.batch_system} for target {target.id}"
            )
        if target.batch_system == "none":
            if target.nodes != 1 or target.max_nodes is not None:
                raise ValueError(
                    f"Target {target.id} of type {target.__class__.__name__} does not support multiple nodes"
                )
            if target.queue is not None:
                eprint(
                    f"Warning: Target {target.id} of type {target.__class__.__name__} does not support queues. (Ignoring.)"
                )
            if target.max_time is not None:
                eprint(
                    f"Warning: Target {target.id} of type {target.__class__.__name__} does not support maximum job time. (Ignoring.)"
                )
        return target

    def _create_oe_files(self: Self, connection: Connection, stream_contents: bool) -> Tuple[str, str]:
        """
        Create job output and error files and optionally stream their contents as they are appended.

        Parameters
        ----------
        connection : Connection
            The connection over which to create the files
        stream_contents : bool
            If true, the contents of the files will be streamed to stdout/stderr as they are appended
        """
        # TODO use random filenames and return them for use in the job submission/cleanup
        output_files = dict(output=sys.stdout, error=sys.stderr)
        for k, v in output_files.items():
            connection.run(
                f"touch {k}",
                warn=True,
                asynchronous=True,
                out_stream=v,
            )
            if stream_contents:
                connection.run(
                    f"tail -f {k} &",
                    warn=True,
                    asynchronous=True,
                    out_stream=v,
                )
        oe = tuple(output_files.keys())
        assert len(oe) == 2
        return oe

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
        if self.max_time is not None and job_spec.seconds > time_to_seconds(self.max_time):
            return False, "Too much time required"
        max_nodes = (
            min(self.nodes, self.max_nodes) if self.max_nodes else self.nodes
        )
        if job_spec.nodes > max_nodes:
            return False, "Too many nodes required"
        cores_per_node = job_spec.ranks_per_node * job_spec.cores_per_rank
        if cores_per_node > self.cores_per_node:
            return False, "Too many cores required"
        for t in job_spec.required_tags:
            if t not in self.tags:
                return False, f'Required tag "{t}" missing'
        for m in job_spec.required_modules:
            if m not in self.module_map:
                return False, f'Required module "{m}" missing'
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
            f'-e "ssh -p {self.port} {ssh_options_str}"',
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
                str(self.port),
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

    def _connect(self: Self, timeout: float = 5) -> Connection:
        """
        Connect to the target over SSH.

        Parameters
        ----------
        timeout : float
            The connection timeout in seconds

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
        if host != self.host:
            eprint(
                f"Warning: HostName mismatch for {self.id}:", host, "!=", self.host
            )
        if self.port != ssh.DEFAULT_PORT and (
            "port" not in target_ssh_config
            or int(target_ssh_config["port"]) != self.port
        ):
            raise RuntimeError(
                f"Cannot connect to target {self.id} (Non-default Port missing in SSH config)"
            )
        config = Config(ssh_config=ssh_config) # type: ignore[no-untyped-call]
        connection = Connection( # type: ignore[no-untyped-call]
            str(self.id),
            config=config,
            connect_kwargs=connect_kwargs,
            connect_timeout=timeout,
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
        """
        match self.batch_system:
            case "none":
                self._execute_batch_system_none(connection, job, env)
            case "slurm":
                self._execute_batch_system_slurm(connection, job, env)
            case "pbs":
                self._execute_batch_system_pbs(connection, job, env)
            case _:
                raise ValueError(
                    f"Unsupported batch system {self.batch_system} for target {self.id}"
                )

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
        specific_modules = [self.module_map[m] for m in modules]
        cmd = " && ".join(
            [f"source {script}" for script in self.source_scripts]
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


    def _execute_batch_system_none(
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


    def _execute_batch_system_slurm(
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
        output_files = self._create_oe_files(connection, True)
        eprint("--- b. Submitting job ---")
        argv = ["sbatch"]
        if self.queue:
            argv.append(f"--partition={self.queue}")
        if job.spec.exclusive:
            argv.append("--exclusive")
        argv.append(f"--nodes={job.spec.nodes}")
        argv.append(f"--ntasks-per-node={job.spec.ranks_per_node}")
        argv.append(f"--cpus-per-task={job.spec.cores_per_rank}")
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
        sacct_cmd = f'sacct -j {slurm_job_id} --format "State,ExitCode" --noheader'
        result = connection.run(
            sacct_cmd,
            warn=True,
            hide=True,
        )
        try:
            expect_ok(result.exited)
            sacct_state, sacct_exit_code = result.stdout.splitlines()[0].split()
            exit_code = int(sacct_exit_code.split(":")[0])
        except Exception:
            eprint(
                f"Job completed, but could not determine exit code using {sacct_cmd}:"
            )
        sys.stdout.flush()
        sys.stderr.flush()
        expect_ok(
            connection.run(f"rm -f {' '.join(output_files)}", warn=True).exited
        )
        if interrupted_error is not None:
            raise interrupted_error
        expect_ok(exit_code)

    def _execute_batch_system_pbs(
        self: Self,
        connection: Connection,
        job: Job,
        env: Dict[str, Any] = {},
    ) -> None:
        """
        Execute the job on the target using PBS.

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
        output_files = self._create_oe_files(connection, True)
        eprint("--- b. Submitting job ---")
        argv = ["qsub"]
        if self.queue:
            argv += ["-q", self.queue]
        if job.spec.exclusive:
            argv += ["-l", "place=excl"]
        cores_per_node = job.spec.cores_per_rank * job.spec.ranks_per_node
        argv += [
            "-l",
            f"select={job.spec.nodes}:ncpus={cores_per_node}:mpiprocs={job.spec.ranks_per_node}:ompthreads={job.spec.cores_per_rank}",
        ]
        argv += ["-l", f"walltime={seconds_to_time(job.spec.seconds, False)}"]
        argv += ["-o", "output"]
        argv += ["-e", "error"]
        argv += ["-koed"]  # Stream output files from execution host
        argv += ["-N", job.spec.name]
        # argv += ["-v", ",".join(f"{k}={v}" for k,v in env.items())]
        argv += ["-V"]  # Just export all environment variables instead
        # For non-script jobs, the directory is always $HOME
        argv += [
            "--",
            "$(which sh)",
            "-c",
            f"'cd {job.remote_output} && {job.spec.cmd_main}'",
        ]
        cmd = self._prefix_cmd(" ".join(argv), job.spec.required_modules)
        result = connection.run(cmd, warn=True, env=env, out_stream=sys.stderr)
        expect_ok(result.exited)
        pbs_job_id = result.stdout.strip()

        backoff_count = 0
        interrupted_error: InterruptedError | None = None

        def sleep_or_cancel(seconds: float) -> None:
            """
            Sleep some time or, if receiving a SIGINT, cancel the PBS job.

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
                # Defer handling until PBS job has been canceled completely
                eprint(f"Canceling PBS job {pbs_job_id}.")
                expect_ok(connection.run(f"qdel {pbs_job_id}", warn=True).exited)
                job.set_status(JobStatus.Canceled())
                backoff_count = 0
                interrupted_error = e

        eprint("--- c. Awaiting job start ---")
        time.sleep(1)
        while True:
            result = connection.run(f"qstat {pbs_job_id}", warn=True, hide=True)
            if (
                len(result.stdout.strip()) == 0
                or result.stdout.splitlines()[-1].strip().split()[-2] == "R"
            ):
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
            result = connection.run(f"qstat {pbs_job_id}", warn=True, hide=True)
            if len(result.stdout.strip()) == 0:
                break  # Job no longer in queue
            sleep_or_cancel(exponential_backoff(backoff_count))
            backoff_count += 1
        eprint("--- e. Obtaining exit code and cleaning up output/error files ---")
        time.sleep(1)  # Wait a bit for the output/error to be received
        exit_code = -1
        qstat_cmd = f"qstat {pbs_job_id} -f -x"
        result = connection.run(
            qstat_cmd,
            warn=True,
            hide=True,
        )
        try:
            expect_ok(result.exited)
            has_exit_code = False
            for line in result.stdout.lower().splitlines():
                line = line.strip()
                if line.startswith("exit_status ="):
                    exit_code = int(line.split("=")[1].strip())
                    has_exit_code = True
                    break
            assert has_exit_code
        except Exception:
            eprint(
                f"Job completed, but could not determine exit code using {qstat_cmd}:"
            )
        sys.stdout.flush()
        sys.stderr.flush()
        expect_ok(
            connection.run(f"rm -f {' '.join(output_files)}", warn=True).exited
        )
        if interrupted_error is not None:
            raise interrupted_error
        expect_ok(exit_code)
