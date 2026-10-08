#! /bin/bash

set -e

if [[ -z "${1:-}" ]]; then
    echo "Usage: $0 <#particle histories>" >&2
    exit 1
fi

MPIEXEC=$(command -v mpiexec)

# Measure energy if praprl (https://github.com/HSU-HPC/praplr) is installed
if command -v praplr >/dev/null 2>&1; then
    echo "Measuring energy with prapl." >&2
    PRAPLR_BIN=$(command -v praplr)
    PRAPLR_CMD=("$PRAPLR_BIN" -o ./praplr-output --)
    PRAPLR_SUMMARIZE_BIN=$(command -v praplr-summarize.py)
    PRAPLR_SUMMARIZE_CMD="$PRAPLR_SUMMARIZE_BIN ./praplr-output"
else
    echo "prapl binary not found. (Energy measurement not possible.)" >&2
    PRAPLR_CMD=()
    PRAPLR_SUMMARIZE_CMD=":"
fi

# Install location of ECP Proxy Apps (https://github.com/HSU-HPC/ProxyAppsSetup)
PROXY_APPS_SETUP_DIR=$HOME/spack-ecp-proxy-apps

# shellcheck disable=SC1091
source "$PROXY_APPS_SETUP_DIR"/env/xsbench.sh

# Explicit OpenMP policies required on some clusters 
export OMP_NUM_THREADS="$MS_RANK_CORES"
export OMP_PROC_BIND=spread
export OMP_PLACES=cores

# Explicit OpenMPI policy required on some clusters 
$MPIEXEC -np "$MS_NODES" --bind-to none `# NOTE: This is OpenMPI specific!` \
    -- "${PRAPLR_CMD[@]}" XSBench -t "$MS_RANK_CORES" -s large -p "$1" -l 100 || : # Catch checksum fails
$PRAPLR_SUMMARIZE_CMD
