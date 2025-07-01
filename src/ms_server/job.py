"""Module containing the Job class for the Meta Scheduler server component."""

import asyncio
from typing import Self, Set

from ms_common.job import Spec as JobSpec
from ms_common.scheduling_decision import SchedulingDecisionType


class Job:
    """
    Class representing a job for the scheduler.
    """

    # TODO make this an abstract base class and move it into model.py (notification may alternatively be done via pub/sub instead of condition variable)

    def __init__(self: Self, spec: JobSpec, available_targets: Set[str]) -> None:
        """
        Create a new job instance.

        Parameters
        ----------
        spec : JobSpec
            The specification of the job to be scheduled
        available_targets : Set[str]
            The set of target IDs which this job may be assigned to
        """
        self.__condition = asyncio.Condition()
        self.spec = spec
        self.available_targets = available_targets
        self.__scheduling_decision: SchedulingDecisionType | None = None
        self.__timestamp_start: int | None = None
        self.__timestamp_end: int | None = None

    @property
    def timestamp_start(self: Self) -> int | None:
        """
        Get the timestamp when this job was started.

        Returns
        -------
        int | None
            The start time of the job as a unix timestamp (seconds since epoch), or None if not started yet
        """
        return self.__timestamp_start

    async def set_timestamp_start(self: Self, timestamp: int) -> None:
        """
        Set the timestamp when this job was started.

        Parameters
        ----------
        timestamp : int
            The start time of the job as a unix timestamp (seconds since epoch)
        """
        assert self.__timestamp_start is None, (
            "Cannot set timestamp_start again, it is already set."
        )
        async with self.__condition:
            self.__timestamp_start = timestamp
            self.__condition.notify_all()

    @property
    def timestamp_end(self: Self) -> int | None:
        """
        Get the timestamp when this job was ended.

        Returns
        -------
        int | None
            The end time of the job as a unix timestamp (seconds since epoch), or None if not ended yet
        """
        return self.__timestamp_end

    async def set_timestamp_end(self: Self, timestamp: int) -> None:
        """
        Set the timestamp when this job was ended.

        Parameters
        ----------
        timestamp : int
            The end time of the job as a unix timestamp (seconds since epoch)
        """
        assert self.__timestamp_end is None, (
            "Cannot set timestamp_end again, it is already set."
        )
        assert self.timestamp_start is not None, (
            "Job must be started before it can be ended."
        )
        assert self.timestamp_start <= timestamp, (
            "Job end time must be after start time."
        )
        async with self.__condition:
            self.__timestamp_end = timestamp
            self.__condition.notify_all()

    async def reschedule(self: Self, available_targets: Set[str]) -> None:
        """
        Reschedule this job with a new set of available targets.

        Parameters
        ----------
        available_targets : Set[str]
            The new set of target IDs which this job may be assigned to
        """
        async with self.__condition:
            self.available_targets = available_targets
            self.__scheduling_decision = None
            self.__timestamp_start = None
            self.__timestamp_end = None
            self.__condition.notify_all()

    async def is_pending(self: Self) -> bool:
        """
        Check if this job is still pending scheduling.

        Returns
        -------
        bool
            True if this job is still pending scheduling, False otherwise
        """
        async with self.__condition:
            return self.__scheduling_decision is None

    async def get_scheduling_decision(self: Self) -> SchedulingDecisionType:
        """
        Get the current scheduling decision for this job.
        If no scheduling decision has been made yet, this will block until a decision is made.

        Returns
        -------
        SchedulingDecision
            The latest scheduling decision for this job
        """
        async with self.__condition:
            await self.__condition.wait_for(
                lambda: self.__scheduling_decision is not None
            )
            assert self.__scheduling_decision is not None  # for mypy
            return self.__scheduling_decision

    async def make_scheduling_decision(
        self: Self, decision: SchedulingDecisionType
    ) -> None:
        """
        Make a scheduling decision for this job.

        Parameters
        ----------
        decision : SchedulingDecision
            The scheduling decision to be made for this job
        """
        async with self.__condition:
            self.__scheduling_decision = decision
            self.__condition.notify_all()
