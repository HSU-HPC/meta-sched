"""Module containing the meta scheduler HTTP API."""

import http
import os
import sys
import threading
from multiprocessing import Process
from os import PathLike
from pathlib import Path
from typing import Any, Self, Tuple

from common import env
from common.job import Spec
from common.scheduler_interface import SchedulerInterface
from common.utils import eprint, try_become_root
from flask import Flask, Response, jsonify, request

from server.config import Config
from server.counter import PersistentCounter
from server.scheduler import Scheduler


class API:
    """
    Flask-based HTTP API for the meta-scheduler.
    """

    def __init__(
        self: Self,
        host: str,
        port: int,
        counter_file: str | PathLike[Any],
        scheduler: SchedulerInterface,
    ) -> None:
        """
        Create a new instance of the HTTP API.

        Parameters
        ----------
        host : str
            The hostname of the HTTP server (use "0.0.0.0" for public and "localhost" for private API)
        port : str
            The port of the HTTP server
        counter_file: str | PathLike[Any]
            The path at which to store the state of the job array counter for unique, sequential identifiers
        scheduler : SchedulerInterface
            The scheduling policy implementation to be applied
        """
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
        self.__lock = threading.Lock()

    def get_targets(self: Self) -> Tuple[Response, http.HTTPStatus]:
        """
        Get all targets which jobs may be assigned to. (API endpoint)

        Returns
        -------
        Tuple[Response, http.HTTPStatus]
            HTTP response and status containing the list of all targets which jobs may be assigned to
        """
        return jsonify(
            dict(status="success", data=[t.to_dict() for t in self.__scheduler.targets])
        ), http.HTTPStatus.OK

    def create_array_id(self: Self) -> Tuple[Response, http.HTTPStatus]:
        """
        Create a new unique identifier for a new job array. (API endpoint)

        Returns
        -------
        Tuple[Response, http.HTTPStatus]
            HTTP response and status containing the new new unique identifier for a job array
        """
        counter_key = "job"
        array_id = self.__counter.get_next(counter_key).split("-")[-1]
        self.__counter.save(self.__counter_file)
        data = dict(array_id=array_id)
        return jsonify(dict(status="success", data=data)), http.HTTPStatus.CREATED

    def request_schedule(self: Self) -> Tuple[Response, http.HTTPStatus]:
        """
        Apply scheduling policy. (API endpoint)

        Returns
        -------
        Tuple[Response, http.HTTPStatus]
            HTTP response and status containing the new new unique identifier for a job array
        """
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
        job_spec = Spec(**data["job_spec"])
        suitable_targets = data["available_targets"]
        target_ids = set([t.id for t in self.__scheduler.targets])
        if any([t not in target_ids for t in suitable_targets]):
            return jsonify(
                dict(
                    status="fail",
                    data=dict(prefix="Unknown target(s)"),
                )
            ), http.HTTPStatus.BAD_REQUEST
        with self.__lock:  # For multi-threaded WSGI servers
            decision = self.__scheduler.request_schedule(job_spec, suitable_targets)
        return jsonify(
            dict(status="success", data=decision.to_dict())
        ), http.HTTPStatus.OK

    def run(self: Self) -> None:
        """Run the HTTP API using the built-in server (blocking)."""
        print(
            f"Starting {self.__class__.__qualname__} at http://{self.__host}:{self.__port}"
        )
        self.__app.run(host=self.__host, port=self.__port)

    def start_process(self: Self) -> Process:
        """Start the HTTP API using the built-in server (non blocking).

        Returns
        -------
        Process
            The process executing the API
        """
        process = Process(target=self.run)
        process.start()
        return process


def main() -> int:
    """
    Execute HTTP API as root with parameters from the environment or default values.

    Returns
    -------
    int
        The exit code (Always 0, but server runs forever and does not return)
    """
    try_become_root(False)
    host = env.get("MS_SERVER_HOST")
    port = int(env.get("MS_SERVER_PORT"))
    key_env_conf = "MS_SCHED_CONFIG"
    config_path = Path(env.get(key_env_conf, Config.get_default_config_path()))
    if not (env.has(key_env_conf) or "--use-default-config" in sys.argv):
        eprint(
            f"No scheduler configuration was given in the environment variable {key_env_conf}."
        )
        eprint(
            "Using the following default configuration, requires the flag --use-default-config:"
        )
        eprint()
        config_str = config_path.read_text()
        eprint(config_str)
        return os.EX_NOINPUT
    config = Config.load(config_path)
    scheduler: Scheduler = config.scheduler_class(config.targets)
    try:
        api = API(host, port, config.counter_file, scheduler)
        api.run()
    except PermissionError as e:
        eprint(e)
        eprint()
        eprint("Maybe try again with the --sudo flag?")
    return os.EX_OK


if __name__ == "__main__":
    sys.exit(main())
