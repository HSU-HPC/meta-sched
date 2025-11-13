"""Module containing scheduling policy implementations which use randomness."""

import json
import os
import random
import time
from typing import List

from ms_common.schemas import Assigned, Target
from ms_common.utils import eprint

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
        The minimum weight for each target for sampling (Should not be zero!)
    weight_unavailable : float = 0.1
        The weighting factor for unavailable cores (Used by other jobs/nodes under maintenance)
    amplification_renewable : float = 0.5
        Additional weighting factor for renewable powered cores
    threshold_reliability_renewable : float = 0.8
        Threshold below which to disregard forecasts
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
        self.weight_unavailable = 0.1
        self.amplification_renewable = 0.5
        self.threshold_reliability_renewable = 0.8

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
            weight = n_cores_avail + (n_cores - n_cores_avail) * self.weight_unavailable
            # Add amplification of renewable powered cores
            # (Must be available continuously)
            n_cores_avail_renewable: float = 0
            timestamp_earliest_done = time.time() + job.spec.get_target_seconds(
                t, job.array_idx
            )
            for i, forecast in enumerate(status.power_forecasts if status else []):
                if (
                    forecast.timestamp > timestamp_earliest_done
                    or forecast.reliability < self.threshold_reliability_renewable
                ):
                    break
                n_cores_avail_renewable = (
                    forecast.nodes_renewable_powered * t.cores_per_node
                    if i == 0
                    else min(
                        n_cores_avail,
                        forecast.nodes_renewable_powered * t.cores_per_node,
                    )
                )
            weight += n_cores_avail_renewable * self.amplification_renewable
            # Ensure all weights are greater than zero
            return weight

        targets_weights = {
            t.id: get_target_weights(t)
            for t in targets_status
            if t.id in set(job.available_targets)
        }
        weights = [targets_weights[t] for t in job.available_targets]
        target_id = random.choices(job.available_targets, weights, k=1)[0]

        log_data = dict(
            timestamp_ns=int(time.time_ns()),
            job=dict(array_id=job.array_id, array_idx=job.array_idx),
            targets_weights=targets_weights,
            selected_target_id=target_id,
        )
        jsonl_line = json.dumps(log_data)
        eprint(jsonl_line)

        # e.g. /var/log/meta-sched-policy.log
        filename = os.getenv("MS_POLICY_LOG")
        if filename:
            with open(filename, "a") as file:
                file.write(jsonl_line)
                file.write("\n")

        decision = Assigned(target_id=target_id)
        await self.on_schedule_job(job.key, decision)
