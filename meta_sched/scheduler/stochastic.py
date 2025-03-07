import random
from typing import List, Self

from meta_sched.common.job import Spec
from meta_sched.common.scheduling_decision import (
    Assigned,
    Impossible,
    SchedulingDecision,
)
from meta_sched.common.target import Target
from meta_sched.scheduler import Scheduler


class Uniform(Scheduler):
    def request_schedule(
        self, job_spec: Spec, available_targets: List[str]
    ) -> SchedulingDecision:
        random.shuffle(available_targets)
        for target_id in available_targets:
            if target_id in self._targets:
                return Assigned(wait_seconds=0, target_id=target_id)
        return Impossible()
    
class WeightedCores(Scheduler):
    def __init__(self: Self, targets: List[Target]) -> None:
        super().__init__(targets)
        self.__weights = {t.id: t.__nodes * t.__cores_per_node for t in targets}

    def request_schedule(
        self, job_spec: Spec, available_targets: List[str]
    ) -> SchedulingDecision:
        available_targets = [t for t in available_targets if t in self._targets]
        if len(available_targets) == 0:
            return Impossible()
        weights = [self.__weights[t] for t in available_targets]
        selected = random.choices(available_targets, weights, k=1)[0]
        return Assigned(wait_seconds=0, target_id=selected)
