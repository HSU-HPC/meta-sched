#! /usr/bin/env python3

import argparse
from functools import reduce
from pathlib import Path

# 1. Parse arguments
arg_parser = argparse.ArgumentParser()
arg_parser.add_argument("-n", "--mpi-ranks", type=int, default=1)
arg_parser.add_argument("-md", "--md-size", type=int, default=60)
arg_parser.add_argument("-c", "--cell-size", type=float, default=5)
args = arg_parser.parse_args()

# 2. Validate arguments
md_size = args.md_size
cell_size = args.cell_size
assert md_size % cell_size == 0
md_mpi_size = [1, 1, 1]
ranks = args.mpi_ranks
i = 0
ranks_remaining = ranks
while ranks_remaining % 2 == 0:
    ranks_remaining //= 2
    md_mpi_size[i] *= 2
    i = (i + 1) % len(md_mpi_size)
md_mpi_size[i] *= ranks_remaining
assert ranks == reduce(lambda a, b: a * b, md_mpi_size, 1)
for ax_ranks, ax in zip(md_mpi_size, "xyz"):
    cells = int(md_size // cell_size)
    if cells % ax_ranks != 0:
        print(
            f"Cannot have {ax_ranks} ranks for MD along {ax}-axis of size {cells} cells."
        )
        exit(1)

# 3. Apply substitute for template files
subsitutions = dict(
    MD_SIZE=10,
    MD_MPI_SIZE_X=md_mpi_size[0],
    MD_MPI_SIZE_Y=md_mpi_size[1],
    MD_MPI_SIZE_Z=md_mpi_size[2],
    CELL_SIZE=cell_size,
)


def apply_template_substitution(name: str) -> None:
    text = (Path(__file__).parent / f"{name}.template").read_text()
    print(name, end=":\n")
    lines = text.splitlines(keepends=True)
    for k, v in subsitutions.items():
        print("-", k, "->", v)
        lines = [s.replace(k, str(v)) for s in lines]
    text = "".join(lines)
    Path(name).write_text(text)


print("Creating config files X based on X.template files...")
apply_template_substitution("ls1config.xml")
apply_template_substitution("couette.xml")
print("\nDone!")
