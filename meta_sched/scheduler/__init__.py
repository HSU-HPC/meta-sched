from typing import List, Self

from meta_sched.common.job import Spec
from meta_sched.common.scheduler_interface import SchedulerInterface
from meta_sched.common.scheduling_decision import SchedulingDecision
from meta_sched.common.target import Target


class Scheduler(SchedulerInterface):
    def __init__(self: Self, targets: List[Target]):
        if self.__class__ == Scheduler:
            raise NotImplementedError()
        self._targets = {t.id: t for t in targets}

    @property
    def targets(self: Self) -> List[Target]:
        return list(self._targets.values())

    def create_array_id(self: Self) -> str:
        raise NotImplementedError()

    def request_schedule(
        self: Self, job_spec: Spec, available_targets: List[str]
    ) -> SchedulingDecision:
        raise NotImplementedError()
