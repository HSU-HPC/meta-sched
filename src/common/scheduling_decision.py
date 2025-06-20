"""Module containing custom data classes for representing scheduling decisions."""

import abc
from dataclasses import dataclass
from typing import Any, Dict, Self

from common.serialization import Serializable


@dataclass(frozen=True)
class SchedulingDecision(Serializable):
    """Base class for scheduling decisions."""

    def __init__(self: Self) -> None:
        """
        Create a new instance of the scheduling decision.

        Raises
        ------
        NotImplementedError
            The base class may not be instantiated
        """
        if self.__class__ == SchedulingDecision:
            raise NotImplementedError()

    def to_dict(self: Self) -> Dict[str, Any]:
        """
        Create a dictionary representation of the object.

        Returns
        -------
        Dict[str, Any]
            The dictionary representing the object
        """
        return self.__dict__ | {"decision": self.__class__.__name__}


@dataclass(frozen=True)
class Impossible(SchedulingDecision):
    """Scheduling decision indicating that a job cannot be scheduled (as requested)."""

    reason: object | None = None


@dataclass(frozen=True)
class Deferred(SchedulingDecision):
    """Scheduling decision indicating that the request should be repeated later."""

    wait_seconds: int


@dataclass(frozen=True)
class Assigned(Deferred):
    """Scheduling decision indicating an assignment to a target for execution of the job."""

    target_id: str


class SchedulingDecisionFactory:
    """
    Class for instantiating scheduling decisions based on their name.
    """

    @staticmethod
    def create(decision: str, **kwargs: Any) -> SchedulingDecision:
        """
        Create a new scheduling decision.

        Parameters
        ----------
        decision : str
            Class name of the scheduling decision
        **kwargs : Any
            Named arguments passed to the constructor of the scheduling decision

        Returns
        -------
        SchedulingDecision
            The scheduling decision
        """
        kwargs = kwargs.copy()
        scheduling_decision_cls: abc.ABCMeta = {
            cls.__name__: cls for cls in [Impossible, Deferred, Assigned]
        }[decision]
        assert issubclass(scheduling_decision_cls, SchedulingDecision)
        return scheduling_decision_cls(**kwargs)
