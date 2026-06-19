"""Module containing base class for executing jobs on a remote batch system."""

import abc
import sys
import time
from typing import Any, Dict, Optional, Tuple

from fabric import Connection  # type: ignore[attr-defined]
from ms_common.utils import eprint

from ms_client.job import Instance as Job
from ms_client.remote_target import RemoteTarget
from ms_client.utils import ExponentialBackoff, expect_ok, sleep


class BatchSystemTarget(RemoteTarget):
    """
    Abstract base class for remote targets which have a local batch system for job execution.
    """

    @abc.abstractmethod
    def _submit_job(
        self: "BatchSystemTarget",
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
    def _has_job_started(
        self: "BatchSystemTarget", connection: Connection, local_job_id: str
    ) -> bool:
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
        self: "BatchSystemTarget", connection: Connection, local_job_id: str
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
    def _has_job_ended(
        self: "BatchSystemTarget", connection: Connection, local_job_id: str
    ) -> bool:
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
        self: "BatchSystemTarget", connection: Connection, local_job_id: str
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
    def _cancel_job(
        self: "BatchSystemTarget", connection: Connection, local_job_id: str
    ) -> None:
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
        self: "BatchSystemTarget", connection: Connection, local_job_id: str
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
        self: "BatchSystemTarget",
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
        output_error_files: Tuple[str, str]
        local_job_id: str
        stream_oe = False  # Must be false if not using long living connection

        eprint("--- a. Submitting job ---")
        requested_seconds = job.spec.get_target_seconds(self._target, job.array_idx)
        eprint(f"SECONDS_REQUESTED={requested_seconds}")
        # Use a fresh, ephemeral connection to ensure correct paths
        with self._get_connection(fresh=True) as connection:
            with connection.cd(job.remote_output):
                output_error_files = self._create_oe_files(connection, stream_oe)
                local_job_id = self._submit_job(
                    connection, job, output_error_files, env
                )

        def await_job_start() -> None:
            """
            Wait until the job has been started by the local batch system.
            """
            eprint("--- b. Awaiting job start ---")
            sleep(1)
            backoff = ExponentialBackoff()
            while True:
                if self._has_job_started(self._get_connection(), local_job_id):
                    break
                sleep(backoff())
                backoff += 1
            callbacks.on_start(
                self._get_job_start_time(self._get_connection(), local_job_id)
            )

        def await_job_completion() -> None:
            """
            Wait until the job is no longer being executed by the local bach system.
            """
            eprint("--- c. Awaiting job completion ---")
            # Do not wait requested time in case job completes earlier
            # sleep(requested_seconds)
            # Check repeatedly in intervals of 1-10% of the job time
            wait_until = time.time() + requested_seconds
            backoff = ExponentialBackoff(
                offset=requested_seconds // 100, maximum=requested_seconds // 10
            )
            while True:
                if self._has_job_ended(self._get_connection(), local_job_id):
                    break
                # Do not oversleep (but sleep at least 1 second)
                seconds = max(1, min(backoff(), wait_until - time.time()))
                sleep(seconds)
                backoff += 1
            callbacks.on_end(
                self._get_job_end_time(self._get_connection(), local_job_id)
            )

        def clean_up_and_get_job_status(
            interrupted_error: Optional[InterruptedError],
        ) -> int:
            """
            Deletes temporary job output files (stdout, stderr) and determines job exit code.

            Parameters
            ----------
            interrupted_error : Optional[InterruptedError]
                The InterruptedError that may have occurred during the execution of the job

            Returns
            -------
            int
                The exit code of the jobs

            Raises
            ------
            InterruptedError
                The InterruptedError passed to the function
            """
            eprint("--- d. Cleaning up output/error files and getting exit code ---")
            sleep(1)  # Wait a bit for the output/error to be received when streaming
            # Use a fresh, ephemeral connection to ensure correct paths
            with self._get_connection(
                fresh=True, ignore_interrupted_error=True
            ) as connection:
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
            with self._get_connection(ignore_interrupted_error=True) as connection:
                exit_code = self._get_job_exit_code(connection, local_job_id)
            if exit_code is None:
                exit_code = -1
            return exit_code

        interrupted_error: Optional[InterruptedError] = None
        was_job_started = False
        try:
            await_job_start()
            was_job_started = True
            await_job_completion()
        except InterruptedError as e:
            interrupted_error = e
            if was_job_started:
                callbacks.on_end()
            with self._get_connection(ignore_interrupted_error=True) as connection:
                self._cancel_job(connection, local_job_id)
        finally:
            return clean_up_and_get_job_status(interrupted_error)
