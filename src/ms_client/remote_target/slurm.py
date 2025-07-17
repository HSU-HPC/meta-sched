"""Module containing class for remote target using the Slurm batch system."""

import io
import sys
import time
from typing import Any, Dict, Optional, Self, Tuple

import pandas as pd
from fabric import Connection  # type: ignore[attr-defined]
from ms_common.schemas import TargetStatus
from ms_common.utils import eprint, expect_ok, seconds_to_time, time_to_seconds

from ms_client.job import Instance as Job
from ms_client.remote_target.batch_system import BatchSystemTarget


class SlurmRemoteTarget(BatchSystemTarget):
    """RemoteTarget implementation for a Slurm system."""

    __template_cmd_sacct = "sacct -j SLURM_JOB_ID --noheader --format=FORMAT | head -n 1 | awk '{print $1}' | xargs -I{} date -d {} +%s"

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
        """
        argv = ["sbatch"]
        if self._target.queue:
            argv.append(f"--partition={self._target.queue}")
        if job.spec.exclusive:
            argv.append("--exclusive")
        argv.append(f"--nodes={job.spec.nodes}")
        argv.append(f"--ntasks-per-node={job.spec.ranks_per_node}")
        argv.append(f"--cpus-per-task={job.spec.cores_per_rank}")
        argv.append(f"--time={seconds_to_time(job.spec.seconds)}")
        argv.append(f"--output={oe[0]}")
        argv.append(f"--error={oe[1]}")
        argv.append(f"--wrap='{job.spec.cmd_main}'")
        argv.append(f"--job-name={job.spec.name}")
        cmd = self._prefix_cmd(" ".join(argv), job.spec.required_modules)
        result = connection.run(cmd, warn=True, env=env, out_stream=sys.stderr)
        expect_ok(result.exited)
        slurm_job_id = result.stdout.strip().split()[-1]
        return str(slurm_job_id)

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
        """
        cmd = self._prefix_cmd(f"squeue -j {local_job_id} --format %T --noheader")
        output = connection.run(cmd, warn=True, hide=True).stdout.strip()
        # Job no longer in queue or has started
        return len(output) == 0 or output == "RUNNING"

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
        """
        cmd = SlurmRemoteTarget.__template_cmd_sacct.replace("FORMAT", "start").replace(
            "SLURM_JOB_ID", local_job_id
        )
        timestamp_start = None
        try:
            timestamp_start = int(
                connection.run(
                    self._prefix_cmd(cmd),
                    warn=True,
                    hide=True,
                ).stdout.strip()
            )
        except Exception:
            pass
        return timestamp_start

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
        """
        cmd = self._prefix_cmd(f"squeue -j {local_job_id} --format %T --noheader")
        output = connection.run(cmd, warn=True, hide=True).stdout.strip()
        # Job no longer in queue
        return len(output) == 0

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
        """
        cmd = SlurmRemoteTarget.__template_cmd_sacct.replace("FORMAT", "end").replace(
            "SLURM_JOB_ID", local_job_id
        )
        timestamp_end = None
        try:
            timestamp_end = int(
                connection.run(
                    cmd,
                    warn=True,
                    hide=True,
                ).stdout.strip()
            )
        except Exception:
            pass
        return timestamp_end

    def _cancel_job(self: Self, connection: Connection, local_job_id: str) -> None:
        """
        Cancel the job submitted to the batch system.

        Parameters
        ----------
        connection : Connection
            The SSH connection to the remote target
        local_job_id : str
            The ID of the job that was submitted
        """
        expect_ok(
            connection.run(
                self._prefix_cmd(f"scancel {local_job_id}"), warn=True
            ).exited
        )

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
        """
        exit_code = None
        cmd = f'sacct -j {local_job_id} --format "State,ExitCode" --noheader'
        result = connection.run(
            self._prefix_cmd(cmd),
            warn=True,
            hide=True,
        )
        try:
            expect_ok(result.exited)
            sacct_state, sacct_exit_code = result.stdout.splitlines()[0].split()
            exit_code = int(sacct_exit_code.split(":")[0])
        except Exception:
            eprint(f"Job completed, but could not determine exit code using {cmd}:")
        return exit_code

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
