from typing import List, Self

from meta_sched.submit.job import JobSpec
from meta_sched.submit.scheduler_interface import SchedulingDecision
from meta_sched.submit.target import Target


class Scheduler:
    def __init__(self: Self, targets: List[Target]):
        if self.__class__ == Scheduler:
            raise NotImplementedError()
        self.__targets = targets

    def request_schedule(
        self: Self, job_spec: JobSpec, suitable_targets: List[str]
    ) -> SchedulingDecision._Decision:
        raise NotImplementedError()
