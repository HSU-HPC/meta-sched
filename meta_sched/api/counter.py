import json
from multiprocessing import Lock
from os import PathLike
from pathlib import Path
from typing import Any, Dict, Self

from meta_sched.common.utils import eprint


class PersistentCounter:
    def __init__(self) -> None:
        self.__counters: Dict[str, int] = dict()
        self.__lock = Lock()

    def load(self: Self, path: str | PathLike[Any]) -> None:
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
        with self.__lock:
            Path(path).write_text(json.dumps(self.__counters, indent=3))
