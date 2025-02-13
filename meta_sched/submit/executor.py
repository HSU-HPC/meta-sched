import os
import sys
import time
import traceback
from pathlib import Path
from typing import Self

from meta_sched.submit import scheduler_interface
from meta_sched.submit.job import JobSpec
from meta_sched.submit.lock_file import LockFile
from meta_sched.submit.scheduler_interface import SchedulingDecision
from meta_sched.submit.target import Target
from meta_sched.submit.utils import InstantiationException, RedirectOutputToFile


class Executor:
    __create_key = object()

    def __init__(
        self,
        create_key: object,
        job_spec: JobSpec,
        scheduler: scheduler_interface.Base,
        redirect_output: bool = False,
    ) -> None:
        if create_key != Executor.__create_key:
            raise InstantiationException(self)
        self.__job_spec = job_spec
        self.__scheduler = scheduler
        self.__redirect_output = redirect_output

    def __run(self: Self) -> None:
        # 1. Select suitable targets
        suitable_targets = self.__scheduler.targets
        # Must be in config
        suitable_targets = {k: v for k, v in suitable_targets.items() if v.has_user}
        # 2. Await/poll* meta scheduler scheduled
        target: Target | None = None
        while not target:
            scheduling_decision = self.__scheduler.request_schedule(
                self.__job_spec, suitable_targets.keys()
            )
            match scheduling_decision:
                case SchedulingDecision.Impossible():
                    print("Can't schedule", file=sys.stderr)
                    return
                case SchedulingDecision.Deferred():
                    wait_seconds = max(1, scheduling_decision.wait_seconds)
                    print(f"Scheduling deferred (Re-attempting in {wait_seconds} sec)")
                    time.sleep(wait_seconds)
                case SchedulingDecision.Assigned():
                    target = scheduling_decision.target
                case _:
                    raise NotImplementedError()
        # 3. Copy to target
        with LockFile(
            f"meta-sched/{os.getuid()}/{target.id}:{self.__job_spec.name}.lock"
        ):
            src = JobSpec.get_user_jobs_dir() / self.__job_spec.input
            dst = Path(f"meta-sched/jobs/{self.__job_spec.input.parent}")  # TODO ?
            if 0 != target.transfer(src, dst, Target.TransferMode.UPLOAD):
                return
        # 4. Run job on target
        # TODO Consider alternative:
        # Instead of running an interactive job on the target
        # * Create and submit a batch job
        # * Monitor the job state on the target
        # * Update the scheduler about the job state
        target.execute(self.__job_spec)
        # 5. Copy back results
        output_name = self.__job_spec.output
        assert output_name
        src = Path(f"meta-sched/jobs/{output_name}")  # TODO ?
        dst = (JobSpec.get_user_jobs_dir() / output_name).parent
        target.transfer(src, dst, Target.TransferMode.DOWNLOAD)
        # 6. Clean up on target
        target.clean_up(self.__job_spec)
        #
        # TODO Use smart/exp. back-off when polling
        # TODO Handle sigint (cancel job), sigterm (stop process), sigkill (?)
        pass

    def run(self: Self) -> None:
        # TODO continue here
        output = self.__job_spec.output
        assert output
        output_dir = JobSpec.get_user_jobs_dir() / output
        output_dir.mkdir(parents=True, exist_ok=True)
        kwargs = (
            dict(
                stdout=output_dir / "stdout",
                stderr=output_dir / "stderr",
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
        scheduler: scheduler_interface.Base,
        local_array_id: int,
        array_idx: int,
        redirect_output: bool = False,
    ) -> Self:
        job_spec = JobSpec.load(spec)
        job_spec["local_array_id"] = local_array_id
        job_spec["array_idx"] = array_idx
        return cls(cls.__create_key, job_spec, scheduler, redirect_output)
