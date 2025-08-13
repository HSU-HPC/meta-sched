"""Module containing class for remote target without a batch system."""

from typing import Any, Dict

from ms_client.job import Instance as Job
from ms_client.remote_target import RemoteTarget
from ms_client.utils import expect_ok


class DirectExecutionRemoteTarget(RemoteTarget):
    """RemoteTarget implementation a target without any batch system."""

    def _execute(
        self: "DirectExecutionRemoteTarget",
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

        # TODO use primitive exclusive job execution:
        # "Queue" job for execution using `flock /tmp/lockfile -c "$CMD"`
        # Check "queue state" using `watch -n 1 "flock -n /tmp/lockfile -c ':' && echo 'free' || echo 'locked'"`

        # TODO avoid long running SSH connection using nohup

        cmd = job.spec.cmd_main
        callbacks.on_start()
        try:
            with self._connect() as connection:
                expect_ok(
                    self._run(
                        connection, f"mkdir -p {job.remote_output}", warn=True
                    ).exited
                )
                with connection.cd(job.remote_output):
                    exit_code = self._run(
                        connection, cmd, env=env, modules=job.spec.required_modules
                    ).exited
        finally:
            callbacks.on_end()
        return exit_code
