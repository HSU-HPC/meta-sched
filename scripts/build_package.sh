#! /bin/bash

set -e

SCRIPT_PATH="$(readlink -f "$0")"
cd "$(dirname "$(dirname "$SCRIPT_PATH")")"

echo "=== Sync project ==="
uv sync
uv lock

echo "=== Build package ==="
uv build

echo "=== Done ==="
