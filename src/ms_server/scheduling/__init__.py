"""Module containing the base class for implementing scheduling policies."""

from typing import Awaitable, Callable, List

from ms_common.schemas import JobKey, SchedulingDecisionType

from ms_server.model import Job, TargetsStatus

ScheduleJobCallback = Callable[[JobKey, SchedulingDecisionType], Awaitable[None]]


class Policy:
    """
    Base class for scheduling policies.
    """

    def __init__(self: "Policy", on_schedule_job: ScheduleJobCallback):
        """
        Create a new instance of the scheduling policy

        Parameters
        ----------
        on_schedule_job : ScheduleJobCallback
            Callback to apply scheduling decision to a job
        """
        if self.__class__ == Policy:
            raise NotImplementedError()
        self.on_schedule_job = on_schedule_job

    async def update(
        self: "Policy",
        pending_jobs: List[Job],
        decided_jobs: List[Job],
        targets_status: TargetsStatus,
    ) -> None:
        """
        Apply the scheduling policy to update the state of the scheduler.

        Parameters
        ----------
        pending_jobs : List[Job]
            The jobs which are pending scheduling
        decided_jobs : List[Job]
            The jobs for which are scheduling decision has already been made
        targets_status : TargetsStatus
            A mapping from target IDs to the corresponding status if available
        Raises
        ------
        NotImplementedError
            Must be implemented in concrete scheduling policy
        """
        raise NotImplementedError()


class GreedyPolicy(Policy):
    """
    This scheduling policy immediately assigns jobs in no particular order according to the policy.
    """

    async def schedule_job(
        self: "GreedyPolicy",
        job: Job,
        decided_jobs: List[Job],
        targets_status: TargetsStatus,
    ) -> None:
        """
        Schedule a job by assigning it according to the policy.

        Parameters
        ----------
        job : Job
            The job to schedule
        decided_jobs : List[Job]
            The jobs for which are scheduling decision has already been made
        targets_status : TargetsStatus
            A mapping from target IDs to the corresponding status if available

        Raises
        ------
        NotImplementedError
            Must be implemented in concrete scheduling policy
        """
        raise NotImplementedError()

    async def update(
        self: "GreedyPolicy",
        pending_jobs: List[Job],
        decided_jobs: List[Job],
        targets_status: TargetsStatus,
    ) -> None:
        """
        Apply the scheduling policy to update the state of the scheduler.

        Parameters
        ----------
        pending_jobs : List[Job]
            The jobs which are pending scheduling
        decided_jobs : List[Job]
            The jobs for which are scheduling decision has already been made
        targets_status : TargetsStatus
            A mapping from target IDs to the corresponding status if available
        Raises
        ------
        NotImplementedError
            Must be implemented in concrete scheduling policy
        """
        for job in pending_jobs:
            await self.schedule_job(job, decided_jobs, targets_status)
