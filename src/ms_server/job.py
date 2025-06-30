"""Module containing the Job class for the Meta Scheduler server component."""

import asyncio
from typing import Self, Set

from ms_common import job
from ms_common.scheduling_decision import SchedulingDecisionType


class Job:
    """
    Class representing a job for the scheduler.
    """

    # TODO make class thread safe (?)
    def __init__(self: Self, spec: job.Spec, available_targets: Set[str]) -> None:
        """
        Create a new job instance.

        Parameters
        ----------
        spec : job.Spec
            The specification of the job to be scheduled
        available_targets : Set[str]
            The set of target IDs which this job may be assigned to
        """
        self.__condition = asyncio.Condition()
        self.spec = spec
        self.available_targets = available_targets
        self.__scheduling_decision: SchedulingDecisionType | None = None

    @property
    def is_pending(self: Self) -> bool:
        """
        Check if this job is still pending scheduling.

        Returns
        -------
        bool
            True if this job is still pending scheduling, False otherwise
        """
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
