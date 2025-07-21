"""Module containing code for executing jobs on a remote target."""

import abc
import enum
import sys
import time
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Any, Dict, List, Self, TextIO, Tuple

import invoke
from fabric import Connection  # type: ignore[attr-defined]
from fabric.config import Config
from invoke.runners import Result
from ms_common.schemas import Target, TargetStatus
from ms_common.utils import (DEFAULT_SSH_PORT, EX_BASH_COMMAND_NOT_FOUND,
                             eprint, expect_ok)

from ms_client import ssh
from ms_client.job import Instance as Job


class RemoteTarget:
    """
    Class for transferring data to and from and executing commands on a remote target.
    """

    class _FactoryAccessToken:
        """This class should only be used internally by factory.py"""

        pass

    def __init__(self, sentinel: _FactoryAccessToken, target: Target) -> None:
        """
        Create a new object representing a remote target for data transfer and command/job execution.

        Parameters
        ----------
        sentinel : _FactoryAccessToken
            Token to make sure the constructor is only used by the factory method
        target : Target
            The target of the
        """
        if not isinstance(sentinel, RemoteTarget._FactoryAccessToken):
            raise PermissionError(
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
                        self._run(connection, f"mkdir -p $(dirname {dst})").exited
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
                expect_ok(self._run(connection, f"mkdir -p {remote_dst}").exited)
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
            expect_ok(self._run(connection, f"rm -rf {job.remote_output}").exited)

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
        # Use random filenames to avoid collisions
        suffix = f"_{int(time.time() * 1000)}"
        output_files = {f"output{suffix}": sys.stdout, f"error{suffix}": sys.stderr}
        for k, v in output_files.items():
            expect_ok(
                self._run(
                    connection,
                    f"touch {k}",
                ).exited
            )
            if stream_contents:
                self._run(
                    connection,
                    f"tail -f {k} &",
                    asynchronous=True,
                    out_stream=v,
                )
        oe = tuple(output_files.keys())
        assert len(oe) == 2
        return oe

    def _run(
        self: Self,
        connection: Connection,
        cmd: str,
        warn: bool = True,
        hide: bool = False,
        asynchronous: bool = False,
        env: Dict[str, Any] = {},
        out_stream: TextIO | Any = sys.stdout,
        modules: List[str] = [],
    ) -> Result:
        """
        Prefix a shell command with commands to source target shell scripts and load environment modules before executing it.

        Parameters
        ----------
        connection : Connection
            The connection over which the command should be executed
        cmd : str
            The command to be prefixed and executed
        warn : bool
            If true, do not raise UnexpectedExit when the exit code of the command is non-zero (Default to True)
        hide : bool
            If true, both the standard output and standard error of the command will be suppressed (Defaults to False)
        asynchronous : bool
            If true, run the command in the background without blocking and return a Promise instead of a Result (Defaults to False)
        env : Dict[str, Any]
            Shell environment used for command execution
        out_stream : TextIO | Any
            The target where the standard output of the command should be sent (Defaults to sys.stdout)
        modules : List[str]
            Optional environment modules to be loaded before executing the command

        Returns
        -------
        Result
            The result of the command
        """
        # Prefix command with source scripts and modules before execution
        specific_modules = [self._target.module_map[m] for m in modules]
        cmd = " && ".join(
            [f". {script}" for script in self._target.source_scripts]
            + [f"module load {module}" for module in specific_modules]
            + [cmd]
        )
        result: Result = connection.run(
            cmd,
            warn=warn,
            hide=hide,
            asynchronous=asynchronous,
            env=env,
            out_stream=out_stream,
        )
        return result

    @staticmethod
    def __get_job_env(job: Job) -> Dict[str, Any]:
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
            expect_ok(self._run(connection, f"mkdir -p {job.remote_output}").exited)
            with connection.cd(job.remote_output):
                if job.spec.cmd_setup:
                    cmd = job.spec.cmd_setup
                    result = self._run(
                        connection,
                        cmd,
                        warn=True,
                        env=RemoteTarget.__get_job_env(job),
                        modules=job.spec.required_modules,
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
        with self._connect() as connection:
            expect_ok(self._run(connection, f"mkdir -p {job.remote_output}").exited)
        self._execute(job, callbacks, RemoteTarget.__get_job_env(job))

    @abc.abstractmethod
    def _execute(
        self: Self,
        job: Job,
        callbacks: JobExecutionCallbacks,
        env: Dict[str, Any] = {},
    ) -> None:
        """
        Execute the job on the remote target.

        Parameters
        ----------
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
