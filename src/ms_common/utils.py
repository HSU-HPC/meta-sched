"""Module containing general purpose utility functions and classes."""

import functools
import os
import shlex
import sys
from typing import Any, Callable, Optional, TypeVar, Union, cast
import warnings

# See https://www.gnu.org/software/bash/manual/html_node/Exit-Status.html
EX_BASH_COMMAND_NOT_FOUND = 127
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


F = TypeVar("F", bound=Callable[..., Any])

def deprecated(reason: str) -> Callable[[F], F]:
    """
    Mark a function as deprecated.

    Parameters
    ----------
    reason : str
        The reason for deprecation


    Returns
    -------
    Callable
        The decorated function
    """
    def decorator(func: F) -> F:
        """
        Deprecation decorator.

        Parameters
        ----------
        func : F
            The function to be deprecated

        Returns
        -------
        F
            The deprecated function
        """
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            """
            Deprecation wrapper for the function
            """
            warnings.warn(
                f"{func.__name__}() is deprecated: {reason}",
                category=DeprecationWarning,
                stacklevel=2
            )
            return func(*args, **kwargs)
        return cast(F, wrapper)
    return decorator

@deprecated(reason="Maybe not needed anymore")
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


def time_to_seconds(time: Union[str, int]) -> int:
    """
    Compute duration in seconds from string in the format "d-hh:MM:ss".
    (Components are parsed from right to left and left-incomplete strings are allowed.)

    Parameters
    ----------
    time : Union[str, int]
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
    emit = time[::-1] # emit is time, but backwards ;)
    cs = ""
    seconds_per_unit = 1
    seconds_per_hour = 3600
    seconds_per_day = seconds_per_hour * 24
    for c in emit:
        if c == "-":
            # Hours -> Days
            if c == "-" and seconds_per_unit != seconds_per_hour:
                raise ValueError("Error parsing formatted time \"{time}\". (Day separator found at invalid position.)")
            seconds += int(cs[::-1]) * seconds_per_unit
            seconds_per_unit *= 24
            cs = ""
        elif c == ":":
            # Seconds -> Minutes -> Hours
            seconds += int(cs[::-1]) * seconds_per_unit
            seconds_per_unit *= 60
            cs = ""
        else:
            cs += c
    seconds += int(cs[::-1]) * seconds_per_unit
    if seconds_per_unit > seconds_per_day:
        raise ValueError(f"Error parsing formatted time \"{time}\". (Found additional unit separator after days.)")
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
    
def is_env_flag_set(key: str) -> bool:
    """
    Check if a flag is set as an environment variable is set (and not empty, 0, false, no).

    Parameter
    ---------
    key : str
        The name of the environment variable

    Returns
    -------
    bool
        The status of the flag from the environment variable
    """
    val = os.getenv(key, "").strip()
    return len(val) > 0 and val != "0" and val.lower() != "false" and val.lower() != "no"
