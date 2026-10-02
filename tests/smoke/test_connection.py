#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "meta-sched-client",
# ]
#
# [tool.uv.sources]
# meta-sched-client = { path = "../../packages/ms_client", editable = true }
# ///

"""
Script to test connection to a remote target.
"""

import argparse
import sys

from ms_client.client import Client
from ms_client.config import Config
from ms_client.remote_target import RemoteTarget

def test_connection(args: list[str]):
    """
    Test the connection to a remote target.

    Parameters
    ----------
    args : list[str]
        Command line arguments to parse
        (Expected exactly one: target_id)
    """
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("target_id", type=str)
    args = arg_parser.parse_args()
    sentinel = RemoteTarget._FactoryAccessToken()
    config = Config.load(raise_on_missing=True)
    client = Client(config)
    targets = [t for t in client.targets if t.id == args.target_id]
    assert len(targets) == 1
    target = targets[0]
    remote_target = RemoteTarget(sentinel, target)
    with remote_target._get_connection() as conn:
        remote_target._run(conn, "echo Successfully connected to $(hostname)!")

if __name__ == "__main__":
    test_connection(sys.argv)