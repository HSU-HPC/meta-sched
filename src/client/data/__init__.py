"""Module containing data files which are used from the module."""

from pathlib import Path


def get_examples_dir() -> Path:
    """
    Get the path to the data directory contained in this module.

    Returns
    -------
    Path
        The path to the data directory.
    """
    return Path(__file__).parent / "examples"
