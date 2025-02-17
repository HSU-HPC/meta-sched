import http
import http.client
from typing import Self

import requests


class Client:
    def __init__(self: Self, host: str, port: int):
        self.__host = host
        self.__port = port

    def get_new_name(self: Self, prefix: str = "") -> str:
        response = requests.get(f"http://{self.__host}:{self.__port}/?prefix={prefix}")
        if http.HTTPStatus.OK != response.status_code:
            raise http.client.error()
        content = response.json()
        if content["status"] != "success":
            raise RuntimeError(content)
        return str(content["data"])
