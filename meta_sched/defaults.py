"""Module containing default environment variables."""

from meta_sched import data

MS_SERVICE_HOST = "localhost"
MS_SERVICE_PORT = 8001

MS_SCHED_CONFIG = data.get_examples_dir() / "config.toml"
