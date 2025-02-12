from meta_sched.submit.cli import CLI
from meta_sched.submit.daemon import Daemon


def run_cli() -> int:
    return CLI().run()


def run_daemon() -> int:
    return Daemon().run()
