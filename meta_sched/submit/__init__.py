from pathlib import Path

from meta_sched import env
from meta_sched.api.client import Client
from meta_sched.submit.cli import CLI
from meta_sched.submit.daemon import Daemon
from meta_sched.utils import try_become_root


def run_cli() -> int:
    return CLI(Path(env.get("MS_SUBMITD_SOCKET"))).run()


def run_daemon() -> int:
    try_become_root(True)
    client = Client(env.get("MS_API_HOST"), int(env.get("MS_API_PORT")))
    return Daemon(
        Path(env.get("MS_SUBMITD_SOCKET")),
        client.create_array_id,
    ).run()
