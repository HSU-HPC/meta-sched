"""Module containing base class for executing jobs on a remote batch system."""

import abc
import sys
import time
from typing import Any, Dict, Optional, Self, Tuple

from fabric import Connection  # type: ignore[attr-defined]
from ms_common.utils import eprint

from ms_client.job import Instance as Job
from ms_client.remote_target import RemoteTarget
from ms_client.utils import ExponentialBackoff, expect_ok


class BatchSystemTarget(RemoteTarget):
    """Abstract base class for remote targets which have a local batch system for job execution."""

    @abc.abstractmethod
    def _submit_job(
        self: Self,
        connection: Connection,
        job: Job,
        oe: Tuple[str, str],
        env: Dict[str, Any],
    ) -> str:
        """
        Submit a job for execution using the batch system.

        Parameters
        ----------
        connection : Connection
            The SSH connection to the remote target
        job : Job
            The job to be executed
        oe : Tuple[str, str]
            The filename for the output and error files to be used by the job
        env : Dict[str, Any]
            Environment variables to be set

        Returns
        -------
        str
            The local job ID

        Raises
        ------
        NotImplementedError
            Must be implemented by the concrete remote target
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def _has_job_started(self: Self, connection: Connection, local_job_id: str) -> bool:
        """
        Check if the job has started being executed by the batch system.

        Parameters
        ----------
        connection : Connection
            The SSH connection to the remote target
        local_job_id : str
            The ID of the job that was submitted

        Returns
        -------
        bool
            True, if the job has started to be executed (may already have finished/failed)

        Raises
        ------
        NotImplementedError
            Must be implemented by the concrete remote target
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def _get_job_start_time(
        self: Self, connection: Connection, local_job_id: str
    ) -> Optional[int]:
        """
        Get the timestamp of when the job started executing.

        Parameters
        ----------
        connection : Connection
            The SSH connection to the remote target
        local_job_id : str
            The ID of the job that was submitted

        Returns
        -------
        Optional[int]
            The unix timestamp (seconds since epoch) of when the job has started or None if it could not be determined

        Raises
        ------
        NotImplementedError
            Must be implemented by the concrete remote target
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def _has_job_ended(self: Self, connection: Connection, local_job_id: str) -> bool:
        """
        Check if the job has stopped being executed by the batch system.

        Parameters
        ----------
        connection : Connection
            The SSH connection to the remote target
        local_job_id : str
            The ID of the job that was submitted

        Returns
        -------
        bool
            True, if the job has finished to be executed (may also have failed)

        Raises
        ------
        NotImplementedError
            Must be implemented by the concrete remote target
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def _get_job_end_time(
        self: Self, connection: Connection, local_job_id: str
    ) -> Optional[int]:
        """
        Get the timestamp of when the job stopped executing.

        Parameters
        ----------
        connection : Connection
            The SSH connection to the remote target
        local_job_id : str
            The ID of the job that was submitted

        Returns
        -------
        Optional[int]
            The unix timestamp (seconds since epoch) of when the job has stopped executing or None if it could not be determined

        Raises
        ------
        NotImplementedError
            Must be implemented by the concrete remote target
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def _cancel_job(self: Self, connection: Connection, local_job_id: str) -> None:
        """
        Cancel the job submitted to the batch system.

        Parameters
        ----------
        connection : Connection
            The SSH connection to the remote target
        local_job_id : str
            The ID of the job that was submitted

        Raises
        ------
        NotImplementedError
            Must be implemented by the concrete remote target
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def _get_job_exit_code(
        self: Self, connection: Connection, local_job_id: str
    ) -> Optional[int]:
        """
        Check if the job has started being executed by the batch system.

        Parameters
        ----------
        connection : Connection
            The SSH connection to the remote target
        local_job_id : str
            The ID of the job that was submitted

        Returns
        -------
        Optional[int]
            The exit code of the job or None if it could not be determined

        Raises
        ------
        NotImplementedError
            Must be implemented by the concrete remote target
        """
        raise NotImplementedError()

    def _execute(
        self: Self,
        job: Job,
        callbacks: RemoteTarget.JobExecutionCallbacks,
        env: Dict[str, Any] = {},
    ) -> int:
        """
        Execute the job directly on the target.

        Parameters
        ----------
        job : Job
            The job to be executed on the target
        callbacks : RemoteTarget.JobExecutionCallbacks
            Callback functions for job state changes
        env : Dict[str, Any]
            Optional environment variables to be injected on the target before executing the job

        Returns
        -------
        int
            The exit code of the job or -1 if it could not be determined
        """
        backoff = ExponentialBackoff()
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
                nonlocal backoff, interrupted_error
                if interrupted_error is not None:
                    eprint("Job was already canceled. (Nothing to do.)")
                    return
                # Defer handling until Slurm job has been canceled completely
                eprint(f"Canceling job with local ID {local_job_id}.")
                with self._connect() as connection:
                    self._cancel_job(connection, local_job_id)
                backoff.reset()
                interrupted_error = e

        output_error_files: Tuple[str, str]
        local_job_id: str
        stream_oe = False  # Must be false if not using long living connection
        with self._connect() as connection:
            with connection.cd(job.remote_output):
                output_error_files = self._create_oe_files(connection, stream_oe)
                local_job_id = self._submit_job(
                    connection, job, output_error_files, env
                )
        eprint("--- c. Awaiting job start ---")
        time.sleep(1)
        while True:
            with self._connect() as connection:
                if self._has_job_started(connection, local_job_id):
                    break
            sleep_or_cancel(backoff())
            backoff += 1
        with self._connect() as connection:
            callbacks.on_start(self._get_job_start_time(connection, local_job_id))
        eprint("--- d. Awaiting job completion ---")
        # Do not wait requested time in case job completes earlier
        # sleep_or_cancel(job.spec.seconds)
        backoff.reset()
        while True:
            with self._connect() as connection:
                if self._has_job_ended(connection, local_job_id):
                    break
            sleep_or_cancel(backoff())
            backoff += 1
        with self._connect() as connection:
            callbacks.on_end(self._get_job_end_time(connection, local_job_id))
        eprint("--- e. Obtaining exit code and cleaning up output/error files ---")
        time.sleep(1)  # Wait a bit for the output/error to be received when streaming
        with self._connect() as connection:
            exit_code = self._get_job_exit_code(connection, local_job_id)
        if exit_code is None:
            exit_code = -1
        with self._connect() as connection:
            with connection.cd(job.remote_output):
                if not stream_oe:
                    eprint()  # Separate with blank line
                    for filename, stream in zip(
                        output_error_files, (sys.stdout, sys.stderr)
                    ):
                        expect_ok(
                            self._run(
                                connection,
                                f"cat {filename} && rm {filename}",
                                out_stream=stream,
                            ).exited
                        )
                expect_ok(
                    self._run(
                        connection, f"rm -f {' '.join(output_error_files)}"
                    ).exited
                )
        sys.stdout.flush()
        sys.stderr.flush()
        if interrupted_error is not None:
            raise interrupted_error
        return exit_code
