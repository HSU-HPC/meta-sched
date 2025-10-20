"""Module containing scheduling policy implementations which use randomness."""

import random
from typing import List

from ms_common.schemas import Assigned, Target

from ms_server.model import Job, TargetsStatus
from ms_server.scheduling import GreedyPolicy, ScheduleJobCallback


class Uniform(GreedyPolicy):
    """
    This scheduling policy assigns jobs using a uniform random distribution per scheduling request.
    (Note that this may result in a non-uniform distribution across all targets depending on the available ones.)
    """

    async def schedule_job(
        self: "Uniform",
        job: Job,
        decided_jobs: List[Job],
        targets_status: TargetsStatus,
    ) -> None:
        """
        Schedule a job by assigning it to a random target from the available ones.

        Parameters
        ----------
        job : Job
            The job to be scheduled
        decided_jobs : List[Job]
            The jobs for which are scheduling decision has already been made
        targets_status : TargetsStatus
            A mapping from target IDs to the corresponding status if available
        """
        available_targets = list(job.available_targets)  # Make an orderable copy
        random.shuffle(available_targets)
        decision = Assigned(target_id=available_targets[0])
        await self.on_schedule_job(job.key, decision)


class WeightedByCores(GreedyPolicy):
    """
    This scheduling policy assigns jobs randomly per scheduling request proportional to the core count of each target.
    (Note that this may result in disproportionate distribution across all targets depending on the available ones.)
    """

    async def schedule_job(
        self: "WeightedByCores",
        job: Job,
        decided_jobs: List[Job],
        targets_status: TargetsStatus,
    ) -> None:
        """
        Schedule a job by assigning it to a target using a weighted random selection based on core count.

        Parameters
        ----------
        job : Job
            The job to be scheduled
        decided_jobs : List[Job]
            The jobs for which are scheduling decision has already been made
        targets_status : TargetsStatus
            A mapping from target IDs to the corresponding status if available
        """
        targets_weights = {t.id: t.nodes * t.cores_per_node for t in targets_status}
        weights = [targets_weights[t] for t in job.available_targets]
        target_id = random.choices(job.available_targets, weights, k=1)[0]
        decision = Assigned(target_id=target_id)
        await self.on_schedule_job(job.key, decision)


class WeightedByCoresAvailability(GreedyPolicy):
    """
    This scheduling policy assigns jobs randomly per scheduling request proportional to the amount of currently unused cores on each target.
    (Note that this may result in disproportionate distribution across all targets depending on the available ones.)

    Policy Parameters
    -----------------
    epsilon : float = 1e-9
        The minimum weight for each target for sampling
    unavailable_discount_factor : float = 0.1
        The discount factor for unavailable cores (Used by other jobs/nodes under maintenance)
    """

    def __init__(
        self: "WeightedByCoresAvailability", on_schedule_job: ScheduleJobCallback
    ):
        """
        Create a new instance of the scheduling policy

        Parameters
        ----------
        on_schedule_job : ScheduleJobCallback
            Callback to apply scheduling decision to a job
        """
        super(WeightedByCoresAvailability, self).__init__(on_schedule_job)
        self.epsilon = 1e-9
        self.unavailable_discount_factor = 0.1

    async def schedule_job(
        self: "WeightedByCoresAvailability",
        job: Job,
        decided_jobs: List[Job],
        targets_status: TargetsStatus,
    ) -> None:
        """
        Schedule a job by assigning it to a target using a weighted random selection based on core count and availability.

        Parameters
        ----------
        job : Job
            The job to be scheduled
        decided_jobs : List[Job]
            The jobs for which are scheduling decision has already been made
        targets_status : TargetsStatus
            A mapping from target IDs to the corresponding status if available
        """

        def get_target_weights(t: Target) -> float:
            """
            Compute weight of target for sampling.

            Parameters
            ----------
            t : Target
                The target

            Returns
            -------
            float
                The weight of the target
            """
            n_cores = t.nodes * t.cores_per_node
            status = targets_status[t]
            n_cores_avail: int
            if not status:
                # Assume all nodes are available
                n_cores_avail = n_cores
            else:
                n_cores_avail = status.nodes_available * t.cores_per_node
            weight = (
                n_cores_avail
                + (n_cores - n_cores_avail) * self.unavailable_discount_factor
            )
            # Ensure all weights are greater than zero
            return max(weight, self.epsilon)

        targets_weights = {t.id: get_target_weights(t) for t in targets_status}
        weights = [targets_weights[t] for t in job.available_targets]
        target_id = random.choices(job.available_targets, weights, k=1)[0]
        decision = Assigned(target_id=target_id)
        await self.on_schedule_job(job.key, decision)
