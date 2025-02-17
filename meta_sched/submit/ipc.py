import os
import select
import socket
import struct
from pathlib import Path
from typing import Any, Callable, Self, Tuple


def _socket_send_prefixed(connection: socket.socket, data: bytes) -> None:
    data_len_prefix = (len(data)).to_bytes(4, byteorder="little", signed=False)
    return connection.sendall(data_len_prefix + data)


# TODO Deal with open connections that refuse to send data (timeout and disconnect)
def _socket_recv_prefixed(connection: socket.socket) -> bytes | None:
    received = connection.recv(4)
    if not received:
        return None
    data_len = int.from_bytes(received, byteorder="little", signed=False)
    data = bytes()
    while len(data) < data_len:
        received = connection.recv(1024)
        data += received
    return received


class Server(object):
    def __init__(
        self,
        socket_path: Path,
    ) -> None:
        self.__socket_path = Path(socket_path)
        self.__server: socket.socket | None = None

    Handler = Callable[[str, Tuple[int, int, int]], str]

    def listen(self: Self) -> None:
        if self.__server:
            return  # Already listening
        # Remove any old socket file
        self.__socket_path.unlink(missing_ok=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(self.__socket_path.absolute()))
        # Make the socket accessible to all users
        os.chmod(self.__socket_path, 0o777)
        server.listen()
        self.__server = server

    def close(self: Self) -> None:
        if not self.__server:
            return
        self.__server.close()
        self.__server = None
        self.__socket_path.unlink(missing_ok=True)

    def __enter__(self: Self) -> Self:
        self.listen()
        return self

    def __exit__(self: Self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    def accept(self: Self, handler: Handler) -> None:
        SO_PEERCRED = 17
        if not self.__server:
            raise socket.error("Server is closed")
        with self.__server.accept()[0] as connection:
            credentials = connection.getsockopt(
                socket.SOL_SOCKET,
                SO_PEERCRED,
                struct.calcsize("3i"),
            )
            fd_ids = struct.unpack("3i", credentials)  # pid, uid, gid
            request = _socket_recv_prefixed(connection)
            if not request:
                return  # Connection was closed without data
            response = handler(request.decode(), fd_ids)
            if response:
                _socket_send_prefixed(connection, response.encode())

    def accept_non_blocking(
        self: Self,
        handler: Handler,
        timeout: float = 1,
    ) -> None:
        if not self.__server:
            raise socket.error("Server is closed")
        ready_to_read = select.select([self.__server], [], [], timeout)[0]
        if len(ready_to_read) > 0:
            self.accept(handler)


class Client(object):
    def __init__(self: Self, socket_path: Path) -> None:
        self.__socket_path = socket_path
        self.__client: socket.socket | None = None

    def connect(self: Self) -> Self:
        if self.__client:
            return self
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(str(self.__socket_path))
        self.__client = client
        return self

    def close(self: Self) -> None:
        if not self.__client:
            return
        self.__client.close()
        self.__client = None

    def __enter__(self: Self) -> Self:
        return self.connect()

    def __exit__(self: Self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    def request(self: Self, message: str) -> str | None:
        if not self.__client:
            raise socket.error(f"{self.__class__.__qualname__} ist not connected.")
        _socket_send_prefixed(self.__client, message.encode())
        response = _socket_recv_prefixed(self.__client)
        if response:
            return response.decode()
        return None
