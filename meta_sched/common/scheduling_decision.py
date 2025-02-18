import abc
from dataclasses import dataclass
from typing import Any, Dict, Self

from meta_sched.common.serialization import Serializable


@dataclass(frozen=True)
class SchedulingDecision(Serializable):
    def __init__(self: Self) -> None:
        if self.__class__ == SchedulingDecision:
            raise NotImplementedError()

    def to_dict(self: Self) -> Dict[str, Any]:
        return self.__dict__ | {"decision": self.__class__.__name__}


@dataclass(frozen=True)
class Impossible(SchedulingDecision):
    reason: object | None = None


@dataclass(frozen=True)
class Deferred(SchedulingDecision):
    wait_seconds: int


@dataclass(frozen=True)
class Assigned(Deferred):
    target_id: str


class SchedulingDecisionFactory:
    @staticmethod
    def create(decision: str, **kwargs: Any) -> SchedulingDecision:
        kwargs = kwargs.copy()
        scheduling_decision_cls: abc.ABCMeta = {
            cls.__name__: cls for cls in [Impossible, Deferred, Assigned]
        }[decision]
        assert issubclass(scheduling_decision_cls, SchedulingDecision)
        return scheduling_decision_cls(**kwargs)
