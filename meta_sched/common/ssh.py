import getpass
from pathlib import Path
from typing import Dict, Tuple

from paramiko import SSHConfig

DEFAULT_PORT = 22

def get_config_paths() -> Tuple[Path, Path]:
    dir_path = Path.home() / ".ssh"
    base_config_path = dir_path / "config"
    config_path = dir_path / "config.d" / "meta-sched"
    return config_path, base_config_path


def get_config() -> SSHConfig:
    try:
        return SSHConfig.from_path(get_config_paths()[0])
    except FileNotFoundError:
        return SSHConfig()


def update_config(include_targets_hostnames: Dict[str, str]) -> int:
    # Add meta-sched SSH config and include it in SSH config
    config_path, base_config_path = get_config_paths()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        config_path.write_text("")
    base_config = base_config_path.read_text() if base_config_path.is_file() else ""
    include = "Include config.d/meta-sched"
    if include not in [s.strip() for s in base_config.splitlines()]:
        with open(base_config_path, "a") as file:
            print(f"\n{include}", file=file)
    # Add missing targets
    config = get_config()
    targets_missing_user = 0
    for target, hostname in include_targets_hostnames.items():
        target_config = config.lookup(target)
        if "user" not in target_config:
            targets_missing_user += 1
        is_in_config = target_config["hostname"] == hostname
        if not is_in_config:
            with open(config_path, "a") as file:
                print("\nHost", target, file=file)
                print("\tHostName", hostname, file=file)
                print(f"\t#User TODO (e.g. {getpass.getuser()})", file=file)
                print("\t#IdentityFile TODO (e.g. ~/.ssh/id_rsa)", file=file)
    return targets_missing_user
