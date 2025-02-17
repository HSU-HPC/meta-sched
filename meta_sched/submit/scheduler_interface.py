import abc
from typing import Any, Dict, Iterable, Self

from meta_sched.submit.job import JobSpec
from meta_sched.submit.target import Target


class SchedulingDecision:
    class _Decision:
        def __init__(self: Self, **kwargs: Any) -> None:
            raise NotImplementedError()

        pass

    class Impossible(_Decision):
        def __init__(self: Self, reason: object | None = None) -> None:
            self.__reason = reason

        @property
        def reason(self: Self) -> object:
            return self.__reason

    class Deferred(_Decision):
        def __init__(self: Self, wait_seconds: int = 0) -> None:
            self.__wait_seconds = wait_seconds

        @property
        def wait_seconds(self: Self) -> int:
            return self.__wait_seconds

    class Assigned(_Decision):
        def __init__(self: Self, target_id: str, wait_seconds: int = 0) -> None:
            self.__target_id = target_id

        @property
        def target_id(self: Self) -> str:
            return self.__target_id

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
    def targets(self: Self) -> Dict[str, Target]:
        raise NotImplementedError()

    @abc.abstractmethod
    def request_schedule(
        self, job_spec: JobSpec, available_targets: Iterable[str]
    ) -> SchedulingDecisionType:
        raise NotImplementedError()


class Dummy(Base):
    def __init__(self: Self, target: Target | None = None) -> None:
        self.__targets = {}
        if target:
            self.__targets[target.id] = target

    @property
    def targets(self: Self) -> Dict[str, Target]:
        return self.__targets

    def request_schedule(
        self, job_spec: JobSpec, available_targets: Iterable[str]
    ) -> SchedulingDecisionType:
        for target_id in available_targets:
            if target_id in self.targets:
                return SchedulingDecision.Assigned(target_id=target_id)
        return SchedulingDecision.Impossible()
