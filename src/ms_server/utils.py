"""Module containing utility functions for the Meta Scheduler Server."""

import os

from ms_common.utils import eprint


def write_policy_log(line: str) -> None:
    """
    Append a line to the meta scheduling policy log if
    a filename is specified through the environment variable MS_POLICY_LOG.
    (e.g. /var/log/meta-sched-policy.log)

    Parameters
    ----------
    line : str
        The log line to be appended to the file
    """
    eprint(line)
    filename = os.getenv("MS_POLICY_LOG")
    if filename:
        with open(filename, "a") as file:
            file.write(line)
            file.write("\n")
