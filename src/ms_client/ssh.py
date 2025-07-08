"""Module containing functionality related to SSH."""

import getpass
from pathlib import Path
from typing import Dict, Tuple

from paramiko import SSHConfig


def has_ssh_config_entry(target_id: str) -> bool:
    """
    Check if the current user can use a target system.

    Parameters
    ----------
    target_id : str
        The ID of the target system

    Returns
    -------
    bool
        True, if the the current user has SSH credentials for this target
    """
    config = get_config()
    return str(target_id) in config.get_hostnames() and "user" in config.lookup(
        str(target_id)
    )


def get_config_paths() -> Tuple[Path, Path]:
    """
    Get the paths of the main SSH configuration file and the meta-scheduler SSH configuration file of the current user.

    Returns
    -------
    Tuple[Path, Path]
        the paths of the main and meta-scheduler SSH configuration file of the current user
    """
    dir_path = Path.home() / ".ssh"
    base_config_path = dir_path / "config"
    config_path = dir_path / "config.d" / "meta-sched"
    return config_path, base_config_path


def get_config() -> SSHConfig:
    """
    Get the main SSH configuration of the current user.

    Returns
    -------
    SSHConfig
        The SSH configuration
    """
    try:
        return SSHConfig.from_path(get_config_paths()[0])
    except FileNotFoundError:
        return SSHConfig()


def update_config(include_targets_hostnames: Dict[str, str]) -> int:
    """
    Update the SSH configuration files of the current user.

    Parameters
    ----------
    include_targets_hostnames : Dict[str, str]
        The mapping of target identifiers to hostnames for the targets available for executing jobs through the meta-scheduler

    Returns
    -------
    int
        The number of targets for which no credentials have been added to the SSH configuration yet
    """
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
