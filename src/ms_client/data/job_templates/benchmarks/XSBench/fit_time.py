#!/usr/bin/env -S uv run --script
#
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "numpy>=2.0.2",
# ]
# ///

"""Script to determine the expression for the requested time of the job spec."""

import argparse
import importlib
import multiprocessing
import os
import subprocess
import sys
import time
from pathlib import Path

XSBENCH_SOURCE_SCRIPT = "$HOME/spack-ecp-proxy-apps/env/xsbench.sh"


# Benchmark for one MPI rank only (XSBench runs the same on all ranks -> perfect weak scaling)
def run_xsbench(t: int, s: str, p: int, l: int) -> float:
    """Run XSBench on a single MPI rank.

    Parameters
    ----------
    t : int
        The number of threads
    s : str
        Benchmark size (small, large, XL, XXL)
    p : int
        Particle histories
    l : int
        Cross section lookups

    Returns
    -------
    float
        The runtime of the benchmark in seconds
    """
    cmd = " && ".join(
        [
            "MPI=$(which mpiexec)",  # Use system MPI
            f"source {XSBENCH_SOURCE_SCRIPT}",
            f"$MPI -n 1 --bind-to none -- XSBench -t {t} -s {s} -p {p} -l {l}",
        ]
    )
    start = time.perf_counter()
    result = subprocess.run(
        ["bash", "-c", cmd],
        capture_output=True,
        text=True,
        check=False,
    )
    if (
        result.returncode != os.EX_OK
        and "INAVALID CHECKSUM!"
        not in ("\n\n" + result.stdout.strip()).splitlines()[-2]
    ):
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError("XSBench exited unexpectedly.")
    elapsed = time.perf_counter() - start
    return elapsed


def measure(filename: str) -> None:
    """
    Run XSBench using multiple parameter sets and measure the runtimes.

    Parameters
    ----------
    filename : str
        The filename of the output CSV
    """
    t0 = multiprocessing.cpu_count() // 2 // 2  # No SMT
    ts = [t0 // 2]  # Only use half of all cores for fitting generously
    s = "large"
    p0 = 500_000
    ps = [p0 * (i + 1) for i in range(3)]
    l = 100
    print("Writing CSV data to", filename)
    Path(filename).write_text("t,p,elapsed\n")
    for t in ts:
        for p in ps:
            elapsed = run_xsbench(t=t, s=s, p=p, l=l)
            print(f"t={t}\ts={s}\tp={p}\tl={l}\telapsed={elapsed}")
            with open(filename, "a") as f:
                print(t, s, p, l, elapsed, sep=",", file=f)
    print("Done.")


def fit(filename: str) -> None:
    """
    Fit a linear model to predict the runtime of XSBench.

    Parameters
    ----------
    filename : str
        The CSV with the measured runtime for different parameter sets
    """
    np = importlib.import_module("numpy")
    data = np.genfromtxt(
        filename,
        delimiter=",",
        names=True,
    )
    p = data["p"]
    elapsed = data["elapsed"]
    p_m = p / 1_000_000  # Explicit scaling for model parameters
    a, b = np.polyfit(p_m, elapsed, 1)
    a = round(a, 3)
    b = round(b, 3)
    predicted = b + a * p / 1_000_000
    # R2 of the rounded model
    ss_res = np.sum((elapsed - predicted) ** 2)
    ss_tot = np.sum((elapsed - np.mean(elapsed)) ** 2)
    r2 = 1 - ss_res / ss_tot
    print("Fitted XSBench parameter model:")
    print(f"elapsed = {b:.3f}{a:+.3f}*(p/1_000_000)")
    print(f"R2 = {r2:.3f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=["measure", "fit"])
    parser.add_argument("filename", type=str)
    args = parser.parse_args()
    {
        "measure": measure,
        "fit": fit,
    }[args.step](args.filename)
