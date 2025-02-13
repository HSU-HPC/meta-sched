import os

from meta_sched import defaults

__defaults = {k: defaults.__dict__[k] for k in dir(defaults) if not k.startswith("__")}


def get(
    key: str,
) -> str:
    return os.getenv(key, __defaults[key])
