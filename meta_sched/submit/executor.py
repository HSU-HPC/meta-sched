import os
import sys
import time
import traceback
from typing import Dict, Self

from meta_sched.common import scheduling_decision
from meta_sched.common.job import Instance as Job
from meta_sched.common.scheduler_interface import SchedulerInterface
from meta_sched.common.target import Target
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

    def __run(self: Self) -> None:
        print("=== 1. Selecting suitable targets for job ===", file=sys.stderr)
        suitable_targets: Dict[str, Target] = {}
        for t in self.__scheduler.targets:
            is_suitable, reason = t.is_suitable(self.__job.spec)
            print(f"- {t.id}: {is_suitable} ({reason})", file=sys.stderr)
            if is_suitable:
                suitable_targets[t.id] = t
        print(
            "=== 2. Requesting scheduling for job using suitable targets ===",
            file=sys.stderr,
        )
        target: Target | None = None
        while not target:
            decision = self.__scheduler.request_schedule(
                self.__job.spec, list(suitable_targets.keys())
            )
            match decision:
                case scheduling_decision.Impossible():
                    print("Can't schedule", file=sys.stderr)
                    return
                case scheduling_decision.Assigned():  # Must come before Deferred, because is child class
                    target = suitable_targets[decision.target_id]
                case scheduling_decision.Deferred():
                    wait_seconds = max(1, decision.wait_seconds)
                    print(
                        f"Scheduling deferred (Re-attempting in {wait_seconds} sec)",
                        file=sys.stderr,
                    )
                    time.sleep(wait_seconds)
                case _:
                    raise NotImplementedError()
        print(f"=== 3. Copying input files to target {target.id} ===", file=sys.stderr)
        with LockFile(
            f"meta-sched/{os.getuid()}/{target.id}:{self.__job.spec.name}.lock"
        ):
            src = self.__job.input
            dst = self.__job.input.parent
            if 0 != target.transfer(src, dst, Target.TransferMode.UPLOAD):
                return
        print(f"=== 4. Executing job on target {target.id} ===", file=sys.stderr)
        # TODO Consider alternative:
        # Instead of running an interactive job on the target
        # * Create and submit a batch job
        # * Monitor the job state on the target
        # * Update the scheduler about the job state
        status = target.execute(self.__job)
        if 0 != status:
            return
        print(f"=== 5. Fetching results from target {target.id} ===", file=sys.stderr)
        assert self.__job.output
        src = self.__job.output
        dst = self.__job.output.parent
        status = target.transfer(src, dst, Target.TransferMode.DOWNLOAD)
        if 0 != status:
            return
        print(f"=== 6. Cleaning up files on target {target.id} ===", file=sys.stderr)
        target.clean_up(self.__job)
        #
        # TODO Use smart/exp. back-off when polling
        # TODO Handle sigint (cancel job), sigterm (stop process), sigkill (?)
        pass

    def run(self: Self) -> None:
        assert self.__job.output
        self.__job.output.mkdir(parents=True, exist_ok=True)
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
            except Exception:
                print(traceback.format_exc(), file=sys.stderr)
