"""Module containing the Job class for the Meta Scheduler server component."""

import abc
from typing import Any, Dict, List, Optional, Self, Set

from ms_common.schemas import JobKey, SchedulingDecisionType
from ms_common.schemas import Spec as JobSpec
from pydantic import BaseModel, ConfigDict


class Job(BaseModel):
    """
    Class representing a job for the scheduler.

    Attributes
    ----------
    token : str
        The random string required to look up the job
    array_id : int
        The job array identifier
    array_idx : int
        The index of the job in the job array
    spec : JobSpec
        The specification of the job to be scheduled
    available_targets : List[str]
        The set of target IDs which this job may be assigned to
    scheduling_decision : Optional[SchedulingDecisionType]
        The decision by the scheduling policy regarding this job or None, if the job has not yet been scheduled
    timestamp_start : Optional[int]
        The unix timestamp (seconds since epoch) of the job start or None, if the job has not yet started
    timestamp_end : Optional[int]
        The unix timestamp (seconds since epoch) of the job end or None, if the job has not yet ended
    """

    token: str
    array_id: int
    array_idx: int
    spec: JobSpec
    available_targets: List[str]
    scheduling_decision: Optional[SchedulingDecisionType]
    timestamp_start: Optional[int] = None
    timestamp_end: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

    @property
    def key(self: Self) -> JobKey:
        return JobKey(self.token, self.array_id, self.array_idx)


class Model(abc.ABC):
    async def create_job_array(
        self: Self, spec: JobSpec, available_targets: Set[str], token: str
    ) -> int:
        raise NotImplementedError()

    async def get_pending_jobs(self: Self) -> List[Job]:
        raise NotImplementedError()

    async def update_job(self: Self, job_key: JobKey, data: Dict[str, Any]) -> None:
        raise NotImplementedError()

    async def remove_job(self: Self, job_key: JobKey) -> None:
        raise NotImplementedError()

    async def await_scheduling_decision(
        self: Self, job_key: JobKey
    ) -> SchedulingDecisionType:
        raise NotImplementedError()
