#! /usr/bin/env python3

import argparse
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# 1. Parse arguments
arg_parser = argparse.ArgumentParser()
arg_parser.add_argument("-w", "--width", type=float, required=True)
args = arg_parser.parse_args()

# 2. Validate arguments
if args.width < 1 or args.width > 10:
    print("Liquid film may only be between 1 and 10 nm thick.", file=sys.stderr)
    sys.exit(1)

# 3. Copy scenario files including template config template
scenario_path = Path("ExplodingLiquid")
if not scenario_path.is_dir():
    shutil.copytree(Path(__file__).parent / scenario_path.name, scenario_path)

y_lower = 290.946
y_upper = y_lower + args.width

substitutions = dict(
    Y_LOWER=y_lower,
    Y_UPPER=y_upper,
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
print("UNIX_STARTED", int(datetime.now(tz=timezone.utc).timestamp()))
print(f"Running exploding liquid simulation with film width of {args.width} nm:")
os.system(f"./MarDyn {config_path}")
print("UNIX_ENDED", int(datetime.now(tz=timezone.utc).timestamp()))
