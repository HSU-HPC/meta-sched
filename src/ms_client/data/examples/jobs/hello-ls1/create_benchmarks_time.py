#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "pandas>=2.3.2",
# ]
# ///

"""Script to generate benchmark_time.csv on a Slurm cluster."""

import math
import multiprocessing
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import ContextManager

import pandas as pd

max_nodes = 2
min_nodes = 0.25
min_film_width = 0.8  # [nm]
n_film_widths = 5
n_samples = 5
pool_size = 20
base_path = Path(__file__).parent.absolute()
benchmarks_path = (base_path / "benchmarks_time.csv").absolute()
n_steps = 1000


def get_slots_per_node() -> int:
    """Determine the number of MPI slots on the current host."""
    cmd = "ml mpi &>/dev/null; mpiexec hostname | wc -l"
    stdout = subprocess.check_output(["sh", "-c", cmd])
    return int(stdout.decode())


def run_benchmark(
    cores: int, film_width: float, sample: int, lock: ContextManager[None]
) -> None:
    """Run the scenario (run_scenario.py) and append the results to the benchmark file."""
    seconds = float("nan")
    global benchmarks_path
    try:
        benchmarks_path = benchmarks_path.absolute()
        benchmarks_files_path = (
            benchmarks_path.parent
            / benchmarks_path.with_suffix(".tmp")
            / f"{cores}cores-{film_width}nm-{sample}"
        )
        if benchmarks_files_path.is_dir():
            print(
                "Benchmark folder already exists:",
                benchmarks_files_path,
                file=sys.stderr,
            )
            return
        benchmarks_files_path.mkdir(parents=True)
        os.chdir(benchmarks_files_path)
        input_path = (benchmarks_path.parent / "input").absolute()
        for filename in ["MarDyn"]:
            shutil.copy2(
                input_path / filename,
                benchmarks_files_path / filename,
                follow_symlinks=True,
            )
        cmd = " ".join(
            map(
                str,
                [
                    f"MS_INPUT={benchmarks_files_path}",
                    input_path / "run_scenario.py",
                    "--steps",
                    n_steps,
                    "--width",
                    film_width,
                    "--dry-run",
                ],
            )
        )
        cmd = subprocess.check_output(["sh", "-c", cmd]).decode()
        # Run using Slurm instead of directly using mpiexec
        nodes = math.ceil(cores / get_slots_per_node())
        cmd = cmd.replace(
            "mpiexec", f"srun -n{cores} --ntasks-per-core=1 -N{nodes}"
        ).strip()
        output_path = benchmarks_files_path / "output"
        cmd += f" &> {output_path}"
        status = os.system(cmd)
        assert status == os.EX_OK, "Simulation did not exit successfully"
        for line in output_path.read_text().splitlines():
            if "Time per iteration:" in line:
                seconds_per_step = float(line.split()[-2])
                seconds = n_steps * seconds_per_step
                break
    except Exception as e:
        # Avoid subprocess failing silently
        print(e)
        raise

    with lock, open(benchmarks_path, "a") as file:
        file.write(
            ",".join(map(str, [cores, film_width, n_steps, sample, seconds]))
        )
        file.write("\n")
        file.flush()
    print(
        f"Finished benchmark sample #{sample} for",
        film_width,
        "nm film on",
        cores,
        "cores in ",
        seconds,
        "seconds.",
    )


def sort_output_rows() -> None:
    """Re-order the rows in the benchmark file."""
    if not benchmarks_path.exists():
        return
    df = pd.read_csv(benchmarks_path)
    df.sort_values(["cores", "film_width", "sample"], inplace=True)
    df.to_csv(benchmarks_path, index=False)


def main() -> None:
    """Run the remaining benchmark runs using Slurm."""
    if os.system("command -v mpiexec >/dev/null 2>&1") != 0:
        print('Command "mpiexec" was not found. (Was MPI loaded?)')
        sys.exit(1)
    os.chdir(base_path / "input")
    os.system("./build_ls1.sh")
    os.chdir(base_path)
    cores_per_node = get_slots_per_node()
    max_cores = max_nodes * cores_per_node
    min_cores = int(min_nodes * cores_per_node)
    df = None
    if not benchmarks_path.exists():
        benchmarks_path.write_text(
            ",".join(["cores", "film_width", "steps", "sample", "seconds"]) + "\n"
        )
    df = pd.read_csv(benchmarks_path)
    cores = max_cores * 2
    benchmark_parameters = []
    while cores > min_cores:
        cores //= 2
        film_width = min_film_width / 2
        for i in range(n_film_widths):
            film_width *= 2
            existing_samples = (
                (df["cores"] == cores) & (df["film_width"] == film_width)
            ).sum()
            for j in range(existing_samples, n_samples):
                benchmark_parameters.append((cores, film_width, j + 1))
    with multiprocessing.Pool(pool_size) as pool:
        manager = multiprocessing.Manager()
        lock = manager.Lock()
        for p in benchmark_parameters:
            pool.apply_async(run_benchmark, [*p, lock])
        pool.close()
        pool.join()
    sort_output_rows()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
