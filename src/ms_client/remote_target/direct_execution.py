"""Module containing class for remote target without a batch system."""

from typing import Any, Dict, Self

from ms_common.utils import expect_ok

from ms_client.job import Instance as Job
from ms_client.remote_target import RemoteTarget


class DirectExecutionRemoteTarget(RemoteTarget):
    """RemoteTarget implementation a target without any batch system."""

    def _execute_batch_system(
        self: Self,
        job: Job,
        callbacks: RemoteTarget.JobExecutionCallbacks,
        env: Dict[str, Any] = {},
    ) -> None:
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
        """

        # TODO use primitive exclusive job execution:
        # "Queue" job for execution using `flock /tmp/lockfile -c "$CMD"`
        # Check "queue state" using `watch -n 1 "flock -n /tmp/lockfile -c ':' && echo 'free' || echo 'locked'"`

        # TODO avoid long running SSH connection using nohup

        cmd = self._prefix_cmd(job.spec.cmd_main, job.spec.required_modules)
        callbacks.on_start()
        try:
            with self._connect() as connection:
                with connection.cd(job.remote_output):
                    exit_code = connection.run(cmd, warn=True, env=env).exited
        except InterruptedError:
            raise
        finally:
            callbacks.on_end()
        expect_ok(exit_code)
