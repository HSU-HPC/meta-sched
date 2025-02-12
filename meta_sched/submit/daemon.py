#! /usr/bin/env python3

import os
import subprocess
import sys
from multiprocessing import Process
from pathlib import Path
from typing import List, Self, Tuple

from meta_sched.submit import ipc
from meta_sched.submit.executor import Executor

# TODO eventually replace with RestAPI
from meta_sched.submit.scheduler_interface import Dummy as Scheduler
from meta_sched.submit.target import SlurmTarget


class Daemon:
    def __init__(self: Self) -> None:
        self.__processes: List[Process] = []
        self.__next_array_id = 1  # TODO maybe resume from last if restarted

    @staticmethod
    def __switch_user(uid: int) -> None:
        cmd = ["getent", "passwd", str(uid)]
        output = subprocess.check_output(cmd).decode()
        home = output.split(":")[-2]
        env_copy = {k: os.environ[k] for k in ["PATH", "PYTHONPATH"] if k in os.environ}
        os.environ.clear()
        os.environ["HOME"] = home
        for k, v in env_copy.items():
            os.environ[k] = v
        os.setuid(uid)

    def __run_executor(
        self: Self, job_spec: str, uid: int, local_array_id: int, array_idx: int
    ) -> None:
        Daemon.__switch_user(uid)
        # TODO only for debugging
        scheduler = Scheduler(
            SlurmTarget(
                id="256b4c0e-c6b7-41da-a35d-03382428528a",
                host="windhpc00.hsu-hh.de",
            )
        )
        Executor.from_job_spec(
            job_spec,
            scheduler,
            local_array_id,
            array_idx,
            redirect_output=False,  # TODO only for debugging
        ).run()

    def __handler(self: Self, request: str, ids: Tuple[int, int, int]) -> str:
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
        array_id = self.__next_array_id
        self.__next_array_id += 1
        print("OK!")
        for i in range(1, array_size + 1):
            p = Process(target=self.__run_executor, args=(job_spec, uid, array_id, i))
            p.start()
            self.__processes.append(p)
        return f"JOBS {job_spec}/output/{array_id}-*"

    def run(self: Self) -> int:
        if os.getuid() != 0:
            if "--sudo" in sys.argv:
                argv = [] + Path(f"/proc/{os.getpid()}/cmdline").read_text().split("\0")
                os.execv("/usr/bin/sudo", argv)
            print("Must be run as root")
            return 1

        with ipc.Server() as server:
            while True:
                print("Awaiting request...")
                server.accept(self.__handler)
                # Clean up finished processes
                self.__processes = [p for p in self.__processes if p.exitcode is None]

        return 0
