#! /bin/bash

set -e

SCRIPT_PATH="$(readlink -f "$0")"
cd "$(dirname "$(dirname "$SCRIPT_PATH")")"

sudo echo "become root" > /dev/null

PIDS=()

handle_sigint() {
    echo "Interrupted!"
    for PID in "${PIDS[@]}"; do
        kill -SIGINT "$PID"
    done
}

uv run ms-namesd  --sudo & PIDS+=($!)
uv run ms-submitd --sudo & PIDS+=($!)
uv run ms-schedd  --sudo & PIDS+=($!)

trap "handle_sigint" SIGINT
for PID in "${PIDS[@]}"; do
    wait "$PID"
done

