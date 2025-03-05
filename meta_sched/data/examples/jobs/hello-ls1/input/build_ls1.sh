#! /bin/bash

# shellcheck disable=SC2089
BUILD_ARGS_LS1="-DENABLE_ADIOS2=OFF -DENABLE_MPI=OFF -DOPENMP=ON -DENABLE_AUTOPAS=OFF -DENABLE_UNIT_TESTS=OFF -DENABLE_ALLLBL=OFF -DMAMICO_COUPLING=OFF"

set -e

clear || :

CWD=$(pwd)
cd "$(dirname "$0")"
ROOT=$(pwd)

echo "::: Downloading latest version of ls1 :::"
cd "$ROOT"
git clone --depth 1 https://github.com/ls1mardyn/ls1-mardyn.git || :
cd ls1-mardyn
git pull

echo "::: Building ls1 :::"
mkdir -p build
cd build
# shellcheck disable=SC2046,SC2116,SC2090,SC2086
cmake $(echo $BUILD_ARGS_LS1) ..
make MarDyn -j"$(nproc)"

ln -sf "$(realpath -s --relative-to="$CWD" "$(pwd)")/src/MarDyn" "$CWD/MarDyn"

