#! /usr/bin/env python3

import os
import subprocess
from multiprocessing import Process
from pathlib import Path
from typing import Callable, List, Self, Tuple

from meta_sched.submit import ipc
from meta_sched.submit.executor import Executor
from meta_sched.submit.lock_file import LockFile

# TODO eventually replace with RestAPI
from meta_sched.submit.scheduler_interface import Dummy as Scheduler
from meta_sched.submit.target import SlurmTarget


class Daemon:
    def __init__(
        self: Self, socket_path: Path, name_provider: Callable[[str], str]
    ) -> None:
        self.__processes: List[Process] = []
        self.__socket_path = socket_path
        self.__name_provider = name_provider

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
        os.chdir(Path.home())

    def __run_executor(
        self: Self, job_spec: str, uid: int, array_id: int, array_idx: int
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
            array_id,
            array_idx,
            redirect_output=True,
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
        array_id = ""
        try:
            array_id = self.__name_provider("job")
        except Exception:
            print("Failed!")
            return "FAILED"
        print("OK!")
        for i in range(1, array_size + 1):
            p = Process(target=self.__run_executor, args=(job_spec, uid, array_id, i))
            p.start()
            self.__processes.append(p)
        return f"JOBS {job_spec}/{array_id}-*"

    def run(self: Self) -> int:
        # Ensure that other users can create lock files
        lock_file_dir = LockFile.get_base_path() / "meta-sched"
        lock_file_dir.mkdir(exist_ok=True)
        os.chmod(lock_file_dir, 0o777)

        with ipc.Server(self.__socket_path) as server:
            while True:
                print("Awaiting request...")
                server.accept(self.__handler)
                # Clean up finished processes
                self.__processes = [p for p in self.__processes if p.is_alive()]

        return 0
