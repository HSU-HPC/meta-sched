import os
import sys
from pathlib import Path
from typing import Self

from meta_sched.common.job import Spec
from meta_sched.submit import ipc


class CLI:
    def __init__(self: Self, socket_path: Path) -> None:
        self.__socket_path = socket_path

    def run(self: Self) -> int:
        argv = sys.argv[1:]
        job_spec = ""
        try:
            job_spec = argv[0]
            os.chdir(Path.home())
            array_size = Spec.load(job_spec).array_size
        except IndexError:
            print("Usage: ms-submit JOB_SPEC")
            return 1
        except FileNotFoundError:
            print("No such job spec:", job_spec)
            return 2
        with ipc.Client(self.__socket_path) as client:
            response = client.request(f"SUBMIT {job_spec} {array_size}")
            print(response)
        return 0
