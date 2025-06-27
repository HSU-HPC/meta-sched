"""Module containing the base class for implementing scheduling policies."""

from typing import List, Self, Set

from ms_common.target import Target

from ms_server.job import Job


class Policy:
    """
    Base class for scheduling policies.
    """

    def __init__(self: Self, targets: List[Target]):
        """
        Create a new instance of the scheduling policy

        Parameters
        ----------
        targets : List[Target]
            The list of targets which jobs may be assigned to
        """
        if self.__class__ == Policy:
            raise NotImplementedError()
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

    async def update(self: Self, pending_jobs: Set[Job]) -> None:
        """
        Apply the scheduling policy to update the state of the scheduler.

        Parameters
        ----------
        pending_jobs : Set[Job]
            The set of jobs which are pending scheduling

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

    async def update(self: Self, pending_jobs: Set[Job]) -> None:
        """
        Apply greedy scheduling policy.

        Parameters
        ----------
        pending_jobs : Set[Job]
            The set of jobs which are pending scheduling
        """
        for job in pending_jobs:
            await self.schedule_job(job)
