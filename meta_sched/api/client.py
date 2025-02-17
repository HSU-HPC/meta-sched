import http
import http.client
from typing import Any, List, Self

import requests

from meta_sched.api import API
from meta_sched.submit.job import JobSpec  # TODO type?


class Client:
    def __init__(self: Self, host: str, port: int):
        self.__host = host
        self.__port = port

    def create_array_id(self: Self) -> str:
        response = requests.post(f"http://{self.__host}:{self.__port}/{API.PATH_JOBS}")
        if http.HTTPStatus.CREATED != response.status_code:
            raise http.client.error()
        content = response.json()
        if content["status"] != "success":
            raise RuntimeError(content)
        return str(content["data"])

    def get_targets(self: Self) -> Any:  # TODO type
        response = requests.get(
            f"http://{self.__host}:{self.__port}/{API.PATH_TARGETS}"
        )
        if http.HTTPStatus.OK != response.status_code:
            raise http.client.error()
        content = response.json()
        if content["status"] != "success":
            raise RuntimeError(content)
        return content["data"]

    def request_schedule(
        self: Self, job_spec: JobSpec, suitable_targets: List[str]
    ) -> Any:  # TODO type
        response = requests.put(
            f"http://{self.__host}:{self.__port}/{API.PATH_TARGETS}"
        )
        if http.HTTPStatus.OK != response.status_code:
            raise http.client.error()
        content = response.json()
        if content["status"] != "success":
            raise RuntimeError(content)
        return content["data"]
