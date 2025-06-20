"""Module containing a dummy scheduling policy for testing and development."""

import random
import uuid
from typing import List, Self

from ms_common.job import Spec
from ms_common.scheduling_decision import (Assigned, Impossible,
                                           SchedulingDecision)
from ms_common.target import Target

from ms_server.scheduler import Scheduler


class Dummy(Scheduler):
    """Dummy scheduling policy which always assigns the same target."""

    def __init__(self: Self, targets: List[Target] = []) -> None:
        """
        Create a new instance of the scheduling policy

        Parameters
        ----------
        targets : List[Target]
            The list of targets (only the first is used)
        """
        super().__init__(
            targets[:1]
        )  # Always only the first target (Good for debugging)

    def create_array_id(self: Self) -> str:
        """
        Create a new identifier for a job array

        Returns
        -------
        str
            A new UUID v4
        """
        return str(uuid.uuid4())

    def request_schedule(
        self, job_spec: Spec, available_targets: List[str]
    ) -> SchedulingDecision:
        """
        Apply scheduling policy, assigning the job to the dummy target if available.

        Parameters
        ----------
        job_spec : Spec
            The job specification (Unused)
        available_targets : List[str]
            List of identifiers of targets available to the client for job submission

        Returns
        -------
        SchedulingDecision
            The scheduling decision based on the policy (assigned to dummy target or impossible)
        """
        random.shuffle(available_targets)
        for target_id in available_targets:
            if target_id in self._targets:
                return Assigned(wait_seconds=0, target_id=target_id)
        return Impossible()
