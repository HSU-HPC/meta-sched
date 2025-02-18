import os
import sys
import time
import traceback
from typing import Self

from meta_sched.common import scheduling_decision
from meta_sched.common.job import Spec
from meta_sched.common.scheduler_interface import SchedulerInterface
from meta_sched.common.target import Target
from meta_sched.common.utils import InstantiationException
from meta_sched.submit.lock_file import LockFile
from meta_sched.submit.utils import RedirectOutputToFile


class Executor:
    __create_key = object()

    def __init__(
        self,
        create_key: object,
        job_spec: Spec,
        scheduler: SchedulerInterface,
        redirect_output: bool = False,
    ) -> None:
        if create_key != Executor.__create_key:
            raise InstantiationException(self)
        self.__job_spec = job_spec
        self.__scheduler = scheduler
        self.__redirect_output = redirect_output

    def __run(self: Self) -> None:
        print("=== 1. Selecting suitable targets for job ===", file=sys.stderr)
        suitable_targets = {t.id: t for t in self.__scheduler.targets}
        # Must be in config
        suitable_targets = {k: v for k, v in suitable_targets.items() if v.has_user}
        print(
            "=== 2. Requesting scheduling for job using suitable targets ===",
            file=sys.stderr,
        )
        target: Target | None = None
        while not target:
            decision = self.__scheduler.request_schedule(
                self.__job_spec, list(suitable_targets.keys())
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
            f"meta-sched/{os.getuid()}/{target.id}:{self.__job_spec.name}.lock"
        ):
            src = self.__job_spec.input
            dst = self.__job_spec.input.parent
            if 0 != target.transfer(src, dst, Target.TransferMode.UPLOAD):
                return
        print(f"=== 4. Executing job on target {target.id} ===", file=sys.stderr)
        # TODO Consider alternative:
        # Instead of running an interactive job on the target
        # * Create and submit a batch job
        # * Monitor the job state on the target
        # * Update the scheduler about the job state
        status = target.execute(self.__job_spec)
        if 0 != status:
            return
        print(f"=== 5. Fetching results from target {target.id} ===", file=sys.stderr)
        assert self.__job_spec.output
        src = self.__job_spec.output
        dst = self.__job_spec.output.parent
        status = target.transfer(src, dst, Target.TransferMode.DOWNLOAD)
        if 0 != status:
            return
        print(f"=== 6. Cleaning up files on target {target.id} ===", file=sys.stderr)
        target.clean_up(self.__job_spec)
        #
        # TODO Use smart/exp. back-off when polling
        # TODO Handle sigint (cancel job), sigterm (stop process), sigkill (?)
        pass

    def run(self: Self) -> None:
        assert self.__job_spec.output
        self.__job_spec.output.mkdir(parents=True, exist_ok=True)
        kwargs = (
            dict(
                stdout=self.__job_spec.output / "stdout",
                stderr=self.__job_spec.output / "stderr",
            )
            if self.__redirect_output
            else {}
        )
        with RedirectOutputToFile(**kwargs):
            try:
                self.__run()
            except Exception:
                print(traceback.format_exc(), file=sys.stderr)

    @classmethod
    def from_job_spec(
        cls,
        spec: str,
        scheduler: SchedulerInterface,
        array_id: int,
        array_idx: int,
        redirect_output: bool = False,
    ) -> Self:
        job_spec = Spec.load(spec)
        job_spec["array_id"] = array_id
        job_spec["array_idx"] = array_idx
        return cls(cls.__create_key, job_spec, scheduler, redirect_output)
