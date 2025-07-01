"""Module containing the model for the Meta Scheduler server component."""

import asyncio
from typing import Self, Set

from ms_common.job import Spec as JobSpec

from ms_server.job import Job, JobId


class Model:
    """
    Class representing the model for the Meta Scheduler server component.
    This class is responsible for storing the state (jobs, queues, etc.) used by the policy.
    """

    def __init__(self: Self) -> None:
        """
        Create a new instance of the model.
        TODO: In memory model, no persistence is implemented yet. (Make into abstract base class and rename this to InMemoryModel)
        """
        # TODO add persistence (e.g. using ZODB)
        self.__lock = asyncio.Lock()
        self.__jobs: dict[JobId, Job] = {}
        self.__next_array_id: int = 1

    async def create_job_array(
        self: Self, spec: JobSpec, available_targets: Set[str]
    ) -> str:
        """
        Create a new job array with the given specification and available targets for scheduling.

        Parameters
        ----------
        spec : JobSpec
            The specification of the job array to be created
        available_targets : Set[str]
            The set of target IDs which this job array may be assigned to

        Returns
        -------
        str
            The ID of the newly created job array
        """
        async with self.__lock:
            array_id = str(self.__next_array_id)
            self.__next_array_id += 1
            for i in range(spec.array_size):
                self.__jobs[array_id, i] = Job(spec, available_targets)
            return array_id

    async def get_pending_jobs(self: Self) -> Set[Job]:
        """
        Get all pending jobs pending scheduling.

        Returns
        -------
        Set[Job]
            All jobs that are pending scheduling
        """
        async with self.__lock:
            pending_jobs: Set[Job] = set()
            for job in self.__jobs.values():
                if await job.is_pending():
                    pending_jobs.add(job)
            return pending_jobs

    async def get_job(self: Self, job_id: JobId) -> Job:
        """
        Get a job by its array ID and index.

        Parameters
        ----------
        job_id : JobId
            The ID of the job to be retrieved, represented as a tuple (array_id, array_idx)

        Returns
        -------
        Job
            The job with the specified array ID and index
        """
        async with self.__lock:
            if job_id not in self.__jobs:
                raise KeyError(
                    f"Job with array ID {job_id[0]} and index {job_id[1]} not found."
                )
            return self.__jobs[job_id]

    async def remove_job(self: Self, job_id: JobId) -> None:
        """
        Remove a job by its array ID and index.

        Parameters
        ----------
        job_id : JobId
            The ID of the job to be removed, represented as a tuple (array_id, array_idx)

        Raises
        ------
        KeyError
            If the job with the specified array ID and index does not exist
        """
        async with self.__lock:
            if job_id not in self.__jobs:
                raise KeyError(
                    f"Job with array ID {job_id[0]} and index {job_id[1]} not found."
                )
            del self.__jobs[job_id]
