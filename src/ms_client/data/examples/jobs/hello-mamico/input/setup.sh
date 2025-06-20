#! /bin/bash

# Compile with MPI if available
if which module >/dev/null; then
    module load mpi
    module load cmake
    module list >&2
fi

set -e

"$MS_INPUT"/build_couette.sh >&2
"$MS_INPUT"/generate_configs.py \
    --mpi-ranks "$MPI_RANKS" \
    --md-size 60 \
    --cell-size 2.5 \
    >&2
