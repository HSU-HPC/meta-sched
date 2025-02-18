from typing import List, Self

from meta_sched.common.job import Spec
from meta_sched.common.scheduling_decision import (
    Assigned,
    Impossible,
    SchedulingDecision,
)
from meta_sched.common.target import Target
from meta_sched.scheduler import Scheduler


class RRScheduler(Scheduler):
    def __init__(self: Self, targets: List[Target]) -> None:
        super().__init__(targets)
        self.__job_count = {t.id: 0 for t in targets}

    def request_schedule(
        self: Self, job_spec: Spec, available_targets: List[str]
    ) -> SchedulingDecision:
        target_ids = [t for t in available_targets if t in self.__job_count]
        if len(target_ids) == 0:
            return Impossible()
        selected = 0
        for i in range(len(target_ids)):
            if self.__job_count[target_ids[selected]] > self.__job_count[target_ids[i]]:
                selected = i
        self.__job_count[target_ids[selected]] += 1
        return Assigned(wait_seconds=0, target_id=target_ids[selected])
