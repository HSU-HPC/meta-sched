import os
import signal
from pathlib import Path

from meta_sched.api import API
from meta_sched.api.client import Client
from meta_sched import env
from meta_sched.common.utils import try_become_root
from meta_sched.config import Config
from meta_sched.scheduler import Scheduler
from meta_sched.submit.cli import CLI
from meta_sched.submit.daemon import Daemon


def __get_api() -> API:
    host = env.get("MS_API_HOST")
    port = int(env.get("MS_API_PORT"))
    config = Config.load(Path(env.get("MS_SCHEDD_CONFIG")))
    scheduler: Scheduler = config.scheduler_class(config.targets)
    return API(host, port, config.counter_file, scheduler)


def serve_api() -> int:
    try_become_root(False)
    __get_api().run()
    return os.EX_OK


def __get_submitd() -> Daemon:
    host = env.get("MS_API_HOST")
    port = int(env.get("MS_API_PORT"))
    socket_path = Path(env.get("MS_SUBMITD_SOCKET"))
    return Daemon(socket_path, Client(host, port))


def run_submitd() -> int:
    try_become_root(True)
    __get_submitd().run()
    return os.EX_OK


def run_service() -> int:
    try_become_root(True)
    host = env.get("MS_API_HOST")
    port = int(env.get("MS_API_PORT"))
    socket_path = Path(env.get("MS_SUBMITD_SOCKET"))
    process_api = __get_api().start_process()
    process_submitd = Daemon(socket_path, Client(host, port)).start_process()
    signal.sigwait([signal.SIGINT, signal.SIGTERM])
    process_submitd.terminate()
    process_submitd.join()
    process_api.kill()  # terminate does not work for flask
    process_api.join()
    return os.EX_OK


def run_cli() -> int:
    host = env.get("MS_API_HOST")
    port = int(env.get("MS_API_PORT"))
    socket_path = Path(env.get("MS_SUBMITD_SOCKET"))
    return CLI(socket_path, Client(host, port)).run()
