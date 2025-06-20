"""Module containing general purpose utility classes and functions for the submit component."""

import sys
from os import PathLike
from typing import Any, Self


class RedirectOutputToFile:
    """Context manager for redirecting sys.stdout/sys.stderr (e.g. the output of all calls to print) to a file."""

    def __init__(
        self: Self,
        stdout: str | PathLike[Any] | None = None,
        stderr: str | PathLike[Any] | None = None,
    ) -> None:
        """
        Create a new instance to redirect stdout/stderr.

        Parameters
        ----------
        stdout : str | PathLike[Any] | None
            Path to redirect sys.stdout to (default None does not redirect output)
        stderr : str | PathLike[Any] | None
            Path to redirect sys.stderr to (default None does not redirect output)
        """
        self.__stdout_redirect = stdout
        self.__stderr_redirect = stderr
        self.__stdout = sys.stdout
        self.__stderr = sys.stderr

    def __enter__(self: Self) -> Self:
        if self.__stdout_redirect:
            sys.stdout = open(self.__stdout_redirect, "a")
        if self.__stderr_redirect:
            sys.stderr = open(self.__stderr_redirect, "a")
        return self

    def __exit__(self: Self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        if self.__stdout_redirect:
            sys.stdout.flush()
            sys.stdout.close()
            sys.stdout = self.__stdout
        if self.__stderr_redirect:
            sys.stderr.flush()
            sys.stderr.close()
            sys.stderr = self.__stderr
