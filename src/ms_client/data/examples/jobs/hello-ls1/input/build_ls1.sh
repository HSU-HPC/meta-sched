#! /bin/bash

# shellcheck disable=SC2089
BUILD_ARGS_LS1="-DENABLE_ADIOS2=OFF -DENABLE_MPI=ON -DOPENMP=ON -DENABLE_AUTOPAS=OFF -DENABLE_UNIT_TESTS=OFF -DENABLE_ALLLBL=ON -DMAMICO_COUPLING=OFF"

set -e

clear || :

if ! command -v cmake >/dev/null 2>&1
then
    # Try to load cmake module (required on some systems)
    ml cmake
fi

if ! command -v mpicxx >/dev/null 2>&1
then
    # Try to load MPI module (required on some systems)
    ml mpi
fi


CWD=$(pwd)
cd "$(dirname "$0")"
ROOT=$(pwd)

MARDYN_BIN_PATH=$(which MarDyn || :)
ARGS=("$@")
if [[ -z "$MARDYN_BIN_PATH" || ! " ${ARGS[*]} " =~ " --find " ]]; then
    echo "::: Downloading latest version of ls1 :::"
    cd "$ROOT"
    git clone --depth 1 https://github.com/ls1mardyn/ls1-mardyn.git || :
    cd ls1-mardyn
    git reset --hard
    git checkout master
    git pull

    echo "::: Building ls1 :::"
    mkdir -p build
    cd build
    # shellcheck disable=SC2046,SC2116,SC2090,SC2086
    cmake $(echo $BUILD_ARGS_LS1) ..
    make MarDyn -j"$(nproc)"
    MARDYN_BIN_PATH="$(realpath -s --relative-to="$CWD" "$(pwd)")/src/MarDyn"
else
    echo "Found existing binary: $MARDYN_BIN_PATH"
fi

ln -sf "$MARDYN_BIN_PATH" "$CWD/MarDyn"

