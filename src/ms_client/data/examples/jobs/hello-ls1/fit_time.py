#! /usr/bin/env python3

"""Script to determine the expression for the requested time of the job spec."""

from io import StringIO
from pathlib import Path

import matplotlib.pyplot as plt  # type: ignore
import numpy as np
import pandas as pd

SIMULATION_STEPS = 100_000  # Number of simulation steps in ls1 mardyn
MIN_FILM_WIDTH = 10  # [nm]
FILM_WIDTH_STEP = 10  # [nm]
SAFETY_FRACTION = 0.1  # e.g. 0.1 => 10% request longer wall time
ARRAY_SIZE = 10  # Should match spec.toml

# Benchmark results on 1 node with 96 OMP threads (WindHPC).
# Exploding liquid simulation was run for 1000 steps.
# NOTE: On less powerful systems this may take longer.
experiments_csv = """
molecules film_width seconds
15616     1          32.7841
155864    10         44.5774
311664    20         58.2996
623832    40         80.7172
1246616   80         123.379
2492536   160        204.409
4687568   320        369.824
"""
experiment_steps = 1000

df = pd.read_csv(StringIO(experiments_csv), delim_whitespace=True, comment="#")
X = df["film_width"]

print(df)
exit()

m, b = np.polyfit(X, df["seconds"], 1)
expression_x = f"{MIN_FILM_WIDTH}+i*{FILM_WIDTH_STEP}"
scale_up_factor = SIMULATION_STEPS / experiment_steps
expression_y = f"{1 + SAFETY_FRACTION}*{scale_up_factor}*({m}*({expression_x})+{b})"

plt.plot(X, df["seconds"], label="Experiments")
plt.plot(X, X.apply(lambda x: m * x + b), label=f"Fit: ${m}\\times$width$+{b}$")
X = [eval(expression_x, None, dict(i=i)) for i in range(ARRAY_SIZE)]
y_fit = np.array([eval(expression_y, None, dict(i=i)) for i in range(ARRAY_SIZE)])
plt.plot(X, y_fit / scale_up_factor, label=f"Expression / {scale_up_factor}")
plt.xlabel("Film Width [nm]")
plt.ylabel("Time/1000 steps [sec]")
plt.title("Experimental Time Required by Simulation")
plt.legend()
plt.tight_layout()

t_min = int(np.ceil(np.min(y_fit)))
t_max = int(np.ceil(np.max(y_fit)))
print(
    f"Wall time range: {t_min} sec ({t_min / 3600:.2f} h) - {t_max} sec ({t_max / 3600:.2f} h)"
)
print("\nAdd this to your spec.toml:\n")
print(f"# Expression generated using {Path(__file__).name}")
print(f'time = "={expression_y}"')

plt.show()
