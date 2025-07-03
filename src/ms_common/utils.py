"""Module containing general purpose utility functions and classes."""

import os
import shlex
import sys
from typing import Any, Optional

from deprecated import deprecated # type: ignore[attr-defined]

DEFAULT_SSH_PORT = 22

def eprint(*args: Any, **kwargs: Any) -> None:
    """
    Print function for stderr.

    Parameters
    ----------
    *args : Any
        Positional arguments forwarded to built-in print function
    **kwargs : Any
        Named arguments forwarded to built-in print function
    """
    kwargs["flush"] = True
    print(*args, **kwargs, file=sys.stderr)


# See https://www.gnu.org/software/bash/manual/html_node/Exit-Status.html
EX_BASH_COMMAND_NOT_FOUND = 127


def exponential_backoff(
    count: int, offset: float = 0, maximum: Optional[float] = 60, base: float = 2
) -> float:
    """
    Compute the delay according to a clamped exponential backoff function.

    Parameters
    ----------
    count : int
        How many times the backoff strategy has already been applied
    offset : float
        The starting value of the function added as a constant offset
    maximum : Optional[float]
        The maximum value of the backoff function (60 by default) or None if it is unclamped
    base : float
        The base of the exponential function (2 by default)

    Returns
    -------
    float
        The next wait duration
    """
    if count < 0:
        raise ValueError()
    time = offset + base**count
    if maximum is not None:
        time = min(time, maximum)
    return time


class StatusException(Exception):
    """
    Exception for an exit code of a process.
    """

    def __init__(self, status: int) -> None:
        """
        Create a new instance of the exception.

        Parameters
        ----------
        status : int
            The exit code of the corresponding process
        """
        self.status = status


def expect_ok(status: int) -> None:
    """
    Assert that status is exit code for success.

    Parameters
    ----------
    status : int
        The exit code of a previously executed process

    Raises
    ------
    StatusException
        The corresponding process did not exit with status code for success.
    """
    if status != os.EX_OK:
        raise StatusException(status)

@deprecated(reason="Maybe not needed anymore") # type: ignore[no-untyped-call,misc]
def try_become_root(required: bool = False) -> None:
    """
    Try to restart the current application as the root user if not already and "--sudo" was given as a command line parameter.
    (Replaces current process.)

    Parameters
    ----------
    required : bool
        If true, exit with an error if not root and "--sudo" is not in the command line arguments
    """
    if os.getuid() != 0:
        if "--sudo" in sys.argv:
            argv = [
                "sudo",
                "--preserve-env=PATH,VIRTUAL_ENV,PYTHONPATH",  # Critical for venv or uv
                sys.executable,
                *map(shlex.quote, sys.argv)
            ]
            os.execv("/usr/bin/sudo", argv)
        elif required:
            eprint("Must be run as root (Add argument --sudo)")
            sys.exit(os.EX_NOPERM)


def time_to_seconds(time: str | int) -> int:
    """
    Compute duration in seconds from string in the format "d-hh:MM:ss".
    (Components are parsed from right to left and left-incomplete strings are allowed.)

    Parameters
    ----------
    time : str | int
        Formatted time duration or seconds (no parsing needed)


    Returns
    -------
    int
        The duration in seconds
    """
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
                cs = ""
            case _:
                cs += c
    seconds += int(cs[::-1]) * seconds_per_unit
    return seconds


def seconds_to_time(seconds: int, include_days: bool = True) -> str:
    """
    Format duration in seconds as "d-hh:MM:ss".

    Parameters
    ----------
    seconds : int
        Time duration in seconds to be formatted
    include_day : bool
        Should days be counted separately from hours


    Returns
    -------
    str
        The duration formatted as "hh:MM:ss" or "d-hh:MM:ss" if include_days=True
    """
    seconds_per_minute = 60
    seconds_per_hour = seconds_per_minute * 60
    seconds_per_day = seconds_per_hour * 24
    days = seconds // seconds_per_day
    seconds %= seconds_per_day
    hours = seconds // seconds_per_hour
    seconds %= seconds_per_hour
    minutes = seconds // seconds_per_minute
    seconds %= seconds_per_minute
    if include_days:
        return f"{days}-{hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{24 * days + hours:02d}:{minutes:02d}:{seconds:02d}"
