import argparse
import errno
import inspect
import os
import shutil
import signal
import sys
import time
from pathlib import Path
from typing import Any, Dict, Self

import pandas as pd

from meta_sched import data
from meta_sched.common import ssh
from meta_sched.common.job import Spec, get_job_outputs, get_jobs_dir
from meta_sched.common.scheduler_interface import SchedulerInterface as Scheduler
from meta_sched.common.utils import eprint
from meta_sched.submit import ipc


# TODO split into Client and CLI
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
        if job_spec not in Spec.list():
            eprint("No such job spec:", job_spec)
            eprint(f"\nAvailable under {get_jobs_dir().absolute()}:")
            for job_spec in Spec.list():
                eprint("-", job_spec)
            return os.EX_NOINPUT
        try:
            array_size = Spec.load(job_spec).array_size
        except ValueError as e:
            eprint("Could not load job spec:", job_spec)
            print(e)
            return os.EX_NOINPUT
        try:
            with ipc.Client(self.__socket_path) as client:
                response = client.request(f"SUBMIT {job_spec} {array_size}")
                print("submitd:", response)
        except (ConnectionRefusedError, FileNotFoundError):
            eprint("Could not connect to ms-submitd. (Is it running?)")
            return os.EX_UNAVAILABLE
        return os.EX_OK

    def status(
        self: Self,
        count: int = 10,
        completed: bool = False,
        failed: bool = False,
        canceled: bool = False,
        all: bool = False,
    ) -> int:
        "Get the status of submitted jobs"
        os.chdir(Path.home())
        df = get_job_outputs()
        df.drop(columns=["path", "pid"], inplace=True)
        pending_scheduled_running = all or not (completed or failed or canceled)

        def filter_status(status: str) -> bool:
            if all:
                return True
            match status.lower().split()[0]:
                case "completed":
                    return completed
                case "failed":
                    return failed
                case "canceled":
                    return canceled
                case _:
                    return pending_scheduled_running

        df["status"] = df["status"].apply(lambda x: x if filter_status(x) else None)
        df = df[~df["status"].isnull()]
        df = df.tail(n=max(0, count))
        if len(df) == 0:
            eprint("No jobs.")
            return os.EX_TEMPFAIL
        print(df.to_string(index=False))
        return os.EX_OK

    def cancel(self: Self, pattern: str, no_confirm: bool = False) -> int:
        "Cancel submitted jobs"
        os.chdir(Path.home())
        df: pd.DataFrame = get_job_outputs()
        if any(not (c.isalnum() or c in "-_.*") for c in pattern):
            eprint(
                "Bad job pattern. (Supports only valid job_id characters and wildcard *.)"
            )
            return os.EX_USAGE
        pattern.replace(".", "\\.")
        pattern = pattern.replace("*", ".*")
        if "\\." not in pattern:
            pattern += "\\..*"  # Any array_idx (since not given)
        if len(df) > 0:
            df = pd.DataFrame(df[df["job_id"].str.contains(f"^{pattern}$", regex=True)])
            df = pd.DataFrame(df[~df["pid"].isna()])
        if len(df) == 0:
            eprint("No jobs.")
            return os.EX_TEMPFAIL
        was_confirmed = False
        if not no_confirm:
            print(f"Confirm cancelation of jobs:\n{', '.join(df['job_id'].values)}")
            try:
                was_confirmed = input('\nType "yes": ').strip() == "yes"
            except KeyboardInterrupt:
                pass
        if not (no_confirm or was_confirmed):
            print("Aborted.")
            return os.EX_OK
        pids = df["pid"].astype(int).values
        for pid in pids:
            os.kill(pid, signal.SIGINT)

        def wait_pid(pid: int, check_interval: float = 1) -> None:
            SIG_CHECK_PID_EXISTS = 0
            while True:
                try:
                    os.kill(pid, SIG_CHECK_PID_EXISTS)
                    time.sleep(check_interval)
                except OSError as e:
                    if e.errno == errno.ESRCH:
                        return

        print("Waiting for canceled job(s) to terminate...", end=" ", flush=True)
        try:
            for pid in pids:
                wait_pid(pid)
            print("Done!")
        except KeyboardInterrupt:
            pass
        return os.EX_OK

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
            args = full_arg_spec.args
            annotations = full_arg_spec.annotations
            defaults = [] if full_arg_spec.defaults is None else full_arg_spec.defaults
            for i, arg in enumerate(args):
                dest = arg.replace("_", "-")
                kwargs: Dict[str, Any] = dict()
                default = None
                if i >= len(args) - len(defaults):
                    default = defaults[i - (len(args) - len(defaults))]
                    dest = f"--{dest}"
                if arg in annotations:
                    arg_type = annotations[arg]
                    if arg_type == Self:
                        continue
                    if arg_type is bool and default is not None:
                        kwargs["action"] = "store_false" if default else "store_true"
                    else:
                        kwargs["type"] = arg_type
                subparser.add_argument(dest, default=default, **kwargs)
        cmd_args = argparser.parse_args(argv[1:])
        kwargs = {k.replace("-", "_"): v for k, v in cmd_args._get_kwargs()}
        del kwargs["command"]
        status = int(
            eval("commands[cmd_args.command](**kwargs)")
        )  # Workaround unknown return type
        return status
