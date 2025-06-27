"""Module implementing job execution."""

import os
import signal
import time
import traceback
from types import FrameType
from typing import Self, Set

from ms_common import job, scheduling_decision
from ms_common.job import Instance as Job
from ms_common.target import Target
from ms_common.utils import StatusException, eprint

from ms_client.lock_file import LockFile
from ms_client.scheduler_interface import SchedulerClientInterface
from ms_client.utils import RedirectOutputToFile


class Executor:
    """
    This class handles the execution of a single job.
    """

    def __init__(
        self: Self,
        job: Job,
        scheduler: SchedulerClientInterface,
        redirect_output: bool = False,
    ) -> None:
        """
        Create a new instance for executing a job.

        Parameters
        ----------
        job : Job
            The job to be executed
        scheduler : SchedulerInterface
            Interface to the component determining execution time and target
        redirect_output : bool
            If true (default), all output to sys.stdout/sys.stderr will be redirected to a corresponding file in the job output folder (disable for debugging)
        """
        self.__job = job
        self.__scheduler = scheduler
        self.__redirect_output = redirect_output

    def __signal_handler(self: Self, signalnum: int, frame: FrameType | None) -> None:
        """
        Handle a signal sent to the process.

        Parameters
        ----------
        signalnum : int
            The signal that was received
        frame : FrameType | None
            (Unused)

        Raises
        ------
        InterruptedError
            Error containing the signal that was sent to the process
        """
        eprint(f"{self.__class__.__name__} received signal {signalnum}.", flush=True)
        raise InterruptedError(signalnum)

    @staticmethod
    def filter_targets(
        job_spec: job.Spec, scheduler: SchedulerClientInterface
    ) -> Set[str]:
        """
        Obtain the set of available targets of the scheduler for a given job specification.

        Parameters
        ----------
        job_spec : job.Spec
            The job specification on which to filter the targets
        scheduler : SchedulerInterface
            The scheduler from which to obtain the targets to be filtered

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
        for t in targets:
            is_suitable, reason = t.is_suitable(job_spec)
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
        target: Target | None = None
        try:
            decision = self.__scheduler.poll_scheduling_decision(
                self.__job.array_id, self.__job.array_idx
            )
        except Exception:
            raise StatusException(os.EX_UNAVAILABLE)
        match decision:
            case scheduling_decision.Impossible():
                raise Exception(
                    f"Can't schedule job spec {self.__job.spec.name} anywhere."
                )
            case scheduling_decision.Assigned():  # Must come before Deferred, because is child class # TODO does the logic in poll... work then?
                # TODO maybe the decision should return the target directly? (Not just the ID)
                target = decision.target
                eprint(
                    f"Scheduler assigned {target.id} ({target.host}) in T minus {decision.wait_seconds} seconds"
                )
                self.__job.set_status(job.Status.Scheduled(target.id))
                time.sleep(decision.wait_seconds)
            case _:
                raise NotImplementedError()
        eprint(
            f"=== 2. Copying input files to target {target.id} and run optional setup step ==="
        )
        with LockFile(
            f"meta-sched/{os.getuid()}/{target.id}:{self.__job.spec.name}.lock"
        ):
            src = self.__job.local_input
            dst = self.__job.remote_input.parent
            target.transfer(src, dst, Target.TransferMode.UPLOAD)
            target.setup(self.__job)
        eprint(f"=== 3. Executing job on target {target.id} ===")
        target.execute(self.__job)
        eprint(f"=== 4. Fetching results from target {target.id} ===")
        src = self.__job.remote_output
        dst = self.__job.local_output.parent
        target.transfer(src, dst, Target.TransferMode.DOWNLOAD)
        eprint(f"=== 5. Cleaning up files on target {target.id} ===")
        # TODO: Consider always cleaning up (even if job failed/was canceled)
        target.clean_up(self.__job)

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
                final_job_status = job.Status.Canceled()
            except Exception as e:
                status = -1
                if isinstance(e, StatusException):
                    status = e.status
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
