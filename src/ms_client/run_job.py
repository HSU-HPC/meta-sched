#! /usr/bin/env python3

"""Script for running a single job. (Invoked by CLI.)"""

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path
from types import FrameType

from ms_common.job import Instance as Job
from ms_common.job import Spec
from ms_common.utils import eprint
from pydantic import ValidationError

from ms_client.client import Client
from ms_client.config import Config
from ms_client.executor import Executor
from ms_client.scheduler_interface import SchedulerClientInterface


def __get_scheduler() -> SchedulerClientInterface:
    """
    Instantiates a client for access to the scheduler.
    (Uses parameters from the environment or default values.)

    Returns
    -------
    Client
        The scheduler client
    """
    try:
        config = Config.load()
    except ValidationError as e:
        eprint(e.json(indent=3))
        sys.exit(os.EX_CONFIG)
    scheduler = Client(config)
    return scheduler


def __start_process(job_spec: str, array_id: str, array_idx: int) -> int:
    """
    Execute a job as a new process running the module containing this function as a script.

    Parameters:
    job_spec : str
        The name of the job spec (folder name) to use
    array_id : str
        The global identifier of the job array
    array_idx : int
        The job index in the array

    Returns
    -------
    str
        The PID of the process that was started
    """
    args = ["-s", job_spec, "-a", array_id, "-i", str(array_idx), "-r", "--nohup"]
    p = subprocess.Popen(
        [sys.executable, __file__] + args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setpgrp,  # Do not receive signals from current process
    )
    return p.pid


class NoTargetsAvailableError(RuntimeError):
    """
    Exception raised when no targets are available to run a job.
    """

    def __init__(self, job_spec: str) -> None:
        """
        Initialize the exception with the job specification that has no targets available.

        Parameters
        ----------
        job_spec : str
            The name of the job spec (folder name)
        """
        super().__init__(f"No targets available to run '{job_spec}'.")
        self.job_spec = job_spec


def launch_job_array(job_spec: str) -> str:
    """
    Execute a job array by starting each job as a processes.

    Parameters
    ----------
    job_spec : str
        The name of the job spec (folder name)

    Returns
    -------
    str
        Information about the launched job spec and job identifiers
        # TODO consider returning python data structure instead

    Raises
    ------
    NoTargetsAvailableError
        If no targets are available to run the job spec
    """
    spec = Spec.load(job_spec)
    scheduler = __get_scheduler()
    suitable_targets = Executor.filter_targets(spec, scheduler)
    if len(suitable_targets) == 0:
        raise NoTargetsAvailableError(job_spec)
    array_id = scheduler.submit_job_array(spec, suitable_targets)
    for array_idx in range(0, spec.array_size):
        __start_process(job_spec, array_id, array_idx)
    # TODO consider returning raw array_id, array_idxs, and PIDs
    return f"JOBS {job_spec} {array_id}_[0-{spec.array_size - 1}]"


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("-s", "--job-spec", type=str, required=True)
    arg_parser.add_argument("-a", "--array-id", type=str, required=True)
    arg_parser.add_argument("-i", "--array-index", type=int, default=1)
    arg_parser.add_argument("-r", "--redirect-output", action="store_true")
    arg_parser.add_argument("--nohup", action="store_true")
    args = arg_parser.parse_args()
    assert args.array_index >= 0

    def ignore_signal(signalnum: int, frame: FrameType | None) -> None:
        """
        Handle a signal sent to the process and do nothing.

        Parameters
        ----------
        signalnum : int
            (Unused)
        frame : FrameType | None
            (Unused)

        """
        pass

    if args.nohup:
        signal.signal(signal.SIGHUP, ignore_signal)

    os.chdir(Path.home())
    job = Job(Spec.load(args.job_spec), args.array_id, args.array_index)
    scheduler = __get_scheduler()
    Executor(
        job,
        scheduler,
        redirect_output=args.redirect_output,
    ).run()
