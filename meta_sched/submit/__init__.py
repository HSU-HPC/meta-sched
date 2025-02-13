from pathlib import Path

from meta_sched import env
from meta_sched.names.client import Client as NameProviderClient
from meta_sched.submit.cli import CLI
from meta_sched.submit.daemon import Daemon
from meta_sched.utils import try_become_root


def run_cli() -> int:
    return CLI(Path(env.get("MS_SUBMITD_SOCKET"))).run()


def run_daemon() -> int:
    try_become_root(True)
    name_provider_client = NameProviderClient(
        env.get("MS_NAMESD_HOST"), int(env.get("MS_NAMESD_PORT"))
    )
    return Daemon(
        Path(env.get("MS_SUBMITD_SOCKET")),
        name_provider_client.get_new_name,
    ).run()
