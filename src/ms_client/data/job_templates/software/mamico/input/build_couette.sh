#! /bin/bash

COMMIT_MAMICO=3e516cc3a5fd2e05130870868cbc1a72a2efaa9f
COMMIT_LS1_MAMICO=31e1e4819275f5fc20076758fa7da2f9ae4438e3

ENABLE_MPI="OFF"
if [ -n "$(which mpicxx)" ]; then
    ENABLE_MPI="ON"
fi

# shellcheck disable=SC2089
BUILD_ARGS_LS1="-DENABLE_ADIOS2=OFF -DENABLE_MPI=$ENABLE_MPI -DOPENMP=OFF -DENABLE_AUTOPAS=OFF -DENABLE_UNIT_TESTS=OFF -DENABLE_ALLLBL=OFF -DMAMICO_COUPLING=ON -DMAMICO_SRC_DIR='../..'"
BUILD_ARGS_MAMICO="-DCMAKE_BUILD_TYPE=Release -DBUILD_WITH_MPI=$ENABLE_MPI -DMD_SIM=LS1_MARDYN"

set -e

clear || :

# Try to load cmake module (required on some systems)
ml cmake || :

CWD=$(pwd)
cd "$(dirname "$0")"
ROOT=$(pwd)

echo "::: Downloading specified version of MaMiCo and ls1 :::"
cd "$ROOT"
mkdir -p mamico
cd mamico
if [ ! -f .checked_out ]; then
    (git init && git remote add origin https://github.com/HSU-HPC/MaMiCo.git) || :
    git fetch --depth 1 origin $COMMIT_MAMICO
    git checkout FETCH_HEAD
    git submodule update --init
    cd ls1
    git checkout $COMMIT_LS1_MAMICO
    cd ..
    echo -e "COMMIT_MAMICO=$COMMIT_MAMICO\nCOMMIT_LS1_MAMICO=$COMMIT_LS1_MAMICO" > .checked_out
fi

echo "::: Building ls1 for MaMiCo :::"
cd "$ROOT/mamico/ls1"
mkdir -p build
cd build
# shellcheck disable=SC2046,SC2116,SC2090,SC2086
cmake $(echo $BUILD_ARGS_LS1) ..
make MarDyn -j8

echo "::: Building MaMiCo :::"
cd "$ROOT/mamico"
mkdir -p build
cd build
# shellcheck disable=SC2046,SC2116,SC2086
cmake $(echo $BUILD_ARGS_MAMICO) ..
make couette -j8
ln -sf "$(realpath -s --relative-to="$CWD" "$(pwd)")/couette" "$CWD/couette"
