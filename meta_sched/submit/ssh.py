from pathlib import Path
from typing import Tuple

from paramiko import SSHConfig


def __get_config_paths() -> Tuple[Path, Path]:
    dir_path = Path.home() / ".ssh"
    base_config_path = dir_path / "config"
    config_path = dir_path / "config.d" / "meta-sched"
    return config_path, base_config_path


def get_config() -> SSHConfig:
    try:
        return SSHConfig.from_path(__get_config_paths()[0])
    except FileNotFoundError:
        return SSHConfig()


def update_config() -> None:
    config_path, base_config_path = __get_config_paths()
    # region Create/update files if necessary
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        config_path.write_text("")
    base_config = base_config_path.read_text() if base_config_path.is_file() else ""
    include = "Include config.d/meta-sched"
    if include not in [s.strip() for s in base_config.splitlines()]:
        with open(base_config_path, "a") as file:
            print(f"\n{include}", file=file)
