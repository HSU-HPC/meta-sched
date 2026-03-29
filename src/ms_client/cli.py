#! /usr/bin/env python3

"""Module/script containing the command line client application for job control."""

import argparse
import errno
import inspect
import os
import shutil
import signal
import sys
from pathlib import Path
from typing import Any, Dict

import pandas as pd
from ms_client.utils import sleep
from ms_common.schemas import Target
from ms_common.utils import eprint
from pydantic import ValidationError

import ms_client.data as data
from ms_client import ssh
from ms_client.client import Client
from ms_client.config import Config
from ms_client.job import (
    get_job_outputs,
    get_jobs_dir,
    list_job_spec_names,
    load_job_spec,
)
from ms_client.remote_target.factory import remote_target_from_target
from ms_client.run_job import NoTargetsAvailableError, launch_job_array


class CLI:
    """
    Meta Scheduler command line application for creating job specifications and for job control.
    """

    def __init__(self: "CLI", client: Client) -> None:
        """
        Create a new instance of the CLI.

        Parameters
        ----------
        client : Client
            Interface to the HTTP API
        """
        self.__client = client

    def require_can_use_client(self: "CLI") -> None:
        """Check if the client has the correct version or exit the process with the corresponding error."""
        try:
            self.__client.check_version_ok()
        except ValueError as e:
            eprint(e)
            sys.exit(os.EX_PROTOCOL)
        except RuntimeError as e:
            eprint(e)
            sys.exit(os.EX_UNAVAILABLE)

    def ssh_config(self: "CLI") -> int:
        """
        Update SSH configuration.
        (Fetches targets from scheduler first.)

        Returns
        -------
        int
            The exit status of the operation
        """
        self.require_can_use_client()
        try:
            targets = self.__client.targets
        except Exception:
            eprint("Could not connect to scheduler")
            return os.EX_UNAVAILABLE
        targets_missing_user = ssh.update_config({t.id: t.host for t in targets})
        print("Updated", ssh.get_config_paths()[0], end=".\n")
        print(
            f"\n({targets_missing_user} incomplete target configs require credentials to be added.)"
        )
        return os.EX_OK if targets_missing_user == 0 else os.EX_TEMPFAIL

    def create(self: "CLI", template: str, name: str) -> int:
        """
        Create a new job spec

        Parameters
        ----------
        template : str
            The name of the template from data.examples.jobs to instantiate
        name : str
            The name of the new job spec (folder name)

        Returns
        -------
        int
            The exit status of the operation
        """
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

    def validate(self: "CLI", job_spec: str) -> int:
        """
        Validate a job spec

        Parameters
        ----------
        job_spec : str
            The name of the job spec (folder name) to validate

        Returns
        -------
        int
            The exit status of the operation
        """
        os.chdir(Path.home())
        job_specs = list_job_spec_names()
        if job_spec not in job_specs:
            eprint("No such job spec:", job_spec)
            eprint(f"\nAvailable under {get_jobs_dir().absolute()}:")
            for job_spec in job_specs:
                eprint("-", job_spec)
            return os.EX_NOINPUT
        try:
            # Validate job spec
            load_job_spec(job_spec)
        except ValueError as e:
            eprint("Could not load job spec:", job_spec)
            print(e)
            return os.EX_NOINPUT
        return os.EX_OK

    def submit(self: "CLI", job_spec: str) -> int:
        """
        Submit a job array for an existing job spec

        Parameters
        ----------
        job_spec : str
            The name of the job spec (folder name) to use

        Returns
        -------
        int
            The exit status of the operation
        """
        status = self.validate(job_spec)
        self.require_can_use_client()
        if status != os.EX_OK:
            return status
        try:
            response = launch_job_array(job_spec)
            print(response)
        except NoTargetsAvailableError as e:
            eprint("No targets available to run job spec:", e.job_spec)
            sys.exit(os.EX_UNAVAILABLE)
        return os.EX_OK

    def status(
        self: "CLI",
        count: int = 10,
        completed: bool = False,
        failed: bool = False,
        canceled: bool = False,
        all: bool = False,
    ) -> int:
        """
        Get the status of submitted jobs

        Parameters
        ----------
        count : int
            The maximum number of jobs to list
        completed : bool
            If True, output jobs that have successfully completed
        failed : bool
            If True, output jobs that have failed
        canceled : bool
            If True, output jobs that have been canceled
        all : bool
            If True, output jobs with any state

        Returns
        -------
        int
            The exit status of the operation
        """
        os.chdir(Path.home())
        df = get_job_outputs()
        df.drop(columns=["path", "pid"], inplace=True)
        pending_scheduled_running = all or not (completed or failed or canceled)

        def filter_status(status: str) -> bool:
            """
            Filter jobs based on their status.

            Parameters
            ----------
            status : str
                The status of the job

            Returns
            -------
            bool
                True, if the job should be included
            """
            if all:
                return True
            status_prefix = status.lower().split()[0]
            if status_prefix == "completed":
                return completed
            elif status_prefix == "failed":
                return failed
            elif status_prefix == "canceled":
                return canceled
            else:
                return pending_scheduled_running

        df["status"] = df["status"].apply(lambda x: x if filter_status(x) else None)
        df = df[~df["status"].isnull()]
        df = df.tail(n=max(0, count))
        if len(df) == 0:
            eprint("No jobs.")
            return os.EX_TEMPFAIL
        print(df.to_string(index=False))
        return os.EX_OK

    def cancel(self: "CLI", array_or_job: str, no_confirm: bool = False) -> int:
        """
        Cancel submitted jobs

        Parameters
        ----------
        array_or_job : str
            Array or job full job ID (array ID and array index) to match against when checking if a job should be canceled
        no_config : bool
            If true, the jobs will be canceled without prompting the user to confirm

        Returns
        -------
        int
            The exit status of the operation
        """
        if any(not (c.isalnum() or c in "_") for c in array_or_job):
            eprint(
                'Bad job pattern. (Supports only valid job_id characters (digits and "_").)'
            )
            return os.EX_USAGE
        os.chdir(Path.home())
        df: pd.DataFrame = get_job_outputs()
        if "_" not in array_or_job:
            array_or_job += "_.*"  # Any array_idx (since not given)
        if array_or_job.endswith("_"):
            array_or_job += ".*"  # Any array_idx (since not given)
        if len(df) > 0:
            df = pd.DataFrame(
                df[~df["pid"].isna()]
            )  # Only jobs that have not yet ended
            df = pd.DataFrame(
                df[df["job_id"].str.contains(f"^{array_or_job}$", regex=True)]
            )
        if len(df) == 0:
            eprint("No jobs.")
            return os.EX_TEMPFAIL
        was_confirmed = False
        if not no_confirm:
            print(f"Confirm cancellation of jobs:\n{', '.join(df['job_id'].values)}")
            try:
                was_confirmed = input('\nType "yes": ').strip() == "yes"
            except KeyboardInterrupt:
                pass
        if not (no_confirm or was_confirmed):
            eprint("Aborted.")
            return os.EX_OK
        pids = df["pid"].astype(int).values
        for pid in pids:
            try:
                os.kill(pid, signal.SIGINT)
            except ProcessLookupError:
                pass  # Process no longer alive anyway

        def wait_pid(pid: int, check_interval: float = 1) -> None:
            """
            Wait until the process with a given pid terminates using a semi-busy loop.

            Parameters
            ----------
            pid : int
                The PID of the process to wait for
            check_interval : float
                Time in seconds between checking the status of the process
            """
            SIG_CHECK_PID_EXISTS = 0
            while True:
                try:
                    os.kill(pid, SIG_CHECK_PID_EXISTS)
                    sleep(check_interval)
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

    def purge(self: "CLI", target_id: str, no_confirm: bool = False) -> int:
        """
        Delete all job files from a target.

        Parameters
        ----------
        target_id : str
            ID of the target on which all job files should be deleted
        no_config : bool
            If true, the target will be purged without prompting the user to confirm

        Returns
        -------
        int
            The exit status of the operation
        """
        self.require_can_use_client()
        os.chdir(Path.home())
        df: pd.DataFrame = get_job_outputs()
        # Ignore finished jobs
        df = df.dropna()
        target: Target
        try:
            target = [t for t in self.__client.targets if t.id == target_id][0]
        except Exception:
            eprint("Could not find target with this ID:", target_id)
            sys.exit(os.EX_USAGE)
        jobs_using_target = df[df["status"].str.contains(target_id, na=False)][
            "job_id"
        ].values
        if len(jobs_using_target) > 0:
            eprint("Target is still being used by some jobs:", *jobs_using_target)
            sys.exit(os.EX_TEMPFAIL)
        was_confirmed = False
        if not no_confirm:
            print("Confirm purging all jobs from:", target_id)
            try:
                was_confirmed = input('\nType "yes": ').strip() == "yes"
            except KeyboardInterrupt:
                pass
        if not (no_confirm or was_confirmed):
            eprint("Aborted.")
            return os.EX_OK
        remote_target = remote_target_from_target(target)
        try:
            remote_target.purge()
            return os.EX_OK
        except Exception:
            eprint("Failed.")
            return os.EX_TEMPFAIL

    def run(self: "CLI") -> int:
        """
        Execute the CLI in the current process (blocking).

        Returns
        -------
        int
            The exit status of the CLI (0 indicates success/no error).
        """
        argv = sys.argv
        argparser = argparse.ArgumentParser(description=(CLI.__doc__ or "").strip())
        command_functions = [
            self.create,
            self.submit,
            self.validate,
            self.status,
            self.cancel,
            self.purge,
            self.ssh_config,
        ]
        commands = {f.__name__.replace("_", "-"): f for f in command_functions}
        subparsers = argparser.add_subparsers(dest="command", required=True)
        for command, f in commands.items():
            docstring = f.__doc__
            subparser = subparsers.add_parser(
                command, help=(docstring if docstring else "").strip().splitlines()[0]
            )
            full_arg_spec = inspect.getfullargspec(f)
            args = full_arg_spec.args
            annotations = full_arg_spec.annotations
            defaults = [] if full_arg_spec.defaults is None else full_arg_spec.defaults
            for i, arg in enumerate(args):
                dest = arg.replace("_", "-")
                if dest == "self":
                    continue
                kwargs: Dict[str, Any] = dict()
                default = None
                if i >= len(args) - len(defaults):
                    default = defaults[i - (len(args) - len(defaults))]
                    dest = f"--{dest}"
                if arg in annotations:
                    arg_type = annotations[arg]
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


def main() -> int:
    """
    Execute command line tool.

    Returns
    -------
    int
        The exit code
    """
    try:
        config = Config.load(raise_on_missing=True)
    except FileNotFoundError as e:
        eprint(e)
        return os.EX_CONFIG
    except ValidationError as e:
        eprint(e.json(indent=3))
        return os.EX_CONFIG
    client = Client(config)
    return CLI(client).run()


if __name__ == "__main__":
    main()
