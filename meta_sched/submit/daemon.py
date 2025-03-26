"""Module for creating job processes for requests through CLI client."""

import os
import subprocess
from multiprocessing import Process
from pathlib import Path
from typing import List, Self, Tuple

from meta_sched.common.job import Instance as Job
from meta_sched.common.job import Spec
from meta_sched.common.scheduler_interface import SchedulerInterface as Scheduler
from meta_sched.submit import ipc
from meta_sched.submit.executor import Executor
from meta_sched.submit.lock_file import LockFile


class Daemon:
    """
    This class creates executer processes for jobs started through the CLI.
    """

    def __init__(self: Self, socket_path: Path, scheduler: Scheduler) -> None:
        """
        Create a new instance of the daemon.

        Parameters
        ----------
        socket_path : Path
            Path to the socket file used for incoming requests by CLI clients
        scheduler : Scheduler
            Interface to the scheduler policy
        """
        self.__processes: List[Process] = []
        self.__socket_path = socket_path
        self.__scheduler = scheduler

    @staticmethod
    def __switch_user(uid: int) -> None:
        """
        Change from the user of the current process and update the environment accordingly.
        (Only HOME, PATH, PYTHONPATH variables are set.)

        Parameters
        ----------
        uid : int
            The UID/GID of the linux user under which the process should continue
        """
        cmd = ["getent", "passwd", str(uid)]
        output = subprocess.check_output(cmd).decode()
        home = output.split(":")[-2]
        env_copy = {k: os.environ[k] for k in ["PATH", "PYTHONPATH"] if k in os.environ}
        os.environ.clear()
        os.environ["HOME"] = home
        for k, v in env_copy.items():
            os.environ[k] = v
        os.setgid(uid)
        os.setuid(uid)
        os.chdir(Path.home())

    def __run_executor(
        self: Self, job_spec: str, uid: int, array_id: str, array_idx: int
    ) -> None:
        """
        Create a job and corresponding executor and run it as the specified user in the current process (blocking).

        Parameters
        ----------
        job_spec : str
            The name of the job specification to load and use to create the job
        uid : int
            The linux UID under which this process should continue executing
        array_id : str
            The ID of the job array to which this job belongs
        array_idx : int
            The unique index of the job in the job array
        """
        Daemon.__switch_user(uid)
        job = Job(Spec.load(job_spec), array_id, array_idx)
        Executor(
            job,
            self.__scheduler,
            redirect_output=True,
        ).run()

    def __handler(self: Self, request: str, ids: Tuple[int, int, int]) -> str:
        """
        Handler for the IPC server of the daemon for incoming job submission requests by a CLI client.

        Parameters
        ----------
        request : str
            The contents of the IPC request sent by the client (Must be SUBMIT <job_spec>)
        ids : Tuple[int, int, int]
            PID, UID, GID of the linux process from which the request originates
        """
        print("Got", request, "...", end="")
        argv = request.split()
        try:
            assert argv[0] == "SUBMIT"
            job_spec = argv[1]
            uid = ids[1]
            array_size = int(argv[2])
        except (AssertionError, ValueError, IndexError):
            print("Invalid!")
            return "INVALID"
        uid = ids[1]
        array_id = ""
        try:
            array_id = self.__scheduler.create_array_id()
        except Exception:
            print("Failed!")
            return "FAILED"
        print("OK!")
        for i in range(1, array_size + 1):
            # TODO consider fully demonizing executor to avoid "orphan remote jobs" when the daemon process dies unexpectedly
            p = Process(target=self.__run_executor, args=(job_spec, uid, array_id, i))
            p.start()
            self.__processes.append(p)
        return f"JOBS {job_spec} {array_id}.[1-{array_size}]"

    def run(self: Self) -> None:
        """Execute the daemon in the current process (blocking)."""
        # Ensure that other users can create lock files
        lock_file_dir = LockFile.get_base_path() / "meta-sched"
        lock_file_dir.mkdir(exist_ok=True)
        os.chmod(lock_file_dir, 0o777)

        with ipc.Server(self.__socket_path) as server:
            while True:
                server.accept_non_blocking(self.__handler)
                # Clean up finished processes
                self.__processes = [p for p in self.__processes if p.is_alive()]

    def start_process(self: Self) -> Process:
        """Start executing the daemon as a new process."""
        process = Process(target=self.run)
        process.start()
        return process
