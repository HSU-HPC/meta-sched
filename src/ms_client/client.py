"""Module containing the Meta Scheduler HTTP API client."""

import http
import http.client
import json
from typing import Dict, List, Set

import ms_common
import requests
from ms_common.schemas import (JobKey, ScheduleRequest, ScheduleResponse,
                               SchedulingDecision, SchedulingDecisionType,
                               Spec, Target, TargetStatus)

from ms_client.config import Config
from ms_client.scheduler_interface import SchedulerClientInterface


class Client(SchedulerClientInterface):
    """Client for the meta-scheduler HTTP API."""

    def __init__(self: "Client", config: Config):
        """
        Create a client for the HTTP server of the API.

        Parameters
        ----------
        endpoint : str
            The HTTP endpoint of the server
        """
        self.__endpoint = config.endpoint

    def check_version_ok(self: "Client") -> None:
        """
        Check if the server is running and if its version matches that of the client.

        Raises
        ------
        RuntimeError
            Error raised if a connection to/response from the server could not be obtained
        ValueError
            Error raised if the version of the server does not match the version of the client
        """
        response: requests.Response
        try:
            response = requests.get(f"{self.__endpoint}/version")
        except Exception:
            raise RuntimeError(
                f"Could check server version at {self.__endpoint}. (Is it running?)"
            )
        if http.HTTPStatus.OK != response.status_code:
            raise http.client.error(response.status_code, response.text)
        server_version = response.json()
        if ms_common.__version__ != server_version:
            raise ValueError(
                f"Version mismatch. (Using server version {server_version} with client version {ms_common.__version__}.)"
            )

    def update_target_status(
        self: "Client", target_id: str, target_status: TargetStatus, api_key: str
    ) -> None:
        """
        Update the status of a remote target at the Meta Scheduler server.

        Parameters
        ----------
        target_id : str
            The target for which the status should be updated
        target_status : TargetStatus
            The new status of the target
        api_key : str
            The API key to authenticate at the Meta Scheduler API
        """
        headers = {"X-API-Key": api_key}
        response = requests.put(
            f"{self.__endpoint}/targets/{target_id}/target_status",
            json=target_status.model_dump(),
            headers=headers,
        )
        if response.status_code not in [http.HTTPStatus.OK, http.HTTPStatus.NO_CONTENT]:
            raise http.client.error(response.status_code, response.text)

    @property
    def targets(self: "Client") -> List[Target]:
        """
        Get all targets which jobs may be assigned to.

        Returns
        -------
        List[Target]
            The list of all targets which jobs may be assigned to
        """
        response = requests.get(f"{self.__endpoint}/targets")
        if http.HTTPStatus.OK != response.status_code:
            raise http.client.error(response.status_code, response.text)
        content = response.json()
        return [Target.model_validate(o) for o in content]

    def submit_job_array(
        self: "Client", job_spec: Spec, available_targets: Set[str]
    ) -> ScheduleResponse:
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
        ScheduleResponse
            The response from the scheduler containing information to look up the jobs that were created
        """
        response = requests.post(
            f"{self.__endpoint}/jobs",
            json=ScheduleRequest(
                available_targets=list(available_targets), job_spec=job_spec
            ).model_dump(),
        )
        if http.HTTPStatus.CREATED != response.status_code:
            raise http.client.error(response.status_code, response.text)
        content = response.json()
        return ScheduleResponse.model_validate(content)

    def __get_job_request_headers(self: "Client", job_token: str) -> Dict[str, str]:
        """
        Create the HTTP headers for requests pertaining to a single job.

        Parameters
        ----------
        job_token : str
            The random string required to modify the job at the server

        Returns
        -------
        Dict[str, str]
            The HTTP headers for the request
        """
        return {"X-Job-Token": job_token}

    def poll_scheduling_decision(
        self: "Client",
        job_key: JobKey,
    ) -> SchedulingDecisionType:
        """
        Apply scheduling policy.

        Parameters
        ----------
        job_key : JobKey
            The token, array id, and array index required to look up the job

        Returns
        -------
        SchedulingDecision
            The scheduling decision based on the policy
        """
        connect_timeout = 5  # seconds
        response_timeout = 30  # seconds
        token, array_id, array_idx = job_key
        while True:
            try:
                response = requests.get(
                    f"{self.__endpoint}/jobs/{array_id}/{array_idx}/scheduling_decision",
                    stream=True,
                    timeout=(connect_timeout, response_timeout),
                    headers=self.__get_job_request_headers(token),
                )
            except requests.Timeout:
                # If the request times out, just retry
                continue
            if http.HTTPStatus.GATEWAY_TIMEOUT == response.status_code:
                continue
            if http.HTTPStatus.OK != response.status_code:
                raise http.client.error(response)
            last_line = list(response.iter_lines())[-1]
            content = json.loads(last_line)
            return SchedulingDecision.parse(content)

    def cancel_job(self: "Client", job_key: JobKey) -> None:
        """
        Cancel a job.

        Parameters
        ----------
        job_key : JobKey
            The token, array id, and array index required to look up the job
        """
        token, array_id, array_idx = job_key
        response = requests.delete(
            f"{self.__endpoint}/jobs/{array_id}/{array_idx}",
            headers=self.__get_job_request_headers(token),
        )
        if response.status_code not in [http.HTTPStatus.OK, http.HTTPStatus.NO_CONTENT]:
            raise http.client.error(response)

    def update_job_started(self: "Client", job_key: JobKey, timestamp: int) -> None:
        """
        Set the timestamp when a job was started.

        Parameters
        ----------
        job_key : JobKey
            The token, array id, and array index required to look up the job
        timestamp : int
            The start time of the job as a unix timestamp (seconds since epoch)
        """
        token, array_id, array_idx = job_key
        response = requests.put(
            f"{self.__endpoint}/jobs/{array_id}/{array_idx}?timestamp_start={timestamp}",
            headers=self.__get_job_request_headers(token),
        )
        if response.status_code not in [http.HTTPStatus.OK, http.HTTPStatus.NO_CONTENT]:
            raise http.client.error(response)

    def update_job_ended(self: "Client", job_key: JobKey, timestamp: int) -> None:
        """
        Set the timestamp when a job was ended.

        Parameters
        ----------
        job_key : JobKey
            The token, array id, and array index required to look up the job
        timestamp : int
            The end time of the job as a unix timestamp (seconds since epoch)
        """
        token, array_id, array_idx = job_key
        response = requests.put(
            f"{self.__endpoint}/jobs/{array_id}/{array_idx}?timestamp_end={timestamp}",
            headers=self.__get_job_request_headers(token),
        )
        if response.status_code not in [http.HTTPStatus.OK, http.HTTPStatus.NO_CONTENT]:
            raise http.client.error(response)

    def reschedule_job(
        self: "Client",
        job_key: JobKey,
        available_targets: Set[str],
    ) -> None:
        """
        Reschedule a job with the given array ID and index.

        Parameters
        ----------
        job_key : JobKey
            The token, array id, and array index required to look up the job
        available_targets : Set[str]
            The set of target IDs which this job may be assigned to
        """
        token, array_id, array_idx = job_key
        response = requests.put(
            f"{self.__endpoint}/jobs/{array_id}/{array_idx}/reschedule",
            json={"available_targets": list(available_targets)},
            headers=self.__get_job_request_headers(token),
        )
        if response.status_code not in [http.HTTPStatus.OK, http.HTTPStatus.NO_CONTENT]:
            raise http.client.error(response)
