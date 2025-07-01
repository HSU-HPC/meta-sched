"""Module containing the Meta Scheduler HTTP API."""

import asyncio
import os
import signal
import sys

from ms_common.utils import eprint, try_become_root
from pydantic import ValidationError

from ms_server.api import API
from ms_server.config import Config
from ms_server.model import Model
from ms_server.scheduling import Policy


async def scheduling_loop(
    scheduler: Policy, scheduling_loop_interval: float, model: Model
) -> None:
    """
    Run the scheduling loop (non-blocking).

    Parameters
    ----------
    scheduler : Policy
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
            await scheduler.update(pending_jobs)
            sleep_time = max(
                0,
                scheduling_loop_interval
                - (asyncio.get_event_loop().time() - loop_start),
            )
            await asyncio.sleep(sleep_time)
    except asyncio.CancelledError:
        pass


async def __run_server(
    api: API, scheduler: Policy, model: Model, config: Config
) -> None:
    """
    Run the Meta Scheduler server asynchronously.

    Parameters
    ----------
    api : API
        The HTTP API of the Meta Scheduler server
    scheduler : Policy
        The scheduling policy to be applied by the Meta Scheduler
    model : Model
        The state of the Meta Scheduler
    config : Config
        The configuration for the Meta Scheduler Server
    """
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    scheduler_task = asyncio.create_task(
        scheduling_loop(scheduler, config.scheduling_loop_interval, model)
    )

    def shutdown() -> None:
        """Signal handler to shut down the scheduling loop."""
        stop_event.set()

    loop.add_signal_handler(signal.SIGINT, shutdown)
    loop.add_signal_handler(signal.SIGTERM, shutdown)
    server, server_task = api.serve()
    await stop_event.wait()
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
    server.should_exit = True
    await server_task


def main() -> int:
    """
    Execute HTTP API as root with parameters from the environment or default values.

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
    scheduler: Policy = config.scheduler_class(config.targets)
    try:
        model = Model()
        api = API(config.host, config.port, config.targets, model)
        asyncio.run(__run_server(api, scheduler, model, config))
    except PermissionError as e:
        eprint(e)
        eprint()
        eprint("Maybe try again with the --sudo flag?")
    return os.EX_OK


if __name__ == "__main__":
    sys.exit(main())
