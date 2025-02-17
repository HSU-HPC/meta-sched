from pathlib import Path

MS_SUBMITD_SOCKET = "/var/run/meta-sched/ms-submitd.sock"

MS_API_HOST = "localhost"
MS_API_PORT = 8001

MS_SCHEDD_CONFIG = Path(__file__).parents[1] / "examples/config.toml"
