#! /usr/bin/env python3

"""Script for running a single job. (Invoked by CLI.)"""

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path
from types import FrameType

from meta_sched import env
from meta_sched.common.job import Instance as Job
from meta_sched.common.job import Spec
from meta_sched.common.scheduler_interface import SchedulerInterface
from meta_sched.service.client import Client
from meta_sched.submit.executor import Executor


def __get_scheduler() -> SchedulerInterface:
    """
    Instantiates a client for access to the scheduler.
    (Uses parameters from the environment or default values.)

    Returns
    -------
    Client
        The scheduler client
    """
    host = env.get("MS_SERVICE_HOST")
    port = int(env.get("MS_SERVICE_PORT"))
    scheduler = Client(host, port)
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
    """
    spec = Spec.load(job_spec)
    scheduler = __get_scheduler()
    array_id = scheduler.create_array_id()
    for array_idx in range(0, spec.array_size):
        __start_process(job_spec, array_id, array_idx)
    # TODO consider returning raw array_id, array_idxs, and PIDs
    return f"JOBS {job_spec} {array_id}#[0-{spec.array_size - 1}]"


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
