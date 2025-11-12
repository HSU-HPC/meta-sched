#! /bin/bash

# Build ls1 from source
#
# Use --find to locate any installed MarDyn binary
# Use --download-only to skip compilation
# Use --skip-download to build only
#

# shellcheck disable=SC2089
BUILD_ARGS_LS1="-DENABLE_ADIOS2=OFF -DENABLE_MPI=ON -DOPENMP=ON -DENABLE_AUTOPAS=OFF -DENABLE_UNIT_TESTS=OFF -DENABLE_ALLLBL=ON -DMAMICO_COUPLING=OFF"

set -e

clear || :

# Try to load GCC 14 explicitly (required on some systems)
ml compiler/gcc/14 || :

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

MARDYN_BIN_PATH=$(command -v MarDyn >/dev/null || :)
ARGS=("$@")
if [[ -z "$MARDYN_BIN_PATH" || ! " ${ARGS[*]} " =~ " --find " ]]; then
    SRC_DIR="$(realpath ls1-mardyn)"
    if [[ " ${ARGS[*]} " =~ " --skip-download " ]]; then
        echo "::: Using source directory $SRC_DIR :::"
        cd $SRC_DIR
    else
        echo "::: Downloading latest version of ls1 to $SRC_DIR :::"
        cd "$ROOT"
        git clone --depth 1 https://github.com/ls1mardyn/ls1-mardyn.git $SRC_DIR || :
        cd $SRC_DIR
        git reset --hard
        git checkout master
        git pull
    fi

    if [[ " ${ARGS[*]} " =~ " --download-only " ]]; then
        exit 0
    fi

    echo "::: Building ls1 :::"
    mkdir -p build
    cd build
    CC=$(command -v gcc)
    CXX=$(command -v g++)
    export CC
    export CXX
    # shellcheck disable=SC2046,SC2116,SC2090,SC2086
    cmake $(echo $BUILD_ARGS_LS1) ..
    make MarDyn -j"$(nproc)"
    MARDYN_BIN_PATH="$(realpath -s --relative-to="$CWD" "$(pwd)")/src/MarDyn"
else
    echo "Found existing binary: $MARDYN_BIN_PATH"
fi

ln -sf "$MARDYN_BIN_PATH" "$CWD/MarDyn"

