import http
import signal
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from typing import Any, Self

from meta_sched.names.name_provider import NameProvider, UniqueNameProvider


class Daemon:
    class _Server(HTTPServer):
        def __init__(
            self: Self,
            server_address: Any,
            name_provider: NameProvider,
            handler_class: Any,
            bind_and_activate: bool = True,
        ) -> None:
            self.__name_provider = name_provider
            super().__init__(server_address, handler_class, bind_and_activate)

        @property
        def name_provider(self: Self) -> NameProvider:
            return self.__name_provider

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self: Self) -> None:
            key = str(self.path)[1:]
            if len(key) > 50 or any(not (c.isalnum() or c in ["-_"]) for c in key):
                self.send_error(http.HTTPStatus.BAD_REQUEST, "Path is not a valid key!")
                return
            server = self.server
            assert isinstance(server, Daemon._Server)
            name = server.name_provider.get_new_name(key)
            self.send_response(http.HTTPStatus.OK)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(name.encode())

    def __init__(self: Self, host: str, port: int, path: Path) -> None:
        print(f"Starting {__name__}.{self.__class__.__name__} at http://{host}:{port}")
        self.__path = path
        print(f"State stored at {self.__path}")
        self.__path.parent.mkdir(parents=True, exist_ok=True)
        self.__name_provider = UniqueNameProvider()
        self.__path.touch()
        self.__name_provider.load(self.__path)
        self.__server = self._Server((host, port), self.__name_provider, self._Handler)

    def shutdown(self: Self, signum: int = signal.SIGINT, frame: Any = None) -> None:
        self.__server.shutdown()

    def run(self: Self) -> int:
        thread = Thread(target=self.__server.serve_forever)
        thread.daemon = True
        thread.start()
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)
        thread.join()
        self.__name_provider.save(self.__path)
        return 0
