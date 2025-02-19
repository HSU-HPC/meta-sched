import http
import http.client
from typing import List, Self

import requests

from meta_sched.common.job import Spec
from meta_sched.common.scheduler_interface import SchedulerInterface
from meta_sched.common.scheduling_decision import (
    SchedulingDecision,
    SchedulingDecisionFactory,
)
from meta_sched.common.target import Target, TargetFactory


class Client(SchedulerInterface):
    def __init__(self: Self, host: str, port: int):
        self.__host = host
        self.__port = port

    @property
    def targets(self: Self) -> List[Target]:
        response = requests.get(f"http://{self.__host}:{self.__port}/targets")
        if http.HTTPStatus.OK != response.status_code:
            raise http.client.error()
        content = response.json()
        if content["status"] != "success":
            raise RuntimeError(content)
        return [TargetFactory.create(**t) for t in content["data"]]

    def create_array_id(self: Self) -> str:
        response = requests.post(f"http://{self.__host}:{self.__port}/jobs")
        if http.HTTPStatus.CREATED != response.status_code:
            raise http.client.error()
        content = response.json()
        if content["status"] != "success":
            raise RuntimeError(content)
        return str(content["data"]["array_id"])

    def request_schedule(
        self: Self, job_spec: Spec, available_targets: List[str]
    ) -> SchedulingDecision:
        response = requests.put(
            f"http://{self.__host}:{self.__port}/jobs",
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
