#! /bin/bash

set -e

SCRIPT_PATH="$(readlink -f "$0")"
cd "$(dirname "$(dirname "$SCRIPT_PATH")")"

uv run ms-service --sudo
