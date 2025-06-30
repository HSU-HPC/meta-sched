"""Module containing the model for the Meta Scheduler server component."""

from typing import Self, Set, Tuple

from ms_common import job

from ms_server.job import Job


class Model:
    """
    Class representing the model for the Meta Scheduler server component.
    This class is responsible for storing the state (jobs, queues, etc.) used by the policy.
    """

    # TODO make class thread safe (?)

    def __init__(self: Self) -> None:
        """
        Create a new instance of the model.
        TODO: In memory model, no persistence is implemented yet.
        """
        # TODO add persistence (e.g. using ZODB)
        self.__jobs: dict[Tuple[str, int], Job] = {}
        self.__next_array_id: int = 1

    def create_job_array(
        self: Self, spec: job.Spec, available_targets: Set[str]
    ) -> str:
        """
        Create a new job array with the given specification and available targets for scheduling.

        Parameters
        ----------
        spec : job.Spec
            The specification of the job array to be created
        available_targets : Set[str]
            The set of target IDs which this job array may be assigned to

        Returns
        -------
        str
            The ID of the newly created job array
        """
        array_id = str(self.__next_array_id)
        self.__next_array_id += 1
        for i in range(spec.array_size):
            self.__jobs[array_id, i] = Job(spec, available_targets)
        return array_id

    @property
    def pending_jobs(self: Self) -> Set[Job]:
        """
        Get all pending jobs pending scheduling.

        Returns
        -------
        Set[Job]
            All jobs that are pending scheduling
        """
        return set(j for j in self.__jobs.values() if j.is_pending)

    # get using jobStore[array_id, array_idx] notation
    def get_job(self: Self, array_id: str, array_idx: int) -> Job:
        """
        Get a job by its array ID and index.

        Parameters
        ----------
        array_id : str
            The ID of the job array
        array_idx : int
            The index of the job within the array

        Returns
        -------
        Job
            The job with the specified array ID and index
        """
        if (array_id, array_idx) not in self.__jobs:
            raise KeyError(
                f"Job with array ID {array_id} and index {array_idx} not found."
            )
        return self.__jobs[array_id, array_idx]

    def remove_job(self: Self, array_id: str, array_idx: int) -> None:
        """
        Remove a job by its array ID and index.

        Parameters
        ----------
        array_id : str
            The ID of the job array
        array_idx : int
            The index of the job within the array

        Raises
        ------
        KeyError
            If the job with the specified array ID and index does not exist
        """
        if (array_id, array_idx) not in self.__jobs:
            raise KeyError(
                f"Job with array ID {array_id} and index {array_idx} not found."
            )
        del self.__jobs[array_id, array_idx]
