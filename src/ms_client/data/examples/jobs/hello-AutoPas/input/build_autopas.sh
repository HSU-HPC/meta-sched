#! /bin/bash

set -e

cd "$(dirname "$0")"

cd AutoPas
mkdir -p build
cd build

LOG_ITERATIONS=ON
LOG_TUNINGRESULTS=ON

# Try to load modules (required on some systems)
ml gcc &>/dev/null || :
ml cmake &>/dev/null || :

cmake \
    -DMD_FLEXIBLE_FUNCTOR_AUTOVEC=ON \
    -DAUTOPAS_BUILD_EXAMPLES=ON \
    -DAUTOPAS_BUILD_TESTS=OFF \
    -DAUTOPAS_ENABLE_ENERGY_MEASUREMENTS=ON \
    -DAUTOPAS_OPENMP=ON \
    -DCMAKE_BUILD_TYPE=Release \
    -DAUTOPAS_LOG_ITERATIONS=$LOG_ITERATIONS \
    -DAUTOPAS_LOG_TUNINGRESULTS=$LOG_TUNINGRESULTS \
    -DPMT_BUILD_RAPL=ON \
    ..
make -j$(($(nproc)/2)) md-flexible
