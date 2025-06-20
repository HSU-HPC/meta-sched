"""Module for managing and retrieving environment variables."""

import os

__defaults = dict(
    MS_SERVER_HOST = "localhost",
    MS_SERVER_PORT = 8001,
)


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
    default: str|None = None
) -> str:
    """Get the value of an environment variable or its default.

    Parameters
    ----------
    key : str
        The name of the environment variable
    default : str | None    
        If not None, overrides the hardcoded default value with a different one

    Returns
    -------
    str
        The value of the environment variable or its default value
    """
    return str(os.getenv(key, default or __defaults.get(key)))
