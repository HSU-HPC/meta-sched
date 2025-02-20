import argparse
import inspect
import os
import shutil
import sys
from pathlib import Path
from typing import Self

from meta_sched import data
from meta_sched.common import ssh
from meta_sched.common.job import Spec, get_job_outputs, get_jobs_dir
from meta_sched.common.scheduler_interface import SchedulerInterface as Scheduler
from meta_sched.common.utils import eprint
from meta_sched.submit import ipc


class CLI:
    def __init__(self: Self, submitd_socket_path: Path, scheduler: Scheduler) -> None:
        self.__socket_path = submitd_socket_path
        self.__scheduler = scheduler

    def ssh_config(self: Self) -> int:
        "Update SSH configuration"
        try:
            targets = self.__scheduler.targets
        except Exception:
            eprint("Could not connect to scheduler")
            return os.EX_OK
        targets_missing_user = ssh.update_config({t.id: t.host for t in targets})
        print("Updated", ssh.get_config_paths()[0], end=".\n")
        print(
            f"\n({targets_missing_user} incomplete target configs require credentials to be added.)"
        )
        return os.EX_OK

    def create(self: Self, template: str, name: str) -> int:
        "Create a new job spec"
        os.chdir(Path.home())
        examples = {p.name: p for p in (data.get_examples_dir() / "jobs").iterdir()}
        if template not in examples:
            eprint("No such job spec template:", template)
            eprint("\nAvailable:")
            for job_spec in examples:
                eprint("-", job_spec)
            return os.EX_NOINPUT
        get_jobs_dir().mkdir(parents=True, exist_ok=True)
        try:
            path = shutil.copytree(examples[template], get_jobs_dir() / name)
            print(
                f'Created job spec "{name}" based on template "{template}".\n\n{path.absolute()}'
            )
        except FileExistsError:
            eprint("Job spec already exists:", name)
            return os.EX_CANTCREAT
        return os.EX_OK

    def submit(self: Self, job_spec: str) -> int:
        "Submit a job array for an existing job spec"
        os.chdir(Path.home())
        try:
            array_size = Spec.load(job_spec).array_size
        except ValueError:
            eprint("No such job spec:", job_spec)
            eprint(f"\nAvailable under {get_jobs_dir().absolute()}:")
            for job_spec in Spec.list():
                eprint("-", job_spec)
            return os.EX_NOINPUT
        try:
            with ipc.Client(self.__socket_path) as client:
                response = client.request(f"SUBMIT {job_spec} {array_size}")
                print("submitd:", response)
        except (ConnectionRefusedError, FileNotFoundError):
            eprint("Could not connect to ms-submitd. (Is it running?)")
            return os.EX_UNAVAILABLE
        return os.EX_OK

    def status(self: Self) -> int:
        "Get the status of submitted jobs"
        os.chdir(Path.home())
        df = get_job_outputs()
        print(df.to_string(index=True))
        return os.EX_OK

    def cancel(self: Self, pattern: str) -> int:
        "Cancel submitted jobs"
        os.chdir(Path.home())
        raise NotImplementedError()

    def run(self: Self) -> int:
        argv = sys.argv
        argparser = argparse.ArgumentParser()
        command_functions = [
            self.create,
            self.submit,
            self.status,
            self.cancel,
            self.ssh_config,
        ]
        commands = {f.__name__.replace("_", "-"): f for f in command_functions}
        subparsers = argparser.add_subparsers(dest="command", required=True)
        for command, f in commands.items():
            subparser = subparsers.add_parser(command, help=f.__doc__)
            full_arg_spec = inspect.getfullargspec(f)
            for arg in full_arg_spec.args:
                arg_type = full_arg_spec.annotations[arg]
                if arg_type == Self:
                    continue
                subparser.add_argument(
                    arg, metavar=arg.replace("_", "-"), type=arg_type
                )
        args = argparser.parse_args(argv[1:])
        kwargs = {k: v for k, v in args._get_kwargs()}
        del kwargs["command"]
        status = int(
            eval("commands[args.command](**kwargs)")
        )  # Workaround unknown return type
        return status
