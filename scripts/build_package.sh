#! /bin/bash

set -e

SCRIPT_PATH="$(readlink -f "$0")"
cd "$(dirname "$(dirname "$SCRIPT_PATH")")"

echo "=== Syncing project ==="
uv sync
uv lock

echo "=== Building package ==="
uv build
