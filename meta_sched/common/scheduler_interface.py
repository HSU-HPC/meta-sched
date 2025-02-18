import abc
from typing import List, Self

from meta_sched.common.job import Spec
from meta_sched.common.scheduling_decision import SchedulingDecision
from meta_sched.common.target import Target


class SchedulerInterface(abc.ABC):
    @property
    @abc.abstractmethod
    def targets(self: Self) -> List[Target]:
        raise NotImplementedError()

    @abc.abstractmethod
    def create_array_id(self: Self) -> str:
        raise NotImplementedError()

    @abc.abstractmethod
    def request_schedule(
        self: Self, job_spec: Spec, available_targets: List[str]
    ) -> SchedulingDecision:
        raise NotImplementedError()
