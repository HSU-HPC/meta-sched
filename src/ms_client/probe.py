#! /usr/bin/env python3

"""Module containing probe used to update remote target status at Meta Scheduler Server."""

import argparse
import multiprocessing
import os
import sys
import time
from typing import List, Optional

from ms_common.schemas import Target, TargetStatus
from ms_common.utils import eprint
from pydantic import ValidationError

from ms_client.client import Client
from ms_client.config import Config
from ms_client.remote_target.factory import remote_target_from_target
from ms_client.ssh import has_ssh_config_entry


def monitor_target(client: Client, target: Target, interval: float) -> None:
    """
    Periodic monitoring of the status of a remote target via the Meta Scheduler API.

    Parameters
    ----------
    client : Client
        The Meta Scheduler API client
    target : Target
        The target to monitor for updates
    interval : float
        The number of seconds between subsequent updates of the target status
    """
    api_key = os.environ["MS_API_KEY"]
    print(f"Started monitor for {target.id} ({target.host})")
    remote_target = remote_target_from_target(target)
    while True:
        start = time.perf_counter()
        target_status: Optional[TargetStatus] = None
        try:
            target_status = remote_target.get_status()
        except NotImplementedError:
            eprint(
                f'Getting the queue status is not implemented for target {target.id} with batch system "{target.batch_system}"'
            )
            break
        try:
            assert target_status
            client.update_target_status(target.id, target_status, api_key)
        except Exception as e:
            eprint("Error sending target status to Meta Scheduler API:", e)
            break
        sleep_for = max(0, interval - (time.perf_counter() - start))
        try:
            time.sleep(sleep_for)
        except KeyboardInterrupt:
            break


def main() -> int:
    """
    Small utility which periodically queries the target state and sends it to the Meta Scheduler API.
    """
    arg_parser = argparse.ArgumentParser(description=(main.__doc__ or "").strip())
    arg_parser.add_argument(
        "-t",
        "--target-id",
        type=str,
        action="append",
        help="Add the ID of a target to monitor",
    )
    arg_parser.add_argument(
        "-i",
        "--interval",
        type=float,
        default=60,
        help="Target state update interval in seconds",
    )
    args = arg_parser.parse_args()
    target_ids = args.target_id
    if target_ids is None or len(target_ids) == 0:
        eprint(
            f"Add at least one target using msprobe -t <target ID> {' '.join(sys.argv[1:])}"
        )
        exit(os.EX_USAGE)

    if "MS_API_KEY" not in os.environ:
        eprint(
            f"API key missing!\n\nUsage:\n\tMS_API_KEY=someSecret msprobe {' '.join(sys.argv[1:])}"
        )
        exit(os.EX_USAGE)

    try:
        config = Config.load(raise_on_missing=True)
    except FileNotFoundError as e:
        eprint(e)
        return os.EX_CONFIG
    except ValidationError as e:
        eprint(e.json(indent=3))
        return os.EX_CONFIG
    client = Client(config)
    client.check_version_ok()
    processes: List[multiprocessing.Process] = []
    for t in client.targets:
        if t.id in target_ids:
            if not has_ssh_config_entry(t.id):
                raise RuntimeError(f"No SSH alias set up for target {t.id} ({t.host})")
            target_ids.remove(t.id)
            p = multiprocessing.Process(
                target=monitor_target, args=(client, t, args.interval)
            )
            processes.append(p)
    if len(target_ids) > 0:
        raise ValueError(f"Unknown target IDs: {', '.join(target_ids)}")
    for p in processes:
        p.start()
    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        pass
    return os.EX_OK


if __name__ == "__main__":
    main()
