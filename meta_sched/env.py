"""Module for managing and retrieving environment variables."""

import os

from meta_sched import defaults

__defaults = {k: defaults.__dict__[k] for k in dir(defaults) if not k.startswith("__")}


def has(key: str) -> bool:
    """Check if an environment variable was set.

    Parameters
    ----------
    key : str
        The name of the environment variable

    Returns
    -------
    bool
        Whether or not the environment variable is set
    """
    return key in os.environ


def get(
    key: str,
) -> str:
    """Get the value of an environment variable or its default.

    Parameters
    ----------
    key : str
        The name of the environment variable

    Returns
    -------
    str
        The value of the environment variable or its default value
    """
    return os.getenv(key, __defaults[key])
