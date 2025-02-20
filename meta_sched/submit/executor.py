import os
import time
import traceback
from typing import Dict, Self

from meta_sched.common import scheduling_decision
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

    def __store_status(self: Self, status: str) -> None:
        status_file = self.__job.output / ".status"
        status_file.write_text(status)

    def __run(self: Self) -> None:
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
                    # TODO sleep by decision.wait_seconds
                case scheduling_decision.Deferred():
                    wait_seconds = max(1, decision.wait_seconds)
                    eprint(
                        f"Scheduling deferred. (Re-attempting in {wait_seconds} sec)."
                    )
                    time.sleep(wait_seconds)
                case _:
                    raise NotImplementedError()
        eprint(f"=== 3. Copying input files to target {target.id} ===")
        with LockFile(
            f"meta-sched/{os.getuid()}/{target.id}:{self.__job.spec.name}.lock"
        ):
            src = self.__job.input
            dst = self.__job.input.parent
            target.transfer(src, dst, Target.TransferMode.UPLOAD)
        eprint(f"=== 4. Executing job on target {target.id} ===")
        # TODO Consider alternative:
        # Instead of running an interactive job on the target
        # * Create and submit a batch job
        # * Monitor the job state on the target
        # * Update the scheduler about the job state
        self.__store_status(f"running on {target.id}")
        target.execute(self.__job)
        eprint(f"=== 5. Fetching results from target {target.id} ===")
        assert self.__job.output
        src = self.__job.output
        dst = self.__job.output.parent
        target.transfer(src, dst, Target.TransferMode.DOWNLOAD)
        eprint(f"=== 6. Cleaning up files on target {target.id} ===")
        target.clean_up(self.__job)
        #
        # TODO Use smart/exp. back-off when polling
        # TODO Handle sigint (cancel job), sigterm (stop process), sigkill (?)
        self.__store_status("completed")

    def run(self: Self) -> None:
        assert self.__job.output
        self.__job.output.mkdir(parents=True, exist_ok=True)
        pid_file = self.__job.output / ".pid"
        pid_file.write_text(str(os.getpid()))
        self.__store_status("pending")
        kwargs = (
            dict(
                stdout=self.__job.output / "stdout",
                stderr=self.__job.output / "stderr",
            )
            if self.__redirect_output
            else {}
        )
        with RedirectOutputToFile(**kwargs):
            try:
                self.__run()
            except Exception as e:
                status = -1
                if isinstance(e, StatusException):
                    status = e.status
                eprint(traceback.format_exc())
                self.__store_status(f"failed {status}")
        pid_file.unlink()
