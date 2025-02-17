from pathlib import Path

from meta_sched import env
from meta_sched.schedule.daemon import Daemon
from meta_sched.utils import try_become_root


def run_daemon() -> int:
    try_become_root()
    return Daemon(
        env.get("MS_API_HOST"),
        int(env.get("MS_API_PORT")),
        Path(env.get("MS_SCHEDD_CONFIG")).absolute(),
    ).run()
