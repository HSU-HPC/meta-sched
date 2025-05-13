"""Main module of the meta-scheduler application."""

import os
import sys
from pathlib import Path

from meta_sched import env
from meta_sched.common.utils import eprint, try_become_root
from meta_sched.config import Config
from meta_sched.scheduler import Scheduler
from meta_sched.service import API
from meta_sched.service.client import Client
from meta_sched.submit.cli import CLI


def run_service() -> int:
    """
    Execute HTTP API as root with parameters from the environment or default values.

    Returns
    -------
    int
        The exit code (Always 0, but server runs forever and does not return)
    """
    try_become_root(False)
    host = env.get("MS_SERVICE_HOST")
    port = int(env.get("MS_SERVICE_PORT"))
    key_env_conf = "MS_SCHED_CONFIG"
    config_path = Path(env.get(key_env_conf))
    if not (env.has(key_env_conf) or "--use-default" in sys.argv):
        eprint(
            f"No scheduler configuration was given in the environment variable {key_env_conf}."
        )
        eprint(
            "Using the following default configuration, requires the flag --use-default:"
        )
        eprint()
        config_str = config_path.read_text()
        eprint(config_str)
        return os.EX_NOINPUT
    config = Config.load(config_path)
    scheduler: Scheduler = config.scheduler_class(config.targets)
    try:
        api = API(host, port, config.counter_file, scheduler)
        api.run()
    except PermissionError as e:
        eprint(e)
        eprint()
        eprint("Maybe try again with the --sudo flag?")
    return os.EX_OK


def run_cli() -> int:
    """
    Execute command line tool with parameters from the environment or default values.

    Returns
    -------
    int
        The exit code
    """
    host = env.get("MS_SERVICE_HOST")
    port = int(env.get("MS_SERVICE_PORT"))
    return CLI(Client(host, port)).run()
