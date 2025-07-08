"""Module containing code for executing jobs on a remote batch system."""

import abc
import enum
import io
import sys
import time
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Any, Dict, List, Optional, Self, Tuple

import invoke
import pandas as pd
from fabric import Connection  # type: ignore[attr-defined]
from fabric.config import Config
from ms_common import utils
from ms_common.schemas import Target, TargetStatus
from ms_common.utils import (DEFAULT_SSH_PORT, EX_BASH_COMMAND_NOT_FOUND,
                             eprint, expect_ok, exponential_backoff,
                             seconds_to_time, time_to_seconds)

from ms_client import ssh
from ms_client.job import Instance as Job


class RemoteTarget:
    """
    Class for transferring data to and from and executing commands on a remote target.
    """

    _SENTINEL = object()

    def __init__(self, sentinel: object, target: Target) -> None:
        """
        Create a new object representing a remote target for data transfer and command/job execution.

        Parameters
        ----------
        target : Target
            The target of the
        """
        if sentinel != RemoteTarget._SENTINEL:
            raise RuntimeError(
                "A remote target instance cannot be created directly. (Use factory method RemoteTarget.from_target(target) instead!)"
            )
        self._target = target

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
        target_ssh_config = ssh_config.lookup(self._target.id)
        host = (
            target_ssh_config["hostname"] if "hostname" in target_ssh_config else None
        )
        if host != self._target.host:
            eprint(
                f"Warning: HostName mismatch for {self._target.id}:",
                host,
                "!=",
                self._target.host,
            )
        if self._target.port != DEFAULT_SSH_PORT and (
            "port" not in target_ssh_config
            or int(target_ssh_config["port"]) != self._target.port
        ):
            raise RuntimeError(
                f"Cannot connect to target {self._target.id} (Non-default Port missing in SSH config)"
            )
        config = Config(ssh_config=ssh_config)  # type: ignore[no-untyped-call]
        connection = Connection(  # type: ignore[no-untyped-call]
            str(self._target.id),
            config=config,
            connect_kwargs=connect_kwargs,
            connect_timeout=timeout,
        )
        return connection

    class TransferMode(enum.Enum):
        """
        Type (direction) of data transfer between submit host and target.
        """

        UPLOAD = 0
        DOWNLOAD = 1

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
                dst = f"{str(self._target.id)}:{dst}"
            case self.TransferMode.DOWNLOAD:
                Path(dst).parent.mkdir(parents=True, exist_ok=True)
                src = f"{str(self._target.id)}:{src}"
        ssh_options = ["StrictHostKeyChecking=no"]
        ssh_options_str = " ".join(f"-o {o}" for o in ssh_options)
        rsync_flags = [
            "--archive",
            "--progress",
            "--verbose",
            f'-e "ssh -p {self._target.port} {ssh_options_str}"',
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
                str(self._target.port),
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

    def _create_oe_files(
        self: Self, connection: Connection, stream_contents: bool
    ) -> Tuple[str, str]:
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
        specific_modules = [self._target.module_map[m] for m in modules]
        cmd = " && ".join(
            [f". {script}" for script in self._target.source_scripts]
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
                    result = connection.run(
                        cmd, warn=True, env=RemoteTarget.__get_env(job)
                    )
                    expect_ok(result.exited)

    @dataclass
    class JobExecutionCallbacks:
        """
        Callbacks for job execution on the target.
        Attributes
        ----------
        on_start : Any
            Callback to be called when the job starts executing on the target
        on_end : Any
            Callback to be called when the job ends executing on the target
        """

        on_start: Any = lambda: None
        on_end: Any = lambda: None

    def execute(
        self: Self, job: Job, callbacks: JobExecutionCallbacks = JobExecutionCallbacks()
    ) -> None:
        """
        Execute the job on the target.

        Parameters
        ----------
        job : Job
            The job which to execute on the target
        callbacks : JobExecutionCallbacks
            Callback functions for job state changes
        """
        # TODO avoid long living connection -> pass in a function to obtain a new callable "run_remote(...)" (with cd(job.remote_output) and command prefixing)
        with self._connect() as connection:
            expect_ok(connection.run(f"mkdir -p {job.remote_output}", warn=True).exited)
            with connection.cd(job.remote_output):
                self._execute_batch_system(
                    connection, job, callbacks, RemoteTarget.__get_env(job)
                )

    @classmethod
    def from_target(cls, target: Target) -> "RemoteTarget":
        """
        Create an instance of the corresponding child class for a given target.

        Parameters
        ----------
        target : Target
            The target for which to create an instance of RemoteTarget

        Returns
        -------
        RemoteTarget
            An instance of the child class matching the batch system of the target
        """
        match target.batch_system:
            case "slurm":
                return SlurmRemoteTarget(cls._SENTINEL, target)
            case "pbs":
                return PBSRemoteTarget(cls._SENTINEL, target)
            case "none":
                return DirectExecutionRemoteTarget(cls._SENTINEL, target)
            case _:
                raise ValueError(f'Unknown batch system "{target.batch_system}"')

    @abc.abstractmethod
    def _execute_batch_system(
        self: Self,
        connection: Connection,
        job: Job,
        callbacks: JobExecutionCallbacks,
        env: Dict[str, Any] = {},
    ) -> None:
        """
        Execute the job on the remote target.

        Parameters
        ----------
        connection : Connection
            The paramiko SSH connection object
        job : Job
            The job to be executed on the target
        callbacks : JobExecutionCallbacks
            Callback functions for job state changes
        env : Dict[str, Any]
            Optional environment variables to be injected on the target before executing the job

        Raises
        ------
        NotImplementedError
            Must be implemented by the concrete remote target
        """
        raise NotImplementedError()

    def get_status(self: Self) -> TargetStatus:
        """
        Get the status of the remote target.

        Returns
        -------
        TargetStatus
            The status of the remote target

        Raises
        ------
        NotImplementedError
            Must be implemented by the concrete remote target
        """
        raise NotImplementedError()


class SlurmRemoteTarget(RemoteTarget):
    """RemoteTarget implementation for a Slurm system."""

    def _execute_batch_system(
        self: Self,
        connection: Connection,
        job: Job,
        callbacks: RemoteTarget.JobExecutionCallbacks,
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
        callbacks : RemoteTarget.JobExecutionCallbacks
            Callback functions for job state changes
        env : Dict[str, Any]
            Optional environment variables to be injected on the target before executing the job
        """
        eprint("--- a. Creating and watching output/error files ---")
        # TODO consider NOT streaming the output/error files (requires long living connection)
        output_files = self._create_oe_files(connection, True)
        eprint("--- b. Submitting job ---")
        argv = ["sbatch"]
        if self._target.queue:
            argv.append(f"--partition={self._target.queue}")
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
        interrupted_error: Optional[InterruptedError] = None

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
                expect_ok(
                    connection.run(
                        self._prefix_cmd(f"scancel {slurm_job_id}"), warn=True
                    ).exited
                )
                backoff_count = 0
                interrupted_error = e

        eprint("--- c. Awaiting job start ---")
        time.sleep(1)
        cmd_get_slurm_job_state = self._prefix_cmd(
            f"squeue -j {slurm_job_id} --format %T --noheader"
        )
        while True:
            output = connection.run(
                cmd_get_slurm_job_state, warn=True, hide=True
            ).stdout.strip()
            if len(output) == 0 or output == "RUNNING":
                break  # Job no longer in queue or has started
            sleep_or_cancel(exponential_backoff(backoff_count))
            backoff_count += 1
        cmd_job_timestamp = self._prefix_cmd(
            "sacct -j SLURM_JOB_ID --noheader --format=FORMAT | head -n 1 | awk '{print $1}' | xargs -I{} date -d {} +%s"
        )
        timestamp_start = None
        try:
            timestamp_start = int(
                connection.run(
                    cmd_job_timestamp.replace("FORMAT", "start").replace(
                        "SLURM_JOB_ID", slurm_job_id
                    ),
                    warn=True,
                    hide=True,
                ).stdout.strip()
            )
        except Exception:
            pass
        finally:
            callbacks.on_start(timestamp_start)
        eprint("--- d. Awaiting job completion ---")
        if interrupted_error is None:
            backoff_count = 0
            # Do not wait requested time in case job completes earlier
            # sleep_or_cancel(job.spec.seconds)
        exit_code = 0
        while True:
            output = connection.run(
                cmd_get_slurm_job_state, warn=True, hide=True
            ).stdout.strip()
            if len(output) == 0:
                break  # Job no longer in queue
            sleep_or_cancel(exponential_backoff(backoff_count))
            backoff_count += 1
        timestamp_end = None
        try:
            timestamp_end = int(
                connection.run(
                    cmd_job_timestamp.replace("FORMAT", "end").replace(
                        "SLURM_JOB_ID", slurm_job_id
                    ),
                    warn=True,
                    hide=True,
                ).stdout.strip()
            )
        except Exception:
            pass
        finally:
            callbacks.on_end(timestamp_end)
        eprint("--- e. Obtaining exit code and cleaning up output/error files ---")
        time.sleep(1)  # Wait a bit for the output/error to be received
        exit_code = -1
        sacct_cmd = f'sacct -j {slurm_job_id} --format "State,ExitCode" --noheader'
        result = connection.run(
            self._prefix_cmd(sacct_cmd),
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
        expect_ok(connection.run(f"rm -f {' '.join(output_files)}", warn=True).exited)
        if interrupted_error is not None:
            raise interrupted_error
        expect_ok(exit_code)

    def get_status(self: Self) -> TargetStatus:
        """
        Get the status of the remote Slurm target.

        Returns
        -------
        TargetStatus
            The status of the remote target
        """
        with self._connect() as connection:
            # Get the job states
            squeue_format = "%D,%l,%T,%M"  # nodes, time limit, state, time
            cmd = self._prefix_cmd(
                f"squeue --partition {self._target.queue} --format '{squeue_format}'"
            )
            output = connection.run(cmd, warn=True, hide=True).stdout.strip()
            df = pd.read_csv(io.StringIO(output.lower()))
            df["time_limit"] = df["time_limit"].apply(lambda s: time_to_seconds(s))
            df["time"] = df["time"].apply(lambda s: time_to_seconds(s))
            df["is_using_nodes"] = df["state"].apply(
                lambda s: s
                in [
                    # https://slurm.schedmd.com/job_state_codes.html
                    # "completing",
                    "configuring",
                    "power_up_nodes",
                    # "signaling",
                    "running",
                ]
            )
            df["time_remaining"] = df["time_limit"] - df["time"]
            records = df[
                ["nodes", "time_limit", "is_using_nodes", "time_remaining"]
            ].to_dict("records")  # pyright: ignore[reportCallIssue]
            # Get the node states
            cmd = self._prefix_cmd(
                f"sinfo --partition {self._target.queue} -N --format '%t' --noheader"
            )
            nodes_state = (
                connection.run(cmd, warn=True, hide=True).stdout.strip().splitlines()
            )
            node_states = dict(
                nodes_in_use=0,
                nodes_unavailable=0,
                nodes_available=0,
            )
            for node_state in nodes_state:
                # https://slurm.schedmd.com/sinfo.html#SECTION_NODE-STATE-CODES
                if node_state.startswith("alloc"):
                    node_states["nodes_in_use"] += 1
                elif node_state.startswith("idle"):
                    node_states["nodes_available"] += 1
                else:
                    node_states["nodes_unavailable"] += 1
            assert sum(node_states.values()) == len(nodes_state)
            return TargetStatus.model_validate(
                node_states | {"timestamp": int(time.time()), "jobs_status": records}
            )


class PBSRemoteTarget(RemoteTarget):
    """RemoteTarget implementation for a PBS Pro/OpenPBS system."""

    def _execute_batch_system(
        self: Self,
        connection: Connection,
        job: Job,
        callbacks: RemoteTarget.JobExecutionCallbacks,
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
        if self._target.queue:
            argv += ["-q", self._target.queue]
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
            "$(command -v sh)",
            "-c",
            f"'cd {job.remote_output} && {job.spec.cmd_main}'",
        ]
        cmd = self._prefix_cmd(" ".join(argv), job.spec.required_modules)
        result = connection.run(cmd, warn=True, env=env, out_stream=sys.stderr)
        expect_ok(result.exited)
        pbs_job_id = result.stdout.strip()

        backoff_count = 0
        interrupted_error: Optional[InterruptedError] = None

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
                eprint(f"Canceling PBS job {pbs_job_id}.")
                expect_ok(
                    connection.run(
                        self._prefix_cmd(f"qdel {pbs_job_id}"), warn=True
                    ).exited
                )
                backoff_count = 0
                interrupted_error = e

        eprint("--- c. Awaiting job start ---")
        time.sleep(1)
        while True:
            result = connection.run(
                self._prefix_cmd(f"qstat {pbs_job_id}"), warn=True, hide=True
            )
            if (
                len(result.stdout.strip()) == 0
                or result.stdout.splitlines()[-1].strip().split()[-2] == "R"
            ):
                break  # Job no longer in queue or has started
            sleep_or_cancel(exponential_backoff(backoff_count))
            backoff_count += 1
        # Report job start time
        timestamp_start = None
        try:
            cmd = self._prefix_cmd(
                "qstat PBS_JOB_ID -xf | grep 'stime = ' | sed 's/.*stime = //' | xargs -I{} date -d \"{}\" +%s"
            )
            timestamp_start = int(
                connection.run(
                    cmd.replace("PBS_JOB_ID", pbs_job_id), warn=True, hide=True
                ).stdout
            )
        except Exception:
            pass
        finally:
            callbacks.on_start(timestamp_start)
        eprint("--- d. Awaiting job completion ---")
        if interrupted_error is None:
            backoff_count = 0
            # Do not wait requested time in case job completes earlier
            # sleep_or_cancel(job.spec.seconds)
        exit_code = 0
        while True:
            result = connection.run(
                self._prefix_cmd(f"qstat {pbs_job_id}"), warn=True, hide=True
            )
            if len(result.stdout.strip()) == 0:
                break  # Job no longer in queue
            sleep_or_cancel(exponential_backoff(backoff_count))
            backoff_count += 1
        # Report job end time
        walltime_fmtd = (
            connection.run(
                self._prefix_cmd(
                    f"qstat {pbs_job_id} -xf | grep 'resources_used.walltime = '"
                ),
                warn=True,
                hide=True,
            )
            .stdout.split("=")[-1]
            .strip()
        )
        timestamp_end = None
        try:
            assert timestamp_start is not None
            timestamp_end = timestamp_start + utils.time_to_seconds(walltime_fmtd)
        except Exception:
            pass
        finally:
            callbacks.on_end(timestamp_end)
        eprint("--- e. Obtaining exit code and cleaning up output/error files ---")
        time.sleep(1)  # Wait a bit for the output/error to be received
        exit_code = -1
        qstat_cmd = f"qstat {pbs_job_id} -f -x"
        result = connection.run(
            self._prefix_cmd(qstat_cmd),
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
        expect_ok(connection.run(f"rm -f {' '.join(output_files)}", warn=True).exited)
        if interrupted_error is not None:
            raise interrupted_error
        expect_ok(exit_code)

    def get_status(self: Self) -> TargetStatus:
        """
        Get the status of the remote PBS target.

        Returns
        -------
        TargetStatus
            The status of the remote target
        """
        with self._connect() as connection:
            # Get the job states
            cmd_template = self._prefix_cmd(
                # Third column indicates the queue
                "qstat -a | awk '$3 == \"QUEUE\" { print $1 }'"
            )
            assert self._target.queue
            output = connection.run(
                cmd_template.replace("QUEUE", self._target.queue), warn=True, hide=True
            ).stdout.strip()
            qstat_job_fields = dict(
                nodes="Resource_List.nodect",
                time_limit="Resource_List.walltime",
                state="job_state",
                time="resources_used.walltime",
            )
            data: Dict[str, List[str]] = {k: [] for k in qstat_job_fields}
            qstat_job_fields = {v: k for k, v in qstat_job_fields.items()}
            job_ids = [s.strip() for s in output.splitlines()]
            cmd = self._prefix_cmd(f"qstat -f {' '.join(job_ids)}")
            output = connection.run(cmd, warn=True, hide=True).stdout.strip()
            for line in output.splitlines() + [None]:  # Handle end of output
                if (line is None or line.startswith("Job Id:")) and len(
                    data["nodes"]
                ) > len(data["time"]):
                    data["time"].append(
                        "0"
                    )  # Job has not started and has no "resources_used.walltime"
                    continue
                try:
                    k, v = line.strip().split(" = ")
                    k = qstat_job_fields[k]
                    data[k].append(v)
                except Exception:
                    continue
            df = pd.DataFrame(data)
            df["time_limit"] = df["time_limit"].apply(lambda s: time_to_seconds(s))
            df["time"] = df["time"].apply(lambda s: time_to_seconds(s))
            df["nodes"] = df["nodes"].apply(lambda s: int(s))
            df["is_using_nodes"] = df["state"].apply(
                lambda s: s
                in [
                    # cf. https://docs.adaptivecomputing.com/torque/4-1-3/Content/topics/commands/qstat.htm
                    "R",  # Running
                    # "E", # Exiting
                    # "T", # Job is being moved
                ]
            )
            df["time_remaining"] = df["time_limit"] - df["time"]
            records = df[
                ["nodes", "time_limit", "is_using_nodes", "time_remaining"]
            ].to_dict("records")  # pyright: ignore[reportCallIssue]
            # Get the node states
            output = connection.run(
                self._prefix_cmd("pbsnodes -a"), warn=True, hide=True
            ).stdout.strip()
            nodes_state = []
            is_node_in_queue = False
            state = "state-unknown"
            for line in output.splitlines():
                line = line.strip()
                if line.startswith("resources_available.Qlist = "):
                    is_node_in_queue = self._target.queue in line.split(" = ")[
                        -1
                    ].split(",")
                elif line.startswith("state ="):
                    state = line.split(" = ")[-1].split(",")
                if len(line.strip()) == 0:
                    if is_node_in_queue:
                        nodes_state.append(state)
                    is_node_in_queue = False
                    state = "state-unknown"
            node_states = dict(
                nodes_in_use=0,
                nodes_unavailable=0,
                nodes_available=0,
            )
            for node_state in nodes_state:
                # https://linux.die.net/man/8/pbsnodes
                if any(s in node_state for s in ["job-exclusive", "reserved", "busy"]):
                    node_states["nodes_in_use"] += 1
                elif not any(
                    s in node_state for s in ["down", "offline", "state-unknown"]
                ):
                    node_states["nodes_available"] += 1
                else:
                    node_states["nodes_unavailable"] += 1
            assert sum(node_states.values()) == len(nodes_state)
            return TargetStatus.model_validate(
                node_states | {"timestamp": int(time.time()), "jobs_status": records}
            )


class DirectExecutionRemoteTarget(RemoteTarget):
    """RemoteTarget implementation a target without any batch system."""

    def _execute_batch_system(
        self: Self,
        connection: Connection,
        job: Job,
        callbacks: RemoteTarget.JobExecutionCallbacks,
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
        callbacks : RemoteTarget.JobExecutionCallbacks
            Callback functions for job state changes
        env : Dict[str, Any]
            Optional environment variables to be injected on the target before executing the job
        """
        cmd = self._prefix_cmd(job.spec.cmd_main, job.spec.required_modules)
        callbacks.on_start()
        try:
            exit_code = connection.run(cmd, warn=True, env=env).exited
        except InterruptedError:
            raise
        finally:
            callbacks.on_end()
        expect_ok(exit_code)
