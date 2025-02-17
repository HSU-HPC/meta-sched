from typing import List, Self

from meta_sched.config import Config
from meta_sched.scheduler.base import Scheduler
from meta_sched.submit.job import JobSpec
from meta_sched.submit.scheduler_interface import SchedulingDecision


class RRScheduler(Scheduler):
    def __init__(self: Self, config: Config) -> None:
        self.__job_count = {t.id: 0 for t in config.targets}

    def request_schedule(
        self: Self, job_spec: JobSpec, suitable_targets: List[str]
    ) -> SchedulingDecision._Decision:
        targets = [t for t in suitable_targets if t in self.__job_count]
        if len(targets) == 0:
            return SchedulingDecision.Impossible()
        selected = 0
        for i in range(len(targets)):
            if self.__job_count[targets[selected]] > self.__job_count[targets[i]]:
                selected = i
        self.__job_count[targets[selected]] += 1
        return SchedulingDecision.Assigned(targets[selected])
