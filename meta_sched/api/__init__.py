import http
from multiprocessing import Process
from os import PathLike
from pathlib import Path
from typing import Any, Self, Tuple

from flask import Flask, Response, jsonify, request

from meta_sched.api.counter import PersistentCounter
from meta_sched.common.scheduler_interface import SchedulerInterface


class API:
    def __init__(
        self: Self,
        host: str,
        port: int,
        counter_file: str | PathLike[Any],
        scheduler: SchedulerInterface,
    ) -> None:
        self.__host = host
        self.__port = port
        self.__app = Flask(f"{self.__class__.__qualname__}")
        self.__scheduler = scheduler
        self.__counter_file = Path(counter_file)
        self.__counter_file.parent.mkdir(parents=True, exist_ok=True)
        self.__counter = PersistentCounter()
        self.__counter_file.touch()
        self.__counter.load(self.__counter_file)
        self.__app.route("/targets", methods=["GET"])(self.get_targets)
        self.__app.route("/jobs", methods=["POST"])(self.create_array_id)
        self.__app.route("/jobs", methods=["PUT"])(self.request_schedule)

    def get_targets(self: Self) -> Tuple[Response, http.HTTPStatus]:
        return jsonify(
            dict(status="success", data=[t.to_dict() for t in self.__scheduler.targets])
        ), http.HTTPStatus.OK

    def create_array_id(self: Self) -> Tuple[Response, http.HTTPStatus]:
        array_id = self.__counter.get_next("job")
        self.__counter.save(self.__counter_file)
        return jsonify(dict(status="success", data=array_id)), http.HTTPStatus.CREATED

    def request_schedule(self: Self) -> Tuple[Response, http.HTTPStatus]:
        data = request.json
        # TODO check if the array_id is known (has been created, has not been scheduled already)
        if (
            not isinstance(data, dict)
            or "job_spec" not in data
            or "available_targets" not in data
        ):
            return jsonify(
                dict(
                    status="fail",
                    data=dict(
                        prefix='Expected JSON: {"job_spec": {...}, "available_targets": [...]}'
                    ),
                )
            ), http.HTTPStatus.BAD_REQUEST
        job_spec = data["job_spec"]
        suitable_targets = data["available_targets"]
        target_ids = set([t.id for t in self.__scheduler.targets])
        if any([t not in target_ids for t in suitable_targets]):
            return jsonify(
                dict(
                    status="fail",
                    data=dict(prefix="Unknown target(s)"),
                )
            ), http.HTTPStatus.BAD_REQUEST
        decision = self.__scheduler.request_schedule(job_spec, suitable_targets)
        return jsonify(
            dict(status="success", data=decision.to_dict())
        ), http.HTTPStatus.OK

    def run(self: Self) -> None:
        print(
            f"Starting {self.__class__.__qualname__} at http://{self.__host}:{self.__port}"
        )
        self.__app.run(host=self.__host, port=self.__port)

    def start_process(self: Self) -> Process:
        process = Process(target=self.run)
        process.start()
        return process
