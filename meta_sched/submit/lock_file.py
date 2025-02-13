import fcntl
from io import TextIOWrapper
from pathlib import Path
from typing import Any, Self


# TODO consider using https://github.com/WoLpH/portalocker or https://linux.die.net/man/3/sem_open
class LockFile:
    @staticmethod
    def get_base_path() -> Path:
        return Path("/tmp")

    def __init__(self: Self, name: str) -> None:
        self.__path = LockFile.get_base_path() / name
        self.__path.parent.mkdir(parents=True, exist_ok=True)
        self.__path.touch()
        self.__file: TextIOWrapper[Any] | None = None

    def __enter__(self: Self) -> Self:
        if self.__file:
            raise RuntimeError("Re-entry not allowed")
        self.__file = open(self.__path)
        fcntl.flock(self.__file.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self: Self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        if self.__file:
            fcntl.flock(self.__file.fileno(), fcntl.LOCK_UN)
            self.__file.close()
            self.__file = None
