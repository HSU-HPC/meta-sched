from pathlib import Path

from meta_sched import env
from meta_sched.names.daemon import Daemon
from meta_sched.utils import try_become_root


def run_daemon() -> int:
    try_become_root()
    return Daemon(
        env.get("MS_NAMESD_HOST"),
        int(env.get("MS_NAMESD_PORT")),
        Path(env.get("MS_NAMESD_FILE")).absolute(),
    ).run()
