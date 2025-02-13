import sys
from pathlib import Path
from typing import Self

from meta_sched.submit import ipc
from meta_sched.submit.job import JobSpec


class CLI:
    def __init__(self: Self, socket_path: Path) -> None:
        self.__socket_path = socket_path

    def run(self: Self) -> int:
        argv = sys.argv[1:]
        job_spec = ""
        try:
            job_spec = argv[0]
            JobSpec.load(job_spec)
            array_size = int(argv[1])
            assert array_size > 0
        except (ValueError, IndexError, AssertionError):
            print("Usage: ms-submit JOB_SPEC ARRAY_SIZE")
            return 1
        except FileNotFoundError:
            print("No such job spec:", job_spec)
            return 2
        with ipc.Client(self.__socket_path) as client:
            response = client.request(f"SUBMIT {job_spec} {array_size}")
            print(response)
        return 0
