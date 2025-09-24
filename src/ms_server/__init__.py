"""Module containing the Meta Scheduler HTTP API."""

import argparse
import asyncio
import itertools
import os
import secrets
import string
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

import ms_common
import ms_common.schemas
from ms_common.schemas import JobKey, SchedulingDecisionType
from ms_common.utils import eprint, try_become_root
from pydantic import ValidationError

from ms_server.api import API
from ms_server.config import Config
from ms_server.db import DataBase
from ms_server.model import Model
from ms_server.scheduling import Policy


async def scheduling_loop(
    policy: Policy, scheduling_loop_interval: float, model: Model
) -> None:
    """
    Run the scheduling loop (non-blocking).

    Parameters
    ----------
    policy : Policy
        The scheduling policy to be applied
    scheduling_loop_interval : float
        The number of seconds between consecutive applications of the scheduling policy
    model : Model
        The state of the Meta Scheduler
    """
    try:
        for i in itertools.count():
            loop_start = asyncio.get_event_loop().time()
            pending_jobs = await model.get_pending_jobs()
            decided_jobs = await model.get_decided_jobs()
            # Filter out jobs which SHOULD already have completed (not yet reported), since they are irrelevant for scheduling new jobs
            decided_jobs = [
                job
                for job in decided_jobs
                if job.timestamp_start is None
                or job.timestamp_start
                + job.requested_seconds
                + scheduling_loop_interval
                > int(time.time())
            ]
            targets_status = await model.get_targets_status()
            # For debugging
            # print(f"Scheduling loop #{i} ({len(pending_jobs)} pending, {len(decided_jobs)} decided)")
            await policy.update(pending_jobs, decided_jobs, targets_status)
            sleep_time = max(
                0,
                scheduling_loop_interval
                - (asyncio.get_event_loop().time() - loop_start),
            )
            await asyncio.sleep(sleep_time)
    except asyncio.CancelledError:
        pass


def main() -> int:
    """
    Execute Server (HTTP API and scheduling loop).

    Returns
    -------
    int
        The exit code (Always 0, but server runs forever and does not return)
    """
    try_become_root(False)

    arg_parser = argparse.ArgumentParser(
        description="Meta Scheduler server application for scheduling jobs across multiple remote targets."
    )
    arg_parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=Config.get_default_config_path(),
        help="Path to the configuration file",
    )
    arg_parser.add_argument(
        "--use-example-config",
        action="store_true",
        help="Use the example configuration file",
    )
    args, _ = arg_parser.parse_known_args()

    config_path = args.config
    if not str(config_path).startswith("/"):
        eprint("Argument value for -c or --config must be an ABSOLUTE path.")
        sys.exit(os.EX_CONFIG)
    if not config_path.is_file():
        eprint(f"No configuration file was found at {config_path}.")
        config_path = Config.get_example_config_path()
        if not args.use_example_config:
            eprint(
                "Using the following example configuration, requires the flag --use-example-config:"
            )
            eprint()
            config_str = config_path.read_text()
            eprint(config_str)
            return os.EX_NOINPUT
        else:
            eprint(f"(Falling back on {config_path}.)")
    try:
        config = Config.load(config_path)
    except ValidationError as e:
        eprint(e.json(indent=3))
        sys.exit(os.EX_CONFIG)
    model = DataBase(config.db_url, config.targets)

    @asynccontextmanager
    async def lifespan(app: API) -> AsyncGenerator[Any, Any]:
        """
        The FastAPI lifespan used for setup and teardown code.
        (Initializes database and start the scheduling loop)

        Parameters
        ----------
        app : API
            (Unused)

        Returns
        -------
        AsyncGenerator[Any, Any]
            Generator used by FastAPI to distinguish setup and teardown code.
        """
        await model.init_models()
        scheduler_task = asyncio.create_task(
            scheduling_loop(scheduler, config.scheduling_loop_interval, model)
        )
        yield
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        await model.dispose()

    targets = {t.id: t for t in config.targets}

    async def on_schedule_job(
        job_key: JobKey, scheduling_decision: SchedulingDecisionType
    ) -> None:
        """
        Callback for the scheduling policy to apply a decision for a single job.

        Parameters
        ----------
        job_key : JobKey
            The key identifying the job for which a scheduling decision has been made
        scheduling_decision : SchedulingDecisionType
            The scheduling decision that should be applied to the job
        """
        seconds: Optional[int] = None
        if isinstance(scheduling_decision, ms_common.schemas.Assigned):
            target = targets[scheduling_decision.target_id]
            job = await model.get_job(job_key)
            seconds = job.spec.get_target_seconds(target, job.array_idx)
        await model.update_job(
            job_key,
            dict(scheduling_decision=scheduling_decision, requested_seconds=seconds),
        )

    scheduler: Policy = config.scheduler_class(on_schedule_job)
    for k, v in config.scheduler_parameter_overrides.items():
        setattr(scheduler, k, v)
    if "MS_API_KEY" not in os.environ:
        characters = string.ascii_letters + string.digits  # A-Z, a-z, 0-9
        api_key = "".join(secrets.choice(characters) for _ in range(32))
        os.environ["MS_API_KEY"] = api_key
        eprint("No API key specified in environment. (Generating randomly.)")
        eprint(f"MS_API_KEY={api_key}")
    api_key = os.environ["MS_API_KEY"]
    api = API(
        config.host, config.port, config.targets, model, api_key, lifespan=lifespan
    )
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    server, server_task = api.serve()
    try:
        loop.run_until_complete(server_task)
    except KeyboardInterrupt:
        server.should_exit = True
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
    return os.EX_OK


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PermissionError as e:
        eprint(e)
        eprint()
        eprint("Maybe try again with the --sudo flag?")
