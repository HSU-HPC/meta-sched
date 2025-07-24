"""Module implementing job execution."""

import os
import signal
import time
import traceback
from types import FrameType
from typing import List, Optional, Self, Set, Tuple

import ms_common.schemas
from ms_common import schemas
from ms_common.schemas import JobKey
from ms_common.schemas import Spec as JobSpec
from ms_common.schemas import Target
from ms_common.utils import StatusException, eprint, time_to_seconds

from ms_client import job, ssh
from ms_client.config import TargetAdditionalConfigs
from ms_client.job import Instance as Job
from ms_client.remote_target import RemoteTarget
from ms_client.remote_target.factory import remote_target_from_target
from ms_client.scheduler_interface import SchedulerClientInterface
from ms_client.utils import LockFile, RedirectOutputToFile


class Executor:
    """
    This class handles the execution of a single job.
    """

    def __init__(
        self: Self,
        job: Job,
        job_token: str,
        scheduler: SchedulerClientInterface,
        redirect_output: bool = False,
    ) -> None:
        """
        Create a new instance for executing a job.

        Parameters
        ----------
        job : Job
            The job to be executed
        job_token : str
            The random string required to modify the job at the server
        scheduler : SchedulerInterface
            Interface to the component determining execution time and target
        redirect_output : bool
            If true (default), all output to sys.stdout/sys.stderr will be redirected to a corresponding file in the job output folder (disable for debugging)
        """
        self.__job = job
        # Used to look up job at client
        self.__job_key = JobKey(job_token, job.array_id, job.array_idx)
        self.__scheduler = scheduler
        self.__redirect_output = redirect_output

    def __signal_handler(
        self: Self, signalnum: int, frame: Optional[FrameType]
    ) -> None:
        """
        Handle a signal sent to the process.

        Parameters
        ----------
        signalnum : int
            The signal that was received
        frame : Optional[FrameType]
            (Unused)

        Raises
        ------
        InterruptedError
            Error containing the signal that was sent to the process
        """
        eprint(f"{self.__class__.__name__} received signal {signalnum}.", flush=True)
        raise InterruptedError(signalnum)

    @staticmethod
    def is_target_suitable(
        target: Target,
        job_spec: JobSpec,
        additional_configs: Optional[TargetAdditionalConfigs] = None,
    ) -> Tuple[bool, str]:
        """
        Check if the target is suitable for executing a specific job.

        Parameters
        ----------
        job_spec : Spec
            The specification of the job considered for execution on the target
        additional_configs : Optional[TargetAdditionalConfigs]
            Additional user configurations by which to evaluate the target

        Returns
        -------
        Tuple[bool, str]
            Suitability of the target for executing the job and reason
        """

        if not ssh.has_ssh_config_entry(target.id):
            return False, "Credentials missing"
        if target.max_time is not None and job_spec.seconds > time_to_seconds(
            target.max_time
        ):
            return False, "Too much time required"
        max_nodes = (
            min(target.nodes, target.max_nodes) if target.max_nodes else target.nodes
        )
        if job_spec.nodes > max_nodes:
            return False, "Too many nodes required"
        cores_per_node = job_spec.ranks_per_node * job_spec.cores_per_rank
        if cores_per_node > target.cores_per_node:
            return False, "Too many cores required"
        tags = target.tags
        if additional_configs:
            tags += additional_configs.tags
        for t in job_spec.required_tags:
            if t not in tags:
                return False, f'Required tag "{t}" missing'
        for m in job_spec.required_modules:
            if m not in target.module_map:
                return False, f'Required module "{m}" missing'
        return True, "OK"

    @staticmethod
    def filter_targets(
        job_spec: JobSpec,
        scheduler: SchedulerClientInterface,
        targets_additional_configs: List[TargetAdditionalConfigs],
    ) -> Set[str]:
        """
        Obtain the set of available targets of the scheduler for a given job specification.

        Parameters
        ----------
        job_spec : JobSpec
            The job specification on which to filter the targets
        scheduler : SchedulerInterface
            The scheduler from which to obtain the targets to be filtered
        targets_additional_configs : List[TargetAdditionalConfigs]
            Additional user configurations by which to filter the targets

        Returns
        -------
        Set[Target]
            All targets on which the job could be executed
        """
        available_targets: Set[str] = set()
        try:
            targets = scheduler.targets
        except Exception:
            raise StatusException(os.EX_UNAVAILABLE)
        additional_configs_dict = {t.id: t for t in targets_additional_configs}
        for t in targets:
            additional_configs = None
            if t.id in additional_configs_dict:
                additional_configs = additional_configs_dict[t.id]
            is_suitable, reason = Executor.is_target_suitable(
                t, job_spec, additional_configs
            )
            # Uncomment for debugging:
            # eprint(f'Job may run on {t.id}: {"Yes" if is_suitable else "No"} ({reason})')
            if is_suitable:
                available_targets.add(t.id)
        return available_targets

    def __run(self: Self) -> None:
        """
        Execute the job (blocking the calling thread).
        """
        signal.signal(signal.SIGINT, self.__signal_handler)
        signal.signal(signal.SIGTERM, self.__signal_handler)
        eprint(f"MS_ARRAY_ID={self.__job.array_id}")
        eprint(f"MS_ARRAY_IDX={self.__job.array_idx}")
        eprint(f"MS_JOB_SPEC={self.__job.spec.name}")
        eprint("=== 1. Awaiting scheduling of job ===")
        target: Target
        try:
            decision = self.__scheduler.poll_scheduling_decision(self.__job_key)
        except Exception:
            raise StatusException(os.EX_UNAVAILABLE)
        match decision:
            case ms_common.schemas.Impossible():
                raise Exception(
                    f"Can't schedule job spec {self.__job.spec.name} anywhere."
                )
            case schemas.Assigned():
                target = [
                    t for t in self.__scheduler.targets if t.id == decision.target_id
                ][0]
                wait_seconds = max(0, decision.timestamp_start - int(time.time()))
                eprint(
                    f"Scheduler assigned {target.id} ({target.host}) in T minus {wait_seconds} seconds (at {decision.timestamp_start})"
                )
                self.__job.set_status(job.Status.Scheduled(target.id))
                time.sleep(wait_seconds)
            case _:
                raise NotImplementedError("Unknown scheduling decision type")
        remote_target = remote_target_from_target(target)
        eprint(
            f"=== 2. Copying input files to target {target.id} and run optional setup step ==="
        )
        with LockFile(
            f"meta-sched/{os.getuid()}/{target.id}:{self.__job.spec.name}.lock"
        ):
            src = self.__job.local_input
            dst = self.__job.remote_input.parent
            remote_target.transfer(src, dst, RemoteTarget.TransferMode.UPLOAD)
            remote_target.setup(self.__job)
        eprint(f"=== 3. Executing job on target {target.id} ===")

        def callback_job_started(timestamp: Optional[int] = None) -> None:
            """
            Callback to update the Meta Scheduler server that the job has started executing on the target.

            Parameters
            ----------
            timestamp : Optional[int]
                The timestamp of when the job was started (Defaults to current timestamp)
            """
            if timestamp is None:
                timestamp = int(time.time())
            self.__job.set_status(job.Status.Running(target.id))
            try:
                self.__scheduler.update_job_started(self.__job_key, timestamp)
            except Exception as e:
                eprint("Error updating job state:", e)

        def callback_job_ended(timestamp: Optional[int] = None) -> None:
            """
            Callback to update the Meta Scheduler server that the job has finished executing on the target.

            Parameters
            ----------
            timestamp : Optional[int]
                The timestamp of when the job has ended (Defaults to current timestamp)
            """
            if timestamp is None:
                timestamp = int(time.time())
            self.__job.set_status(job.Status.Completed())
            try:
                self.__scheduler.update_job_ended(self.__job_key, timestamp)
            except Exception as e:
                eprint("Error updating job state:", e)

        callbacks = RemoteTarget.JobExecutionCallbacks(
            on_start=callback_job_started,
            on_end=callback_job_ended,
        )
        remote_target.execute(self.__job, callbacks)
        eprint(f"=== 4. Fetching results from target {target.id} ===")
        src = self.__job.remote_output
        dst = self.__job.local_output.parent
        remote_target.transfer(src, dst, RemoteTarget.TransferMode.DOWNLOAD)
        eprint(f"=== 5. Cleaning up files on target {target.id} ===")
        # TODO: Consider always cleaning up (even if job failed/was canceled)
        remote_target.clean_up(self.__job)

    def run(self: Self) -> None:
        """
        Execute the job (blocking the calling thread) and manage output files.
        """
        self.__job.local_output.mkdir(parents=True, exist_ok=True)
        pid_file = self.__job.local_output / ".pid"
        pid_file.write_text(str(os.getpid()))
        self.__job.set_status(job.Status.Pending())
        kwargs = (
            dict(
                stdout=self.__job.local_output / "stdout",
                stderr=self.__job.local_output / "stderr",
            )
            if self.__redirect_output
            else {}
        )
        with RedirectOutputToFile(**kwargs):
            final_job_status: job.Status._Enum = job.Status.Completed()
            try:
                self.__run()
            except InterruptedError:
                self.__scheduler.cancel_job(self.__job_key)
                final_job_status = job.Status.Canceled()
            except Exception as e:
                status = -1
                if isinstance(e, StatusException):
                    status = e.status
                    eprint(e)
                else:
                    eprint(traceback.format_exc())
                final_job_status = job.Status.Failed(status)
            finally:
                try:
                    self.__job.set_status(final_job_status)
                except FileNotFoundError:
                    eprint(
                        f"Status file for job {self.__job.array_id}.{self.__job.array_idx} was deleted."
                    )
        pid_file.unlink(missing_ok=True)
