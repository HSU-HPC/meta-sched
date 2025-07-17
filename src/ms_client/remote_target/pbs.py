"""Module containing class for remote target using the PBS Pro/OpenPBS batch system."""

import sys
import time
from typing import Any, Dict, List, Optional, Self

import pandas as pd
from ms_common import utils
from ms_common.schemas import TargetStatus
from ms_common.utils import (eprint, expect_ok, exponential_backoff,
                             seconds_to_time, time_to_seconds)

from ms_client.job import Instance as Job
from ms_client.remote_target import RemoteTarget


# TODO FIXME change parent class
class PBSRemoteTarget(RemoteTarget):
    """RemoteTarget implementation for a PBS Pro/OpenPBS system."""

    def _execute_batch_system(
        self: Self,
        job: Job,
        callbacks: RemoteTarget.JobExecutionCallbacks,
        env: Dict[str, Any] = {},
    ) -> None:
        """
        Execute the job on the target using PBS.

        Parameters
        ----------
        job : Job
            The job to be executed on the target
        env : Dict[str, Any]
            Optional environment variables to be injected on the target before executing the job
        """
        eprint("--- a. Creating and watching output/error files ---")
        # Do not NOT stream the output/error files
        with self._connect() as connection:
            with connection.cd(job.remote_output):
                output_files = self._create_oe_files(connection, False)
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
        with self._connect() as connection:
            with connection.cd(job.remote_output):
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
                with self._connect() as connection:
                    with connection.cd(job.remote_output):
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
            with self._connect() as connection:
                with connection.cd(job.remote_output):
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
            with self._connect() as connection:
                with connection.cd(job.remote_output):
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
            with self._connect() as connection:
                with connection.cd(job.remote_output):
                    result = connection.run(
                        self._prefix_cmd(f"qstat {pbs_job_id}"), warn=True, hide=True
                    )
            if len(result.stdout.strip()) == 0:
                break  # Job no longer in queue
            sleep_or_cancel(exponential_backoff(backoff_count))
            backoff_count += 1
        # Report job end time
        with self._connect() as connection:
            with connection.cd(job.remote_output):
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
        with self._connect() as connection:
            with connection.cd(job.remote_output):
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
        with self._connect() as connection:
            with connection.cd(job.remote_output):
                expect_ok(
                    connection.run(f"rm -f {' '.join(output_files)}", warn=True).exited
                )
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
