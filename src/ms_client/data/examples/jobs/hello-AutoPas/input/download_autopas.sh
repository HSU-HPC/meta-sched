#! /bin/bash

set -e

AUTOPAS_REPO_URL=https://github.com/rubenhorn/AutoPas.git

cd "$(dirname "$0")"

# Fork with support for OpenMP thread count tuning
git clone $AUTOPAS_REPO_URL AutoPas || :
cd AutoPas
git checkout feature/thread-count || :
