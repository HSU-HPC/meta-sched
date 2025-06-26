"""Module containing the meta scheduler HTTP API."""

import os
import sys

from ms_common.utils import eprint, try_become_root

from ms_server.api import API
from ms_server.config import Config
from ms_server.scheduler import Scheduler


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
    config = Config.load(config_path)
    scheduler: Scheduler = config.scheduler_class(config.targets)
    try:
        api = API(config.counter_file, scheduler)
        api.run(*config.endpoint)
    except PermissionError as e:
        eprint(e)
        eprint()
        eprint("Maybe try again with the --sudo flag?")
    return os.EX_OK


if __name__ == "__main__":
    sys.exit(main())
