#! /bin/bash

set -e

SCRIPT_PATH="$(readlink -f "$0")"
cd "$(dirname "$(dirname "$SCRIPT_PATH")")"

echo "=== Sync project ==="
uv sync --upgrade
uv lock --upgrade

echo "=== Build package ==="
uv build --wheel

echo "=== Done ==="
