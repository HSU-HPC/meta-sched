"""Module containing the base class for implementing scheduling policies."""

from typing import Awaitable, Callable, List, Self

from ms_common.schemas import JobKey, SchedulingDecisionType, Target

from ms_server.model import Job

ScheduleJobCallback = Callable[[JobKey, SchedulingDecisionType], Awaitable[None]]


class Policy:
    """
    Base class for scheduling policies.
    """

    def __init__(
        self: Self, targets: List[Target], on_schedule_job: ScheduleJobCallback
    ):
        """
        Create a new instance of the scheduling policy

        Parameters
        ----------
        targets : List[Target]
            The list of targets which jobs may be assigned to
        on_schedule_job : ScheduleJobCallback
            Callback to apply scheduling decision to a job
        """
        if self.__class__ == Policy:
            raise NotImplementedError()
        self.on_schedule_job = on_schedule_job
        self._targets = {t.id: t for t in targets}

    @property
    def targets(self: Self) -> List[Target]:
        """
        Get all targets which jobs may be assigned to.

        Returns
        -------
        List[Target]
            The list of all targets which jobs may be assigned to
        """
        return list(self._targets.values())

    async def update(self: Self, pending_jobs: List[Job]) -> None:
        """
        Apply the scheduling policy to update the state of the scheduler.

        Parameters
        ----------
        pending_jobs : List[Job]
            The jobs which are pending scheduling

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

    async def schedule_job(self: Self, job: Job) -> None:
        """
        Schedule a job by assigning it according to the policy.

        Parameters
        ----------
        job : Job
            The job to schedule

        Raises
        ------
        NotImplementedError
            Must be implemented in concrete scheduling policy
        """
        raise NotImplementedError()

    async def update(self: Self, pending_jobs: List[Job]) -> None:
        """
        Apply greedy scheduling policy.

        Parameters
        ----------
        pending_jobs : List[Job]
            The jobs which are pending scheduling
        """
        for job in pending_jobs:
            await self.schedule_job(job)
