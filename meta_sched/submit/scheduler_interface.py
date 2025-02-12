import abc
import uuid
from typing import Any, Dict, Iterable, Self

from meta_sched.submit.job import JobSpec
from meta_sched.submit.target import Target


class SchedulingDecision:
    class __Decision:
        def __init__(self: Self, **kwargs: Any) -> None:
            raise NotImplementedError()

        pass

    class Impossible(__Decision):
        def __init__(self: Self, reason: object | None = None) -> None:
            self.__reason = reason

        @property
        def reason(self: Self) -> object:
            return self.__reason

    class Deferred(__Decision):
        def __init__(self: Self, wait_seconds: int = 0) -> None:
            self.__wait_seconds = wait_seconds

        @property
        def wait_seconds(self: Self) -> int:
            return self.__wait_seconds

    class Assigned(__Decision):
        def __init__(self: Self, target: Target, wait_seconds: int = 0) -> None:
            self.__target = target

        @property
        def target(self: Self) -> Target:
            return self.__target

    def __init__(self: Self, **kwargs: Any) -> None:
        if self.__class__ == SchedulingDecision:
            raise Exception(f"Cannot create instance of {self.__class__.__name__}")


SchedulingDecision.Impossible.__bases__ = (SchedulingDecision,)
SchedulingDecision.Deferred.__bases__ = (SchedulingDecision,)
SchedulingDecision.Assigned.__bases__ = (SchedulingDecision,)

SchedulingDecisionType = (
    SchedulingDecision.Impossible
    | SchedulingDecision.Deferred
    | SchedulingDecision.Assigned
)


class Base(abc.ABC):
    @property
    @abc.abstractmethod
    def targets(self: Self) -> Dict[uuid.UUID, Target]:
        raise NotImplementedError()

    @abc.abstractmethod
    def request_schedule(
        self, job_spec: JobSpec, available_targets: Iterable[uuid.UUID]
    ) -> SchedulingDecisionType:
        raise NotImplementedError()


class Dummy(Base):
    def __init__(self: Self, target: Target | None = None) -> None:
        self.__targets = {}
        if target:
            self.__targets[target.id] = target

    @property
    def targets(self: Self) -> Dict[uuid.UUID, Target]:
        return self.__targets

    def request_schedule(
        self, job_spec: JobSpec, available_targets: Iterable[uuid.UUID]
    ) -> SchedulingDecisionType:
        for target_id in available_targets:
            if target_id in self.targets:
                return SchedulingDecision.Assigned(target=self.targets[target_id])
        return SchedulingDecision.Impossible()
