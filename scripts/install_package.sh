#! /bin/bash

set -e

SCRIPT_PATH="$(readlink -f "$0")"
cd "$(dirname "$(dirname "$SCRIPT_PATH")")"

echo "=== Install package ==="
pipx install dist/*.whl --force

echo "=== Done ==="
