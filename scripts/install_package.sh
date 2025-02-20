#! /bin/bash

set -e

SCRIPT_PATH="$(readlink -f "$0")"
cd "$(dirname "$(dirname "$SCRIPT_PATH")")"

./scripts/build_package.sh

echo "=== Uninstall package (if present) ==="
pipx uninstall meta-sched || :

echo "=== Install package ==="
pipx install dist/*.whl --force

echo "=== Done ==="
