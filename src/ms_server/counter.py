"""Module containing class for persistent counter."""

import json
from multiprocessing import Lock
from os import PathLike
from pathlib import Path
from typing import Any, Dict, Self

from ms_common.utils import eprint


class PersistentCounter:
    """A thread-safe persistent counter."""

    def __init__(self) -> None:
        """Create a new instance of the persistent counter."""
        self.__counters: Dict[str, int] = dict()
        self.__lock = Lock()

    def load(self: Self, path: str | PathLike[Any]) -> None:
        """
        Load the state of the counter.

        Parameters
        ----------
        path : str | PathLike[Any]
            The file path were from where to the state of the counter
        """
        counters = {}
        try:
            counters = json.loads(Path(path).read_text())
        except json.decoder.JSONDecodeError:
            eprint("Could not load JSON from", path)
            return
        if (
            not isinstance(counters, dict)
            or any(not isinstance(k, str) for k in counters.keys())
            or any(not isinstance(v, int) for v in counters.values())
        ):
            raise TypeError()
        with self.__lock:
            self.__counters = counters

    def get_next(self: Self, prefix: str = "") -> str:
        """
        Increment the counter and return the new value.

        Parameter
        ---------
        prefix : str
            The key of the corresponding count and prefix of the returned value (Empty by default)

        Returns
        -------
        str
            The corresponding value with the prefix matching that key
        """
        with self.__lock:
            if prefix not in self.__counters:
                self.__counters[prefix] = 0
            self.__counters[prefix] += 1
            name = prefix
            if len(name) > 0:
                name += "-"
            name += str(self.__counters[prefix])
            return name

    def save(self: Self, path: str | PathLike[Any]) -> None:
        """
        Store the state of the counter.

        Parameters
        ----------
        path : str | PathLike[Any]
            The file path where to store the state of the counter
        """
        with self.__lock:
            Path(path).write_text(json.dumps(self.__counters, indent=3))
