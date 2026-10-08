#! /bin/bash

# Run with MPI and fixed number of processes if module can be loaded
# (When using OpenMPI allow oversubscribing slots)
if module load mpi; then
    MPI_EXEC_ARGS=("-n" "$MPI_RANKS")
    if mpiexec --version | grep "OneAPI"; then
        MPI_EXEC_ARGS+=("--oversubscribe")
    fi
    mpiexec "${MPI_EXEC_ARGS[@]}" ./couette
    exit $?
fi
./couette
