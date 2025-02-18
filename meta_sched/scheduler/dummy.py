import uuid
from typing import List, Self

from meta_sched.common.job import Spec
from meta_sched.common.scheduling_decision import (
    Assigned,
    Impossible,
    SchedulingDecision,
)
from meta_sched.common.target import Target
from meta_sched.scheduler import Scheduler


class Dummy(Scheduler):
    def __init__(self: Self, targets: List[Target] = []) -> None:
        self._targets = targets[:1]

    def create_array_id(self: Self) -> str:
        return str(uuid.uuid4())

    def request_schedule(
        self, job_spec: Spec, available_targets: List[str]
    ) -> SchedulingDecision:
        for target_id in available_targets:
            if target_id in [t.id for t in self.targets]:
                return Assigned(wait_seconds=0, target_id=target_id)
        return Impossible()
