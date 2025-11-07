#! /usr/bin/env python3

"""Script for generating ls1 configuration and running simulation."""

import argparse
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# 1. Parse arguments
arg_parser = argparse.ArgumentParser()
arg_parser.add_argument(
    "-s",
    "--steps",
    type=int,
    default=100000,
    required=False,
    help="Number of simulation steps.",
)
arg_parser.add_argument(
    "-w", "--width", type=float, required=True, help="Liquid film width in nm."
)
arg_parser.add_argument(
    "-d",
    "--dry-run",
    action="store_true",
    help="Do not execute simulation command. (Only print it and generate config.)",
)
args = arg_parser.parse_args()

if "MS_INPUT" not in os.environ:
    print(
        "Environment variable MS_INPUT (pointing to folder containing MarDyn executable) was not set.",
        file=sys.stderr,
    )
    sys.exit(1)
input_path = Path(os.environ["MS_INPUT"])
mardyn_path = Path("MarDyn").absolute()

try:
    assert mardyn_path.exists()
except Exception:
    print(
        f"MarDyn executable not found at {mardyn_path}",
        file=sys.stderr,
    )
    sys.exit(1)

# 2. Validate arguments
if args.steps <= 0:
    print("Number of simulation steps must be positive.", file=sys.stderr)
if args.width < 0.1 or args.width > 100:
    print("Liquid film may only be between 0.1 and 100 nm thick.", file=sys.stderr)
    sys.exit(1)

# 3. Copy scenario files including template config template
scenario_path = Path(input_path) / "ExplodingLiquid"
if not scenario_path.is_dir():
    shutil.copytree(Path(__file__).parent / scenario_path.name, scenario_path)

# Center liquid film along y
# (Width in nm/10)
y_lower = 290.946 - 10 * (args.width / 2)
y_upper = y_lower + 10 * args.width

substitutions = dict(
    Y_LOWER=y_lower,
    Y_UPPER=y_upper,
    STEPS=args.steps,
)

# 4. Apply substitution for config template file
config_template_path = scenario_path / "config.xml.template"
config_path = scenario_path / config_template_path.stem

with open(config_path, "w") as file:
    for line in config_template_path.read_text().splitlines(keepends=True):
        for k, v in substitutions.items():
            line = line.replace(k, str(v))
        file.write(line)

# 5. Run ls1 mardyn simulation
sys.stdout.flush()
cmd: str
if os.system("command -v mpiexec >/dev/null 2>&1") == 0:
    # Disable OMP parallelism
    cmd = f"OMP_NUM_THREADS=1 mpiexec {mardyn_path} {config_path}"
else:
    cmd = f"{mardyn_path} {config_path}"
status = 0
if args.dry_run:
    print(cmd)
else:
    print("UNIX_STARTED", int(datetime.now(tz=timezone.utc).timestamp()))
    print(f"Running exploding liquid simulation with film width of {args.width} nm:")
    status = os.system(cmd)
    print("UNIX_ENDED", int(datetime.now(tz=timezone.utc).timestamp()))
sys.exit(status)
