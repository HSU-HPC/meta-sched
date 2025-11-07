#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "numpy>=2.0.2",
#     "pandas>=2.3.2",
#     "plotly>=6.3.0",
#     "scipy>=1.13.1",
# ]
# ///

"""Script to determine the expression for the requested time of the job spec."""

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd
import plotly.graph_objects as go  # type: ignore
from scipy.optimize import curve_fit, minimize  # type: ignore

# region script parameters
SIMULATION_STEPS = 100_000  # Number of simulation steps in ls1 mardyn
MIN_FILM_WIDTH = 1  # [nm]
FILM_WIDTH_STEP = 1  # [nm]
SAFETY_FRACTION = 0.01  # e.g. 0.01 => 1% request longer wall time
ARRAY_SIZE = 10  # Should match spec.toml
# endregion script parameters

# region experiment data
# Experiment data from using WindHPC node running the
# ls1 exploding liquid simulation for 1000 steps with MPI.
# (NOTE: On less powerful systems this may take longer.)
benchmark_path = Path(__file__).parent / "benchmarks_time.csv"
if not benchmark_path.is_file():
    print(f'File not found: {benchmark_path}\n(Run "{Path(__file__).parent/"create_benchmarks_time.py"} first!)', file=sys.stderr)
    sys.exit(1)
df = pd.read_csv(benchmark_path)
assert len(df["steps"].unique()) == 1, "Some experiments ran for different lenghts."
experiment_steps = df["steps"].values[0]
df = df.groupby(["cores", "film_width"], as_index=False)["seconds"].mean()
df.sort_values(["film_width", "cores"], inplace=True)  # ignore: type[reportCallIssue]
print("Benchmarks Mean:")
film_widths = df["film_width"].unique()  # ignore: type[reportAttributeAccessIssue]
data = dict(
    film_width=film_widths,
)
for cores in df["cores"].unique()[::-1]:  # ignore: type[reportAttributeAccessIssue]
    mask_cores = df["cores"] == cores
    column_seconds = []
    for film_width in film_widths:
        seconds = df[mask_cores & (df["film_width"] == film_width)][
            "seconds"
        ].values  # ignore: type[reportAttributeAccessIssue]
        column_seconds.append(seconds[0] if len(seconds) == 1 else np.nan)
    data[f"{cores} cores"] = column_seconds
print(pd.DataFrame(data).to_string(index=False), end="\n\n")
# endregion experiment data


# region fitting/optimization
surface_expr = "a + b * x**c * y**(-d)"
print("Fitting:", surface_expr)


@contextmanager
def suppress_stderr() -> Iterator[None]:
    """Context manager to temporarily hide output to sys.stderr."""
    with open(os.devnull, "w") as fnull:
        old_stderr = sys.stderr
        sys.stderr = fnull
        try:
            yield
        finally:
            sys.stderr = old_stderr


def surface(xy, a, b, c, d):  # type: ignore[no-untyped-def]
    """Function for a surface polynomial: f(x,y)=eval(surface_expr).

    Parameters
    ----------
    xy
        The function inputs
    a, b, c, d
        The function coefficients

    Returns
    -------
    The value of the function evaluation
    """
    x, y = xy
    with suppress_stderr():
        return eval(surface_expr)


def optmization_objective(params, xy, z):  # type: ignore[no-untyped-def]
    """Optimization objective function: sum of squared residuals."""
    pred = surface(xy, *params)  # type: ignore[no-untyped-call]
    return np.sum((z - pred) ** 2)


def make_constraint(xi, yi, zi):  # type: ignore[no-untyped-def]
    """Create an optimization constraint: surface >= experiments."""

    def constraint(params):  # type: ignore[no-untyped-def]
        """Optimization constraint."""
        return surface((np.array([xi]), np.array([yi])), *params)[0] - zi  # type: ignore[no-untyped-call]

    return constraint


X = df["film_width"]
Y = df["cores"]
Z_sample = df["seconds"]
# Initial guess for parameters
init_params = curve_fit(surface, (X, Y), Z_sample)[0]
constraints = [
    {"type": "ineq", "fun": make_constraint(xi, yi, zi)}  # type: ignore[no-untyped-call]
    for xi, yi, zi in zip(X, Y, Z_sample)
]
result = minimize(
    optmization_objective, init_params, args=((X, Y), Z_sample), constraints=constraints
)
if not result.success:
    print(f"Optimization failed: {result.message}")
else:
    print(result.message)
