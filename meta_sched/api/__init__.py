import http
from os import PathLike
from pathlib import Path
from typing import Any, Self, Tuple

from flask import Flask, Response, jsonify, request

from meta_sched import env
from meta_sched.api.counter import PersistentCounter
from meta_sched.config import Config
from meta_sched.scheduler.base import Scheduler
from meta_sched.utils import try_become_root


class API:
    PATH_JOBS = "/jobs"
    PATH_TARGETS = "/targets"

    def __init__(
        self: Self, host: str, port: int, config_path: str | PathLike[Any]
    ) -> None:
        self.__host = host
        self.__port = port
        self.__app = Flask(f"{self.__class__.__qualname__}")
        self.__config = Config.load(config_path)
        self.__scheduler: Scheduler = self.__config.scheduler_class(self.__config)
        self.__config.counter_file.parent.mkdir(parents=True, exist_ok=True)
        self.__counter = PersistentCounter()
        self.__config.counter_file.touch()
        self.__counter.load(self.__config.counter_file)
        self.__app.route(API.PATH_TARGETS, methods=["GET"])(self.get_targets)
        # Globally unique job ids (TODO could use authentication to add meta-data/manipulate)
        self.__app.route(API.PATH_JOBS, methods=["POST"])(self.create_array_id)
        self.__app.route(API.PATH_JOBS, methods=["PUT"])(self.request_schedule)

    def get_targets(self: Self) -> Tuple[Response, http.HTTPStatus]:
        return jsonify(
            dict(status="success", data=self.__config.targets)
        ), http.HTTPStatus.OK

    def create_array_id(self: Self) -> Tuple[Response, http.HTTPStatus]:
        return jsonify(
            dict(status="success", data=self.__counter.get_next("job"))
        ), http.HTTPStatus.CREATED

    def request_schedule(self: Self) -> Tuple[Response, http.HTTPStatus]:
        data = request.json
        # TODO check if the array_id is known (has been created, has not been scheduled already)
        if (
            not isinstance(data, dict)
            or "job_spec" not in data
            or "suitable_targets" not in data
        ):
            return jsonify(
                dict(
                    status="fail",
                    data=dict(
                        prefix='Expected JSON: {"job_spec": {...}, "suitable_targets": [...]}'
                    ),
                )
            ), http.HTTPStatus.BAD_REQUEST
        job_spec = data["job_spec"]
        suitable_targets = data["suitable_targets"]
        target_ids = set([t.id for t in self.__config.targets])
        if any([t not in target_ids for t in suitable_targets]):
            return jsonify(
                dict(
                    status="fail",
                    data=dict(prefix="Unknown target(s)"),
                )
            ), http.HTTPStatus.BAD_REQUEST
        decision = self.__scheduler.request_schedule(job_spec, suitable_targets)
        return jsonify(dict(status="success", data=decision)), http.HTTPStatus.OK

    def run(self: Self) -> int:
        print(
            f"Starting {self.__class__.__qualname__} at http://{self.__host}:{self.__port}"
        )
        self.__app.run(host=self.__host, port=self.__port)
        return 0


def run_server() -> int:
    try_become_root()
    api = API(
        env.get("MS_API_HOST"),
        int(env.get("MS_API_PORT")),
        Path(env.get("MS_SCHEDD_CONFIG")).absolute(),
    )
    return api.run()  # TODO do not run forever (Ctrl+C -> store counter)
