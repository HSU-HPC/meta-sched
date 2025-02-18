import signal
from pathlib import Path

from meta_sched import env
from meta_sched.api import API
from meta_sched.api.client import Client
from meta_sched.submit.daemon import Daemon
from meta_sched.utils import try_become_root


def run_service() -> int:
    try_become_root(True)
    host = env.get("MS_API_HOST")
    port = int(env.get("MS_API_PORT"))
    process_api = API(
        host, port, Path(env.get("MS_SCHEDD_CONFIG")).absolute()
    ).start_process()
    api_client = Client(host, port)
    process_submitd = Daemon(
        Path(env.get("MS_SUBMITD_SOCKET")), api_client.create_array_id
    ).start_process()
    signal.sigwait([signal.SIGINT, signal.SIGTERM])
    process_submitd.terminate()
    process_submitd.join()
    process_api.kill()  # terminate does not work for flask
    process_api.join()
    return 0
