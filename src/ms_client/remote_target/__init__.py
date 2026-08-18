"""Module containing code for executing jobs on a remote target."""

import abc
import enum
import os
import sys
import time
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Any, Optional, TextIO, Union

import invoke
from fabric import Connection  # type: ignore[attr-defined]
from fabric.config import Config
from invoke.runners import Result
from ms_common.schemas import Target, TargetStatus
from ms_common.utils import DEFAULT_SSH_PORT, EX_BASH_COMMAND_NOT_FOUND, eprint, is_env_flag_set
from paramiko.ssh_exception import SSHException

from ms_client import ssh
from ms_client.job import Instance as Job
from ms_client.job import get_jobs_dir
from ms_client.utils import ExponentialBackoff, SuppressStderr, expect_ok, sleep


class RemoteTarget:
    """
    Class for transferring data to and from and executing commands on a remote target.
    """

    class _FactoryAccessToken:
        """This class should only be used internally by factory.py"""


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
        self._connection: Optional[Connection] = None
        self.__print_cmd = is_env_flag_set("MS_DEBUG_CMD")

    def _get_connection(
        self: "RemoteTarget",
        retry_count: int = 5,
        backoff: ExponentialBackoff = ExponentialBackoff(factor=10),
        timeout: float = 60,
        ignore_interrupted_error: bool = False,
        fresh: bool = False,
    ) -> Connection:
        """
        Connect to the target over SSH.

        Parameters
        ----------
        retry_count : int
            The maximum number of connection attempts
        backoff : ExponentialBackoff
            Exponential backoff strategy to ensure connection is eventually established
        timeout : float
            The connection timeout in seconds
        ignore_interrupted_error : bool
            If true, ignore InterruptedError (default is False)
        fresh : bool
            If true, do not re-use any open connection

        Returns
        -------
        Connection
            The paramiko SSH connection

        Raises
        ------
        RuntimeError
            The port must match the port in the corresponding SSH configuration entry
        """
        # connect_kwargs are forwarded to
        # https://docs.paramiko.org/en/latest/api/client.html#paramiko.client.SSHClient.connect
        connect_kwargs = dict(
            allow_agent=False,
            look_for_keys=False,
            banner_timeout=timeout,
            auth_timeout=timeout,
            channel_timeout=timeout,
        )
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
        attempt = 0
        if self._connection:
            if self._connection.is_connected:
                if fresh:
                    self._connection.close()  # type: ignore[no-untyped-call]
                    backoff.reset()
                else:
                    return self._connection
        self._connection = None
        while attempt < retry_count:
            try:
                self._connection = Connection(  # type: ignore[no-untyped-call]
                    self._target.id, # Alias from SSH configuration
                    config=config,
                    connect_kwargs=connect_kwargs,
                    connect_timeout=timeout,
                )
                with SuppressStderr():  # Paramiko dumps entire stack trace on stderr
                    #  Explicitly open the connection (eager instead of lazy)
                    self._connection.open()  # type: ignore[no-untyped-call]
                assert self._connection
                return self._connection  # Do not try to reconnect again
            except InterruptedError:  # If ignored, does not count toward attempts
                if not ignore_interrupted_error:
                    raise
            except (OSError, SSHException, EOFError, ConnectionResetError) as e:
                attempt += 1
                eprint(f"Connection failed on attempt #{attempt}:")
                eprint(e)
                if attempt < retry_count:
                    delay = backoff()
                    backoff += 1
                    eprint(f"(Will try again in {delay} seconds.)")
                    sleep(delay)
                else:
                    raise RuntimeError(
                        f"Failed to connect to {self._target.id} after {attempt} attempts."
                    ) from e
        raise RuntimeError("Unreachable code somehow reached")

    def __enter__(self: "RemoteTarget") -> "RemoteTarget":
        return self

    def __exit__(
        self: "RemoteTarget", exc_type: Any, exc_value: Any, traceback: Any
    ) -> None:
        # Clean up any open connection
        if self._connection and self._connection.is_connected:
            self._connection.close()  # type: ignore[no-untyped-call]
        self._connection = None

    class TransferMode(enum.Enum):
        """
        Type (direction) of data transfer between submit host and target.
        """

        UPLOAD = 0
        DOWNLOAD = 1

    def transfer(
        self: "RemoteTarget",
        src: Union[str, PathLike[Any]],
        dst: Union[str, PathLike[Any]],
        mode: TransferMode,
    ) -> None:
        """
        Transfer data between the submit host and the target

        Parameters
        ----------
        src : Union[str, PathLike[Any]]
            Source directory
        std : Union[str, PathLike[Any]]
            Destination directory
        mode : TransferMode
            Direction in which data is transferred between submit host and target
        print_cmd: bool
            Print the command(s) to be executed for debugging purposes
        """
        eprint(
            "Up" if mode == self.TransferMode.UPLOAD else "Down",
            "loading",
            sep="",
            end=" ",
        )
        eprint(src, "to", dst)
        if mode == self.TransferMode.UPLOAD:
            expect_ok(
                self._run(self._get_connection(), f"mkdir -p $(dirname {dst})").exited
            )
            dst = f"{self._target.id!s}:{dst}"
        elif mode == self.TransferMode.DOWNLOAD:
            Path(dst).parent.mkdir(parents=True, exist_ok=True)
            src = f"{self._target.id!s}:{src}"
        else:
            raise NotImplementedError()
        ssh_options = ["StrictHostKeyChecking=no"]
        ssh_options_str = " ".join(f"-o {o}" for o in ssh_options)
        rsync_flags = [
            "--archive",
            # Limit output (uncomment for debugging)
            # "--progress",
            # "--verbose",
            f'-e "ssh -p {self._target.port} {ssh_options_str}"',
        ]
        cmd = f"rsync {' '.join(rsync_flags)} {src} {dst} 1>&2"
        if self.__print_cmd:
            eprint(f"<local>:{os.getcwd()}$", cmd)
        result = invoke.run(
            cmd,
            warn=True,
            in_stream=None,
            out_stream=sys.stderr,
            hide=True,
            pty=False,
        )
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
            src = f"{src!s}/*"
            remote_dst = str(dst).split(":")[-1]
            expect_ok(
                self._run(self._get_connection(), f"mkdir -p {remote_dst}").exited
            )
            cmd = f"scp {' '.join(scp_flags)} {src} {dst} 1>&2"
            if self.__print_cmd:
                eprint(f"<local>:{os.getcwd()}$", cmd)
            result = invoke.run(
                cmd,
                warn=True,
                in_stream=None,
                out_stream=sys.stderr,
                hide=True,
                pty=False,
            )
        status = -1 if result is None else result.exited
        expect_ok(status)

    def purge(self: "RemoteTarget") -> None:
        """
        Delete all job files from the target.
        """
        expect_ok(
            self._run(
                self._get_connection(), f"rm -rf {get_jobs_dir(hidden=True)}",
            ).exited
        )

    def clean_up(self: "RemoteTarget", job: Job) -> None:
        """
        Clean up job related files on the target.

        Parameters
        ----------
        job : Job
            The job of which related files should be deleted on the target
        """
        expect_ok(
            self._run(self._get_connection(), f"rm -rf {job.remote_output}",).exited
        )

    def _create_oe_files(
        self: "RemoteTarget", connection: Connection, stream_contents: bool
    ) -> tuple[str, str]:
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
        suffix = f"_{int(time.time_ns())}"
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
        self: "RemoteTarget",
        connection: Connection,
        cmd: str,
        warn: bool = True,
        hide: bool = False,
        asynchronous: bool = False,
        env: dict[str, Any] = {},
        out_stream: Union[TextIO, Any] = sys.stdout,
        err_stream: Union[TextIO, Any] = sys.stderr,
        modules: list[str] = [],
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
        out_stream : Union[TextIO, Any]
            The target where the standard output of the command should be sent (Defaults to sys.stdout)
        err_stream : Union[TextIO, Any]
            The target where the standard error of the command should be sent (Defaults to sys.stderr)
        modules : List[str]
            Optional environment modules to be loaded before executing the command

        Returns
        -------
        Result
            The result of the command
        """
        # Prefix command with source scripts and modules before execution
        specific_modules = [self._target.module_map[m] for m in modules]  # type: ignore[index]
        cmd = " && ".join(
            [f". {script}" for script in self._target.source_scripts]
            + [f"module load {module}" for module in specific_modules]
            + [cmd]
        )
        if self.__print_cmd:
            cwd = connection.cwd
            if not cwd:
                cwd = ""
            if not cwd.startswith("/"):
                prefix = "~" if len(cwd) == 0 else "~/"
                cwd = f"{prefix}{cwd}"
            eprint(f"{self._target.id}:{cwd}$", cmd)
        result: Result = connection.run(
            cmd,
            warn=warn,
            hide=hide,
            asynchronous=asynchronous,
            env=env,
            out_stream=out_stream,
            err_stream=err_stream,
        )
        return result

    @staticmethod
    def __get_job_env(job: Job) -> dict[str, Any]:
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

    def setup(self: "RemoteTarget", job: Job) -> None:
        """
        Run the set up command of the job files on the target.

        Parameters
        ----------
        job : Job
            The job which to set up on the target
        """
        # Use a fresh, ephemeral connection to ensure correct paths
        with self._get_connection(fresh=True) as connection:
            # Create the job output folder (delete any existing one to avoid confusion)
            expect_ok(self._run(connection, f"rm -rf {job.remote_output}").exited)
            expect_ok(self._run(connection, f"mkdir -p {job.remote_output}").exited)
            with connection.cd(job.remote_output):
                if job.spec.cmd_setup_target:
                    cmd = job.spec.cmd_setup_target
                    result = self._run(
                        connection,
                        cmd,
                        warn=True,
                        env=RemoteTarget.__get_job_env(job),
                        modules=job.spec.required_modules,
                    )
                    eprint(result.stdout)
                    eprint(result.stderr)
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

        on_start: Any = lambda *args, **kwargs: None
        on_end: Any = lambda *args, **kwargs: None

    def execute(
        self: "RemoteTarget",
        job: Job,
        callbacks: JobExecutionCallbacks = JobExecutionCallbacks(),
    ) -> int:
        """
        Execute the job on the target.

        Parameters
        ----------
        job : Job
            The job which to execute on the target
        callbacks : JobExecutionCallbacks
            Callback functions for job state changes

        Returns
        -------
        int
            The exit code of the job or -1 if it could not be determined
        """
        return self._execute(job, callbacks, RemoteTarget.__get_job_env(job))

    @abc.abstractmethod
    def _execute(
        self: "RemoteTarget",
        job: Job,
        callbacks: JobExecutionCallbacks,
        env: dict[str, Any] = {},
    ) -> int:
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

        Returns
        -------
        int
            The exit code of the job or -1 if it could not be determined

        Raises
        ------
        NotImplementedError
            Must be implemented by the concrete remote target
        """
        raise NotImplementedError()

    def get_status(self: "RemoteTarget") -> TargetStatus:
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
