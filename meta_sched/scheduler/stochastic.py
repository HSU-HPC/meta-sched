import random
from typing import List

from meta_sched.common.job import Spec
from meta_sched.common.scheduling_decision import (
    Assigned,
    Impossible,
    SchedulingDecision,
)
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