surface_coefficients = result.x
# endregion fitting/optimization

# region create expression
expression_x = f"({MIN_FILM_WIDTH}+i*{FILM_WIDTH_STEP})"
scale_up_factor = SIMULATION_STEPS / experiment_steps
# Remove trailing ".0"
scale_up_factor = (
    int(scale_up_factor) if int(scale_up_factor) == scale_up_factor else scale_up_factor
)
expression_z = f"{1 + SAFETY_FRACTION}*{scale_up_factor}*({surface_expr})"
expression_z = expression_z.replace("x", expression_x)
expression_z = expression_z.replace("y", "p")
print("Coefficients")
for i, val in enumerate(surface_coefficients):
    var = chr(ord("a") + i)
    val_fmtd = f"{val:.2f}"
    print(f" - {var} = {val_fmtd}")
    expression_z = expression_z.replace(var, val_fmtd)
expression_z = expression_z.replace(" ", "")
expression_z = expression_z.replace("+-", "-")


def eval_expression_z(xy):  # type: ignore[no-untyped-def]
    """Function to evaluate the wall time expression.

    Parameters
    ----------
    xy
        The thickness of the liquid film (x) and number of cores (y)

    Returns
    -------
    The value of the expression evaluation
    """
    x, y = xy
    substitution = dict(
        i=(x - MIN_FILM_WIDTH) / FILM_WIDTH_STEP,
        p=y,
    )
    return eval(expression_z, None, substitution)


x_range = np.linspace(np.min(X), np.max(X), 10)
y_range = np.linspace(np.min(Y), np.max(Y), 10)
X_surface, Y_surface = np.meshgrid(x_range, y_range)
Z_fit = surface((X_surface, Y_surface), *surface_coefficients)  # type: ignore[no-untyped-call]
Z_expr = eval_expression_z((X_surface, Y_surface)) / scale_up_factor  # type: ignore[no-untyped-call]
assert (Z_fit <= Z_expr).all(), "Expression must not lie below the fitted surface!"
Z_sample = df["seconds"]
residuals = Z_sample - (eval_expression_z((X, Y)) / scale_up_factor)  # type: ignore[no-untyped-call]
root_mean_square_error = (np.sum(residuals) ** 2 / len(Z_sample)) ** 0.5
print(
    f"RMSE: {int(np.ceil(root_mean_square_error))} sec ({root_mean_square_error / 60:.2f} min)"
)
n_cores = 48
t_min = int(np.ceil(eval_expression_z((x_range[0], n_cores))))  # type: ignore[no-untyped-call]
t_max = int(np.ceil(eval_expression_z((x_range[-1], n_cores))))  # type: ignore[no-untyped-call]
print(
    f"Estimated wall time range with {n_cores} cores for {x_range[0]} - {x_range[-1]} nm and {SIMULATION_STEPS} steps:",
    f"{t_min} sec ({t_min / 3600:.2f} h) - {t_max} sec ({t_max / 3600:.2f} h)",
)
print("\nAdd this to your spec.toml:\n")
print(f"# Expression generated using {Path(__file__).name}")
print(f'time = "={expression_z}"\n')
# endregion create expression

# region visualization
fig = go.Figure()
above = Z_sample > surface((X, Y), *surface_coefficients)  # type: ignore[no-untyped-call]
below = ~above
for mask, label, color in [
    (above, "Experiments (underestimated)", "red"),
    (below, "Experiments (not underestimated)", "black"),
]:
    fig.add_trace(
        go.Scatter3d(
            x=X[mask],
            y=Y[mask],
            z=Z_sample[mask],
            mode="markers",
            marker=dict(size=3, color=color, opacity=1),
            name=label,
            showlegend=True,
        )
    )
fig.add_trace(
    go.Surface(
        x=X_surface,
        y=Y_surface,
        z=Z_fit,
        colorscale="Blues",
        opacity=1,
        name="Fit",
        showlegend=True,
        showscale=False,
    )
)
fig.add_trace(
    go.Surface(
        x=X_surface,
        y=Y_surface,
        z=Z_expr,
        colorscale="Greens",
        opacity=1,
        name="Expression",
        showlegend=True,
        showscale=False,
    )
)
fig.update_layout(
    title="Experimental Time Required by Simulation",
    scene=dict(
        xaxis_title="Film Width [nm]",
        yaxis_title="Cores",
        zaxis_title="Time/1000 Steps [sec]",
    ),
)
fig.show()
# endregion visualization
