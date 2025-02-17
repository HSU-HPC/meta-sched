import http
import re
from pathlib import Path
from typing import Self, Tuple

from flask import Flask, Response, jsonify, request

from meta_sched.names.name_provider import UniqueNameProvider


class Daemon:
    def __init__(self: Self, host: str, port: int, path: Path) -> None:
        self.__host = host
        self.__port = port
        print(f"Starting {__name__}.{self.__class__.__name__} at http://{host}:{port}")
        self.__path = path
        print(f"State stored at {self.__path}")
        self.__path.parent.mkdir(parents=True, exist_ok=True)
        self.__name_provider = UniqueNameProvider()
        self.__path.touch()
        self.__name_provider.load(self.__path)
        self.__app = Flask(f"{__package__}.{self.__class__.__name__}")
        self.__app.route("/", methods=["GET"])(self.get_new_name)

    def get_new_name(self: Self) -> Tuple[Response, http.HTTPStatus]:
        prefix = request.args.get("prefix", default="", type=str)
        pattern = "^[a-zA-Z0-9-_]+$"
        max_prefix_len = 50
        if not re.match(pattern, prefix) or len(prefix) > max_prefix_len:
            return jsonify(
                dict(
                    status="fail",
                    data=dict(
                        prefix=f'Argument "prefix" must not exceed a length of {max_prefix_len} and match {pattern}'
                    ),
                )
            ), http.HTTPStatus.BAD_REQUEST
        name = self.__name_provider.get_new_name(prefix)
        return jsonify(dict(status="success", data=name)), http.HTTPStatus.OK

    def run(self: Self) -> int:
        self.__app.run(host=self.__host, port=self.__port)
        return 0
