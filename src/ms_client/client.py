"""Module containing the meta scheduler HTTP API client."""

import http
import http.client
from typing import List, Self

import requests
from ms_common.job import Spec
from ms_common.scheduler_interface import SchedulerInterface
from ms_common.scheduling_decision import (SchedulingDecision,
                                           SchedulingDecisionFactory)
from ms_common.target import Target, TargetFactory

from ms_client.config import Config


class Client(SchedulerInterface):
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
        if content["status"] != "success":
            raise RuntimeError(content)
        return [TargetFactory.create(**t) for t in content["data"]]

    def create_array_id(self: Self) -> str:
        """
        Create a new unique identifier for a new job array.

        Returns
        -------
        str
            A new unique identifier for a job array
        """
        response = requests.post(f"{self.__endpoint}/jobs")
        if http.HTTPStatus.CREATED != response.status_code:
            raise http.client.error()
        content = response.json()
        if content["status"] != "success":
            raise RuntimeError(content)
        return str(content["data"]["array_id"])

    def request_schedule(
        self: Self, job_spec: Spec, available_targets: List[str]
    ) -> SchedulingDecision:
        """
        Apply scheduling policy.

        Parameters
        ----------
        job_spec : Spec
            The job specification
        available_targets : List[str]
            List of identifiers of targets available to the client for job submission

        Returns
        -------
        SchedulingDecision
            The scheduling decision based on the policy
        """
        response = requests.put(
            f"{self.__endpoint}/jobs",
            json=dict(
                job_spec=job_spec.__dict__,
                available_targets=available_targets,
            ),
        )
        if http.HTTPStatus.OK != response.status_code:
            raise http.client.error(response)
        content = response.json()
        if content["status"] != "success":
            raise RuntimeError(content)
        return SchedulingDecisionFactory.create(**content["data"])
