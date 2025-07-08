"""Module containing the Meta Scheduler HTTP API."""

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

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
        while True:
            # TODO update jobs which have started and who must have finished, but have not been updated accordingly
            loop_start = asyncio.get_event_loop().time()
            pending_jobs = await model.get_pending_jobs()
            targets_status = await model.get_targets_status()
            print(
                {k.id: v for k, v in targets_status.items()}
            )  # FIXME just for testing
            await policy.update(pending_jobs, targets_status)
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
    config_path = Config.get_config_path()
    if not config_path.is_file():
        if "--use-default-config" not in sys.argv:
            eprint(f"No scheduler configuration was found at {config_path}.")
            eprint(
                "Using the following default configuration, requires the flag --use-default-config:"
            )
            eprint()
            config_str = config_path.read_text()
            eprint(config_str)
            return os.EX_NOINPUT
        config_path = Config.get_default_config_path()
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
        await model.update_job(job_key, dict(scheduling_decision=scheduling_decision))

    scheduler: Policy = config.scheduler_class(on_schedule_job)
    if "MS_API_KEY" not in os.environ:
        eprint(
            f"API key missing!\n\nUsage:\n\tMS_API_KEY=someSecret msserver {' '.join(sys.argv[1:])}"
        )
        exit(os.EX_USAGE)
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
