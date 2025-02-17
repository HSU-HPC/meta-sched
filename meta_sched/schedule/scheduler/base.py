from typing import Any, List, Self

from meta_sched.submit.job import JobSpec
from meta_sched.submit.scheduler_interface import SchedulingDecision


class Scheduler:
    def __init__(self: Self, **kwargs: Any):
        if self.__class__ == Scheduler:
            raise NotImplementedError()

    def request_schedule(
        self: Self, job_spec: JobSpec, suitable_targets: List[str]
    ) -> SchedulingDecision._Decision:
        raise NotImplementedError()
