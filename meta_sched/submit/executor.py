import os
import signal
import time
import traceback
from types import FrameType
from typing import Dict, Self

from meta_sched.common import job, scheduling_decision
from meta_sched.common.job import Instance as Job
from meta_sched.common.scheduler_interface import SchedulerInterface
from meta_sched.common.target import Target
from meta_sched.common.utils import StatusException, eprint
from meta_sched.submit.lock_file import LockFile
from meta_sched.submit.utils import RedirectOutputToFile


class Executor:
    def __init__(
        self,
        job: Job,
        scheduler: SchedulerInterface,
        redirect_output: bool = False,
    ) -> None:
        self.__job = job
        self.__scheduler = scheduler
        self.__redirect_output = redirect_output

    def __signal_handler(self: Self, signalnum: int, frame: FrameType | None) -> None:
        eprint(f"{self.__class__.__name__} received signal {signalnum}.", flush=True)
        raise InterruptedError(signalnum)

    def __run(self: Self) -> None:
        signal.signal(signal.SIGINT, self.__signal_handler)
        signal.signal(signal.SIGTERM, self.__signal_handler)
        eprint("=== 1. Selecting suitable targets for job ===")
        suitable_targets: Dict[str, Target] = {}
        try:
            targets = self.__scheduler.targets
        except Exception:
            raise StatusException(os.EX_UNAVAILABLE)
        for t in targets:
            is_suitable, reason = t.is_suitable(self.__job.spec)
            eprint(f"- {t.id}: {is_suitable} ({reason})")
            if is_suitable:
                suitable_targets[t.id] = t
        eprint("=== 2. Requesting scheduling for job using suitable targets ===")
        target: Target | None = None
        while not target:
            try:
                decision = self.__scheduler.request_schedule(
                    self.__job.spec, list(suitable_targets.keys())
                )
            except Exception:
                raise StatusException(os.EX_UNAVAILABLE)
            match decision:
                case scheduling_decision.Impossible():
                    raise Exception(
                        f"Can't schedule job spec {self.__job.spec.name} anywhere."
                    )
                case scheduling_decision.Assigned():  # Must come before Deferred, because is child class
                    target = suitable_targets[decision.target_id]
                    eprint(
                        f"Sheduler assigned {target.id} ({target.host}) in T minus {decision.wait_seconds} seconds"
                    )
                    self.__job.set_status(job.Status.Scheduled(target.id))
                    time.sleep(decision.wait_seconds)
                case scheduling_decision.Deferred():
                    wait_seconds = max(1, decision.wait_seconds)
                    eprint(
                        f"Scheduling deferred. (Re-attempting in {wait_seconds} sec)."
                    )
                    time.sleep(wait_seconds)
                case _:
                    raise NotImplementedError()
        eprint(
            f"=== 3. Copying input files to target {target.id} and run optional setup step ==="
        )
        with LockFile(
            f"meta-sched/{os.getuid()}/{target.id}:{self.__job.spec.name}.lock"
        ):
            src = self.__job.input
            dst = self.__job.input.parent
            target.transfer(src, dst, Target.TransferMode.UPLOAD)
            target.setup(self.__job)
        eprint(f"=== 4. Executing job on target {target.id} ===")
        target.execute(self.__job)
        eprint(f"=== 5. Fetching results from target {target.id} ===")
        assert self.__job.output
        src = self.__job.output
        dst = self.__job.output.parent
        target.transfer(src, dst, Target.TransferMode.DOWNLOAD)
        eprint(f"=== 6. Cleaning up files on target {target.id} ===")
        # TODO consider always cleaning up (even if job failed/was canceled)
        target.clean_up(self.__job)

    def run(self: Self) -> None:
        assert self.__job.output
        self.__job.output.mkdir(parents=True, exist_ok=True)
        pid_file = self.__job.output / ".pid"
        pid_file.write_text(str(os.getpid()))
        self.__job.set_status(job.Status.Pending())
        kwargs = (
            dict(
                stdout=self.__job.output / "stdout",
                stderr=self.__job.output / "stderr",
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
