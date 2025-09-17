"""Module containing class for remote target using the PBS Pro/OpenPBS batch system."""

import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from fabric import Connection  # type: ignore[attr-defined]
from ms_common import utils
from ms_common.schemas import TargetStatus
from ms_common.utils import eprint, seconds_to_time, time_to_seconds

from ms_client.job import Instance as Job
from ms_client.remote_target.batch_system import BatchSystemTarget
from ms_client.utils import expect_ok


class PBSRemoteTarget(BatchSystemTarget):
    """RemoteTarget implementation for a PBS Pro/OpenPBS system."""

    def _submit_job(
        self: "PBSRemoteTarget",
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
        argv = ["qsub"]
        if self._target.queue:
            argv += ["-q", self._target.queue]
        if job.spec.exclusive:
            argv += ["-l", "place=excl"]
        ranks_per_node = job.spec.ranks_per_node
        if ranks_per_node is None:
            ranks_per_node = self._target.cores_per_node // job.spec.cores_per_rank
        cores_per_node = job.spec.cores_per_rank * ranks_per_node
        argv += [
            "-l",
            f"select={job.spec.nodes}:ncpus={cores_per_node}:mpiprocs={ranks_per_node}:ompthreads={job.spec.cores_per_rank}",
        ]
        argv += [
            "-l",
            f"walltime={seconds_to_time(job.spec.get_target_seconds(self._target), False)}",
        ]
        argv += ["-o", oe[0]]
        argv += ["-e", oe[1]]
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
        cmd = " ".join(argv)
        result = self._run(
            connection,
            cmd,
            warn=True,
            env=env,
            out_stream=sys.stderr,
            modules=job.spec.required_modules,
        )
        expect_ok(result.exited)
        pbs_job_id = result.stdout.strip()
        return str(pbs_job_id)

    def _has_job_started(
        self: "PBSRemoteTarget", connection: Connection, local_job_id: str
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
        """
        result = self._run(connection, f"qstat {local_job_id}", hide=True)
        # Job no longer in queue or has started
        return (
            len(result.stdout.strip()) == 0
            or result.stdout.splitlines()[-1].strip().split()[-2] == "R"
        )

    def _get_job_start_time(
        self: "PBSRemoteTarget", connection: Connection, local_job_id: str
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
        timestamp_start = None
        try:
            cmd = (
                "qstat PBS_JOB_ID -xf | grep 'stime = ' | sed 's/.*stime = //' | xargs -I{} date -d \"{}\" +%s"
            ).replace("PBS_JOB_ID", local_job_id)
            timestamp_start = int(self._run(connection, cmd, hide=True).stdout)
        except Exception:
            pass
        return timestamp_start

    def _has_job_ended(
        self: "PBSRemoteTarget", connection: Connection, local_job_id: str
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
        """
        result = self._run(connection, f"qstat {local_job_id}", hide=True)
        # Job no longer in queue
        return len(result.stdout.strip()) == 0

    def _get_job_end_time(
        self: "PBSRemoteTarget", connection: Connection, local_job_id: str
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
        walltime_fmtd = (
            self._run(
                connection,
                f"qstat {local_job_id} -xf | grep 'resources_used.walltime = '",
                hide=True,
            )
            .stdout.split("=")[-1]
            .strip()
        )
        timestamp_end = None
        try:
            timestamp_start = self._get_job_start_time(connection, local_job_id)
            assert timestamp_start is not None
            timestamp_end = timestamp_start + utils.time_to_seconds(walltime_fmtd)
        except Exception:
            pass
        return timestamp_end

    def _cancel_job(
        self: "PBSRemoteTarget", connection: Connection, local_job_id: str
    ) -> None:
        """
        Cancel the job submitted to the batch system.

        Parameters
        ----------
        connection : Connection
            The SSH connection to the remote target
        local_job_id : str
            The ID of the job that was submitted
        """
        expect_ok(self._run(connection, f"qdel {local_job_id}").exited)

    def _get_job_exit_code(
        self: "PBSRemoteTarget", connection: Connection, local_job_id: str
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
        cmd = f"qstat {local_job_id} -f -x"
        result = self._run(
            connection,
            cmd,
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
            eprint(f"Job completed, but could not determine exit code using {cmd}:")
        return exit_code

    def get_status(self: "PBSRemoteTarget") -> TargetStatus:
        """
        Get the status of the remote PBS target.

        Returns
        -------
        TargetStatus
            The status of the remote target
        """
        with self._connect() as connection:
            # Get the job states
            assert self._target.queue
            # Third column indicates the queue
            cmd = "qstat -a | awk '$3 == \"QUEUE\" { print $1 }'".replace(
                "QUEUE", self._target.queue
            )
            output = self._run(connection, cmd, hide=True).stdout.strip()
            qstat_job_fields = dict(
                nodes="Resource_List.nodect",
                time_limit="Resource_List.walltime",
                state="job_state",
                time="resources_used.walltime",
            )
            data: Dict[str, List[str]] = {k: [] for k in qstat_job_fields}
            qstat_job_fields = {v: k for k, v in qstat_job_fields.items()}
            job_ids = [s.strip() for s in output.splitlines()]
            cmd = f"qstat -f {' '.join(job_ids)}"
            output = self._run(connection, cmd, hide=True).stdout.strip()
            for line in output.splitlines() + [None]:  # Handle end of output
                if (line is None or line.startswith("Job Id:")) and len(
                    data["nodes"]
                ) > len(data["time"]):
                    data["time"].append(
                        "0"
                    )  # Job has not started and has no "resources_used.walltime"
                    continue
                try:
                    assert line is not None
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
            output = self._run(connection, "pbsnodes -a", hide=True).stdout.strip()
            nodes_state = []
            is_node_in_queue = False
            state = ["state-unknown"]
            for line in output.splitlines():
                line = line.strip()
                if line.startswith("resources_available.Qlist = "):
                    is_node_in_queue = self._target.queue in line.split(" = ")[
                        -1
                    ].split(",")
                elif line.startswith("state ="):
                    state = line.split(" = ")[-1].split(",")
                if len(line.strip()) == 0:
                    # Complete parsing node and reset state
                    if is_node_in_queue:
                        nodes_state.append(state)
                    is_node_in_queue = False
                    state = ["state-unknown"]
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
