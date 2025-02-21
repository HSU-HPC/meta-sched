import os
import sys
from pathlib import Path
from typing import Any


def eprint(*args: Any, **kwargs: Any) -> None:
    print(*args, **kwargs, file=sys.stderr)


# https://www.gnu.org/software/bash/manual/html_node/Exit-Status.html
EX_BASH_COMMAND_NOT_FOUND = 127


class StatusException(Exception):
    def __init__(self, status: int) -> None:
        self.status = status


def expect_ok(status: int) -> None:
    if status != os.EX_OK:
        raise StatusException(status)


def try_become_root(required: bool = False) -> None:
    if os.getuid() != 0:
        if "--sudo" in sys.argv:
            argv = [] + Path(f"/proc/{os.getpid()}/cmdline").read_text().split("\0")
            os.execv("/usr/bin/sudo", argv)
        elif required:
            eprint("Must be run as root (Add argument --sudo)")
            sys.exit(os.EX_NOPERM)


def time_to_seconds(time: str | int) -> int:
    if isinstance(time, int):
        return time
    seconds = 0
    # Parse char by char from right to left
    emit = time[::-1]
    cs = ""
    seconds_per_unit = 1
    for c in emit:
        match c:
            # Seconds -> Minutes -> Hours
            case ":":
                seconds += int(cs[::-1]) * seconds_per_unit
                seconds_per_unit *= 60
                cs = ""
            # Hours -> Days
            case "-":
                seconds += int(cs[::-1]) * seconds_per_unit
                seconds_per_unit *= 24
            case _:
                cs += c
    seconds += int(cs[::-1]) * seconds_per_unit
    return seconds


def seconds_to_time(seconds: int) -> str:
    seconds_per_minute = 60
    seconds_per_hour = seconds_per_minute * 60
    seconds_per_day = seconds_per_hour * 24
    days = seconds // seconds_per_day
    seconds %= seconds_per_day
    hours = seconds // seconds_per_hour
    seconds %= seconds_per_hour
    minutes = seconds // seconds_per_minute
    seconds %= seconds_per_minute
    return f"{days}-{hours:02d}:{minutes:02d}:{seconds:02d}"
