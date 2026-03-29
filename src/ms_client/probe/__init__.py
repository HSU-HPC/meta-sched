#! /usr/bin/env python3

"""Module containing probe used to update remote target status at Meta Scheduler Server."""

import argparse
import multiprocessing
import os
import sys
import time
from datetime import datetime
from typing import List, Optional

from ms_client.utils import sleep
from ms_common.schemas import PowerForecast, Target, TargetStatus
from ms_common.utils import eprint
from pydantic import ValidationError

from ms_client.client import Client
from ms_client.config import Config
from ms_client.probe.datacenter_api_client import (
    ApiArgs,
    Forecast,
    ForecastSource,
)
from ms_client.remote_target import RemoteTarget
from ms_client.remote_target.factory import remote_target_from_target
from ms_client.ssh import has_ssh_config_entry


def _get_target_status(
    target: Target,
    remote_target: RemoteTarget,
    forecast_source: Optional[ForecastSource],
    verbose: bool = False,
) -> TargetStatus:
    """
    Fetch the status of a remote target.

    Parameters
    ----------
    target : Target
        The target to monitor for updates
    remote_target : RemoteTarget
        An instance of the remote target to execute commands (fetch status)
    forecast_source : Optional[ForecastSource]
        ForecastSource for the datacenter API of this target
        (Used to fetch additional data about the state of the target)
    verbose : bool
        Print some fetched information about the target (Defaults to False)
    """
    target_status: TargetStatus
    print(f"===== Fetched state at {datetime.now()} =====")
    try:
        target_status = remote_target.get_status()
    except NotImplementedError:
        eprint(
            f'Getting the queue status is not implemented for target {target.id} with batch system "{target.batch_system}"'
        )
        raise
    assert target_status  # Should not be None
    if verbose:
        print("Target State:")
        print("Nodes available:", target_status.nodes_available)
        print("Nodes in use:", target_status.nodes_in_use)
        print("Nodes unavailable:", target_status.nodes_unavailable)
        print("Current job count:", len(target_status.jobs_status))
    if forecast_source:
        forecasts = forecast_source.get_forecasts()[0]
        target_status.power_forecasts = [
            PowerForecast(
                timestamp=f.timestamp,
                nodes_renewable_powered=f.renewable_powered,
                reliability=f.reliability,
            )
            for f in forecasts
        ]
        df = Forecast.forecasts_to_dataframe(forecasts)
        if verbose:
            print("\nPower Forecast:")
            print(df.head().to_string(index=False))
            print()
    return target_status


def _monitor_target(
    client: Client,
    target: Target,
    interval: float,
    forecast_source: Optional[ForecastSource],
    verbose: bool = False,
) -> None:
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
    forecast_source : Optional[ForecastSource]
        Forecast source for the datacenter API of this target
        (Used to fetch additional data about the state of the target)
    verbose : bool
        Print some fetched information about the target (Defaults to False)
    """
    api_key = os.environ["MS_API_KEY"]
    print(f"Started monitor for {target.id} ({target.host})")
    with remote_target_from_target(target) as remote_target:
        while True:
            start = time.perf_counter()
            target_status: Optional[TargetStatus]
            try:
                target_status = _get_target_status(
                    target, remote_target, forecast_source, verbose
                )
            except Exception as e:
                eprint("Error fetching target status:", e)
                break
            try:
                client.update_target_status(target.id, target_status, api_key)
            except Exception as e:
                eprint("Error sending target status to Meta Scheduler API:", e)
                break
            sleep_for = max(0, interval - (time.perf_counter() - start))
            try:
                sleep(sleep_for)
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
    arg_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print fetched information (brief) to stdout",
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
    targets_config = {t.id: t for t in config.targets}
    for t in client.targets:
        if t.id in target_ids:
            if not has_ssh_config_entry(t.id):
                raise RuntimeError(f"No SSH alias set up for target {t.id} ({t.host})")
            target_ids.remove(t.id)
            datacenter_api_forecast_source: Optional[ForecastSource] = None
            if t.id in targets_config:
                datacenter_api_endpoint = targets_config[t.id].datacenter_api_endpoint
                datacenter_api_forecast_source_id = targets_config[
                    t.id
                ].datacenter_api_forecast_source_id
                datacenter_api_forecast_source = (
                    ForecastSource(
                        datacenter_api_forecast_source_id,
                        ApiArgs(datacenter_api_endpoint),
                    )
                    if datacenter_api_endpoint
                    and datacenter_api_forecast_source_id is not None
                    else None
                )
            p = multiprocessing.Process(
                target=_monitor_target,
                args=(
                    client,
                    t,
                    args.interval,
                    datacenter_api_forecast_source,
                    args.verbose,
                ),
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
