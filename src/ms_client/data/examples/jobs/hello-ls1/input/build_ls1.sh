#! /bin/bash

# Build ls1 from source
#
# Use --find to locate any installed MarDyn binary
# Use --download-only to skip compilation
# Use --skip-download to build only
#

# shellcheck disable=SC2089
BUILD_ARGS="-DENABLE_ADIOS2=OFF -DENABLE_MPI=ON -DOPENMP=ON -DENABLE_AUTOPAS=OFF -DENABLE_UNIT_TESTS=OFF -DENABLE_ALLLBL=ON -DMAMICO_COUPLING=OFF"
GIT_REPO_URL=https://github.com/ls1mardyn/ls1-mardyn.git
BRANCH=master

set -e

clear || :


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
        # Clone shallowly if it doesn’t exist
        if [ ! -d "$SRC_DIR/.git" ]; then
            echo "Fetching source code..."
            git clone --depth 1 -b "$BRANCH" "$GIT_REPO_URL" "$SRC_DIR"
        else
            # Otherwise update and make shallow
            echo "Updating source code..."
            cd "$SRC_DIR"
            git fetch --depth=1 origin "$BRANCH"
            git checkout -B "$BRANCH" "origin/$BRANCH"
            git reset --hard "origin/$BRANCH"
            git reflog expire --expire=now --all || true
            git gc --prune=now --aggressive || true
        fi
    fi

    if [[ " ${ARGS[*]} " =~ " --download-only " ]]; then
        exit 0
    fi

    echo "::: Building ls1 :::"
    # Try to load recent GCC (required on some systems)
    ml gcc/13.2.0 &>/dev/null || : # HSUper
    ml compiler/gcc/14 &>/dev/null || : # WindHPC

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

    mkdir -p build
    cd build
    CC=$(command -v gcc)
    CXX=$(command -v g++)
    export CC
    export CXX
    # shellcheck disable=SC2046,SC2116,SC2090,SC2086
    cmake $(echo $BUILD_ARGS) ..
    make MarDyn -j"$(nproc)"
    MARDYN_BIN_PATH="$PWD/src/MarDyn"
else
    echo "Found existing binary: $MARDYN_BIN_PATH"
fi

echo "Creating link to $MARDYN_BIN_PATH from $ROOT/MarDyn."
ln -sf "$MARDYN_BIN_PATH" "$ROOT/MarDyn"
