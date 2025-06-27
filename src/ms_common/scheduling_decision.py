"""Module containing custom data classes for representing scheduling decisions."""

from typing import Any, Dict, Literal, Self, Union

from pydantic import BaseModel, TypeAdapter

from ms_common.target import Target

class Impossible(BaseModel):
    """Scheduling decision indicating that a job cannot be scheduled (as requested)."""
    type: Literal["impossible"] = "impossible"
    reason: str | None = None


class Deferred(BaseModel):
    """Scheduling decision indicating that the request should be repeated later."""
    type: Literal["deferred"] = "deferred"
    wait_seconds: int = 0


class Assigned(BaseModel):
    """Scheduling decision indicating an assignment to a target for execution of the job."""
    type: Literal["assigned"] = "assigned"
    target: Target
    wait_seconds: int = 0

SchedulingDecisionType = Union[Impossible, Deferred, Assigned]
class SchedulingDecision:
    """Utility class for scheduling decisions."""

    def __init__(self: Self) -> None:
        """SchedulingDecision is not meant to be instantiated."""
        raise NotImplementedError("SchedulingDecision is a type alias, not a class.")

    @staticmethod
    def parse(data: Dict[str, Any]) -> SchedulingDecisionType:
        """Parse a scheduling decision from a dictionary.

        Parameters
        ----------
        data : Dict[str, Any]
            The dictionary containing the scheduling decision data
        
        Returns
        -------
        SchedulingDecisionType
            The parsed scheduling decision object
        """
        adapter: TypeAdapter[SchedulingDecisionType] = TypeAdapter(SchedulingDecisionType)
        return adapter.validate_python(data)
