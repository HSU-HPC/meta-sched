"""Module for Inter Process Communication (IPC)."""

import os
import select
import socket
import struct
from pathlib import Path
from typing import Any, Callable, Self, Tuple


def _socket_send_prefixed(connection: socket.socket, data: bytes) -> None:
    """Send a specified amount of data over a socket by first sending the amount of bytes.

    Parameters
    ----------
    connection : socket.socket
        The socket over which to send the data
    data : bytes
        The the data to be sent
    """
    data_len_prefix = (len(data)).to_bytes(4, byteorder="little", signed=False)
    return connection.sendall(data_len_prefix + data)


def _socket_recv_prefixed(connection: socket.socket) -> bytes | None:
    """Receive a specified amount of data over a socket by first receiving the amount of bytes.

    TODO: Deal with open connections that refuse to send data (timeout or disconnect)

    Parameters
    ----------
    connection : socket.socket
        The socket over which to receive the data

    Returns
    -------
    bytes | None
        The the data to that was sent or None if nothing was received
    """
    received = connection.recv(4)
    if not received:
        return None
    data_len = int.from_bytes(received, byteorder="little", signed=False)
    data = bytes()
    while len(data) < data_len:
        received = connection.recv(1024)
        if received is not None:
            data += received
    return received


class Server(object):
    """Synchronous class implementing the server in client-server based IPC communication."""

    def __init__(
        self: Self,
        socket_path: Path,
    ) -> None:
        """Instantiate the server.

        Parameters
        ----------
        socket_path : Path
            Path where the socket file should be created
        """
        self.__socket_path = Path(socket_path)
        self.__server: socket.socket | None = None

    Handler = Callable[[str, Tuple[int, int, int]], str]

    def listen(self: Self) -> None:
        """
        (Re-)create the socket file and start listening for incoming connections on the socket.

        (Calling this method multiple times has not effect.)
        """
        if self.__server:
            return  # Already listening
        # Remove any old socket file
        self.__socket_path.unlink(missing_ok=True)
        self.__socket_path.parent.mkdir(parents=True, exist_ok=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(self.__socket_path.absolute()))
        # Make the socket accessible to all users
        os.chmod(self.__socket_path, 0o777)
        server.listen()
        self.__server = server

    def close(self: Self) -> None:
        """
        Stop listening for incoming connections and delete the socket file.

        (Calling this method multiple times has not effect.)
        """
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
        """
        Await an incoming connection on the opened socket and then invoke the handler.

        The PID, UID, and GID of the process from which the request originates are resolved which may be used for authentication.

        Parameters
        ----------
        handler : Handler
            Callback to handle the request by the client (return response data for PID, UID, GID, and request data)
        """
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
        """
        Await an incoming connection on the opened socket and then invoke the handler or timeout.

        The PID, UID, and GID of the process from which the request originates are resolved which may be used for authentication.

        Parameters
        ----------
        handler : Handler
            Callback to handle the request by the client (return response data for PID, UID, GID, and request data)
        timeout : float
            Amount of time to wait for an incoming request in seconds
        """
        if not self.__server:
            raise socket.error("Server is closed")
        ready_to_read = select.select([self.__server], [], [], timeout)[0]
        if len(ready_to_read) > 0:
            self.accept(handler)


class Client(object):
    """Synchronous class implementing the client in client-server based IPC communication."""

    def __init__(self: Self, socket_path: Path) -> None:
        """Instantiate the client.

        Parameters
        ----------
        socket_path : Path
            Path of the socket file used for sending requests to the server
        """
        self.__socket_path = socket_path
        self.__client: socket.socket | None = None

    def connect(self: Self) -> Self:
        """
        Open the socket file.

        (Calling this method multiple times has not effect.)
        """
        if self.__client:
            return self
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(str(self.__socket_path))
        self.__client = client
        return self

    def close(self: Self) -> None:
        """
        Close the socket file.

        (Calling this method multiple times has not effect.)
        """
        if not self.__client:
            return
        self.__client.close()
        self.__client = None

    def __enter__(self: Self) -> Self:
        return self.connect()

    def __exit__(self: Self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    def request(self: Self, message: str) -> str | None:
        """
        Send a request to the server over the opened socket file.

        Parameters
        ----------
        message : str
            The request data to be sent to the server

        Returns
        -------
        str | None
            The response data from the server or None
        """
        if not self.__client:
            raise socket.error(f"{self.__class__.__qualname__} ist not connected.")
        _socket_send_prefixed(self.__client, message.encode())
        response = _socket_recv_prefixed(self.__client)
        if response:
            return response.decode()
        return None
