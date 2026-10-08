#! /bin/bash

set -e

ROOT="$(dirname "$0")"

MD_FLEXIBLE_BIN=$ROOT/AutoPas/build/examples/md-flexible/md-flexible

# Delete any old outputs
rm -rf vtkOutput AutoPas_*.csv

export OMP_PLACES=threads
export OMP_PROC_BIND=close

$MD_FLEXIBLE_BIN --yaml-filename $ROOT/config.yaml

echo -n "mean_threads="
OUTPUT=$(ls AutoPas_tuningResults_*.csv)
python3 - << EOF
from pathlib import Path
lines = Path("$OUTPUT").read_text().splitlines()[1:]
thread_counts = [int(s.split(",")[-3]) for s in lines]
print(sum(thread_counts) / len(thread_counts))
EOF
echo "num_cores=$(nproc)"
