"""Module containing the Meta Scheduler HTTP API client."""

import http
import http.client
import time
from typing import List, Self, Set

import requests
from ms_common.job import Spec
from ms_common.scheduling_decision import (Deferred, SchedulingDecision,
                                           SchedulingDecisionType)
from ms_common.target import Target

from ms_client.config import Config
from ms_client.scheduler_interface import SchedulerClientInterface


class Client(SchedulerClientInterface):
    """Client for the meta-scheduler HTTP API."""

    def __init__(self: Self, config: Config):
        """
        Create a client for the HTTP server of the API.

        Parameters
        ----------
        endpoint : str
            The HTTP endpoint of the server
        """
        self.__endpoint = config.endpoint

    @property
    def targets(self: Self) -> List[Target]:
        """
        Get all targets which jobs may be assigned to.

        Returns
        -------
        List[Target]
            The list of all targets which jobs may be assigned to
        """
        response = requests.get(f"{self.__endpoint}/targets")
        if http.HTTPStatus.OK != response.status_code:
            raise http.client.error()
        content = response.json()
        return [Target.model_validate(o) for o in content]

    def submit_job_array(
        self: Self, job_spec: Spec, available_targets: Set[str]
    ) -> str:
        """
        Create a new unique identifier for a new job array and schedule the corresponding jobs.

        Parameters
        ----------
        job_spec : Spec
            The job specification
        available_targets : List[str]
            List of identifiers of targets available to the client for job submission

        Returns
        -------
        str
            A new unique identifier for a job array
        """
        response = requests.post(
            f"{self.__endpoint}/jobs",
            json={
                "job_spec": job_spec.model_dump(),
                "available_targets": list(available_targets),
            },
        )
        if http.HTTPStatus.CREATED != response.status_code:
            raise http.client.error()
        content = response.json()
        if content["status"] != "success":
            raise RuntimeError(content)
        return str(content["data"]["array_id"])

    def poll_scheduling_decision(
        self: Self, array_id: str, array_idx: int
    ) -> SchedulingDecisionType:
        """
        Apply scheduling policy.

        Parameters
        ----------
        array_id : str
            The unique identifier of the job array
        array_idx : int
            The index of the job in the job array

        Returns
        -------
        SchedulingDecision
            The scheduling decision based on the policy
        """
        timeout = 60  # seconds
        while True:
            try:
                response = requests.get(
                    f"{self.__endpoint}/jobs/{array_id}/{array_idx}/scheduling_decision",
                    timeout=timeout,
                )
            except requests.Timeout:
                # If the request times out, just retry
                continue
            if http.HTTPStatus.OK != response.status_code:
                raise http.client.error(response)
            content = response.json()
            decision = SchedulingDecision.parse(content)
            if isinstance(decision, Deferred):
                time.sleep(decision.wait_seconds)
            else:
                return decision

    def cancel_job(self: Self, array_id: str, array_idx: int) -> None:
        """
        Cancel a job.

        Parameters
        ----------
        array_id : str
            The unique identifier of the job array
        array_idx : int
            The index of the job in the job array
        """
        response = requests.delete(
            f"{self.__endpoint}/jobs/{array_id}/{array_idx}",
        )
        if http.HTTPStatus.NO_CONTENT != response.status_code:
            raise http.client.error(response)

    def update_job_started(
        self: Self, array_id: str, array_idx: int, timestamp: int
    ) -> None:
        """
        Set the timestamp when a job was started.

        Parameters
        ----------
        array_id : str
            The unique identifier of the job array
        array_idx : int
            The index of the job in the job array
        timestamp : int
            The start time of the job as a unix timestamp (seconds since epoch)
        """
        response = requests.put(
            f"{self.__endpoint}/jobs/{array_id}/{array_idx}?timestamp_start={timestamp}"
        )
        if http.HTTPStatus.NO_CONTENT != response.status_code:
            raise http.client.error(response)

    def update_job_ended(
        self: Self, array_id: str, array_idx: int, timestamp: int
    ) -> None:
        """
        Set the timestamp when a job was ended.

        Parameters
        ----------
        array_id : str
            The unique identifier of the job array
        array_idx : int
            The index of the job in the job array
        timestamp : int
            The end time of the job as a unix timestamp (seconds since epoch)
        """
        response = requests.put(
            f"{self.__endpoint}/jobs/{array_id}/{array_idx}?timestamp_end={timestamp}"
        )
        if http.HTTPStatus.NO_CONTENT != response.status_code:
            raise http.client.error(response)

    def reschedule_job(
        self: Self, array_id: str, array_idx: int, available_targets: Set[str]
    ) -> None:
        """
        Reschedule a job with the given array ID and index.

        Parameters
        ----------
        array_id : str
            The unique identifier of the job array
        array_idx : int
            The index of the job in the job array
        available_targets : Set[str]
            The set of target IDs which this job may be assigned to
        """
        response = requests.put(
            f"{self.__endpoint}/jobs/{array_id}/{array_idx}/reschedule",
            json={"available_targets": list(available_targets)},
        )
        if http.HTTPStatus.NO_CONTENT != response.status_code:
            raise http.client.error(response)
