#! /bin/bash

set -e

SCRIPT_PATH="$(readlink -f "$0")"
cd "$(dirname "$(dirname "$SCRIPT_PATH")")"

echo "=== Update project ==="
uv sync
uv lock

echo "=== Apply formatting ==="
uvx isort .
uvx ruff check --fix
uvx ruff format

echo "=== Perform static type checking for modules ==="

# shellcheck source=/dev/null
source .venv/bin/activate

echo -n "mypy " && mypy -p meta_sched
echo -n "pyright " && PYRIGHT_PYTHON_FORCE_VERSION=latest pyright -p meta_sched

echo "=== Done ==="

