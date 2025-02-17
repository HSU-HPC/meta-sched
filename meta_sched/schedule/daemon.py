import http
import importlib
import tomllib
import uuid
from pathlib import Path
from typing import Any, List, Self, Tuple

from flask import Flask, Response, jsonify, request

from meta_sched.schedule.scheduler.base import Scheduler


class Daemon:
    def __load_config(self: Self, path: Path) -> None:
        print("Loading config from", path)
        config = tomllib.loads(path.read_text())

        def require_config(
            config: Any,
            path: List[str | None],
            value_type: Any = None,
            options: List[Any] = [],
            path_str: str = "<root>",
        ) -> None:
            if len(path) == 0:
                if value_type and not isinstance(config, value_type):
                    raise ValueError(
                        f'Required config "{path_str} must be of type {value_type.__name__}"'
                    )
                if len(options) > 0 and config not in options:
                    raise ValueError(
                        f'Required config "{path_str} can only have these values: {options}"'
                    )
            else:
                keys: Any = path[:1]
                if isinstance(config, dict):
                    keys = config.keys() if keys[0] is None else keys
                elif isinstance(config, list):
                    keys = range(len(config)) if keys[0] is None else keys
                else:
                    raise ValueError(f'Required dict/list config "{path_str}"')
                for k in keys:
                    path_str = f"{path_str}/{k}"
                    try:
                        value = config[k]
                    except Exception:
                        raise ValueError(f'Required config "{path_str}"')
                    require_config(value, path[1:], value_type, options, path_str)

        require_config(config, ["scheduler_class"], str)
        require_config(config, ["targets", None, "id"], str)
        for i in range(len(config["targets"])):
            id = config["targets"][i]["id"]
            try:
                uuid.UUID(id)
            except ValueError:
                raise ValueError(f'Target id must be a valid UUID ("{id}" is not)')
            if id in [t["id"] for t in config["targets"][i + 1 :]]:
                raise ValueError(
                    f"Targets must have unique ids, but found multiple occurances of {id}"
                )
        require_config(config, ["targets", None, "host"], str)
        require_config(config, ["targets", None, "batch"], str, ["slurm"])

        self.__config = config

    def __init__(self: Self, host: str, port: int, config_path: Path) -> None:
        self.__host = host
        self.__port = port
        self.__load_config(config_path)
        module_name, class_name = self.__config["scheduler_class"].split(".")
        try:
            module = importlib.import_module(
                f"meta_sched.schedule.scheduler.{module_name}"
            )
            cls = getattr(module, class_name)
            self.__scheduler: Scheduler = cls(**self.__config)
        except (ModuleNotFoundError, AttributeError):
            raise ValueError(
                f'Could not load scheduler "{self.__config["scheduler_class"]}"'
            )
        self.__app = Flask(f"{__package__}.{self.__class__.__name__}")
        self.__app.route("/targets", methods=["GET"])(self.get_executors)
        self.__app.route("/scheduling_request", methods=["POST"])(self.request_schedule)

    def get_executors(self: Self) -> Tuple[Response, http.HTTPStatus]:
        return jsonify(
            dict(status="success", data=self.__config["executors"])
        ), http.HTTPStatus.OK

    def request_schedule(self: Self) -> Tuple[Response, http.HTTPStatus]:
        data = request.json
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
        target_ids = set([t["id"] for t in self.__config["targets"]])
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
        self.__app.run(host=self.__host, port=self.__port)
        return 0
