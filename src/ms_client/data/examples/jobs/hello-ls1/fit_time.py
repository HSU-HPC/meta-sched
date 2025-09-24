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

from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go  # type: ignore
from scipy.optimize import curve_fit, minimize  # type: ignore

# region script parameters
SIMULATION_STEPS = 100_000  # Number of simulation steps in ls1 mardyn
MIN_FILM_WIDTH = 10  # [nm]
FILM_WIDTH_STEP = 10  # [nm]
SAFETY_FRACTION = 0.1  # e.g. 0.1 => 10% request longer wall time
ARRAY_SIZE = 10  # Should match spec.toml
# endregion script parameters

# region experiment data
# Experiment data from using WindHPC node running the
# ls1 exploding liquid simulation for 1000 steps with OMP.
# (NOTE: On less powerful systems this may take longer.)
experiments_csv = """
molecules film_width seconds cores
# All physical cores
155864    10         48.2166 48
311664    20         57.8555 48
623832    40         79.5075 48
1246616   80         124.213 48
2492536   160        207.794 48
4687568   320        353.156 48
# Half of all physical cores (one socket)
155864    10         66.2023 24
311664    20         82.1669 24
623832    40         114.267 24
1246616   80         173.255 24
2492536   160        308.564 24
4687568   320        536.159 24
# Quarter of all physical cores
155864    10         104.093 12
311664    20         132.059 12
623832    40         185.308 12
1246616   80         293.452 12
2492536   160        500.408 12
4687568   320        887.295 12
"""
experiment_steps = 1000
df = pd.read_csv(StringIO(experiments_csv), sep="\s+", comment="#")
# endregion experiment data


# region fitting/optimization
def surface(xy, a, b, c, d, e):  # type: ignore[no-untyped-def]
    """Function for a surface polynomial: f(x,y)=a+bx+cy+dxy^(1/e).

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
    return a + b * x + c * y ** (1 / e) + d * x * y ** (1 / e)


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
a, b, c, d, e = surface_coefficients
expression_x = f"{MIN_FILM_WIDTH}+i*{FILM_WIDTH_STEP}"
scale_up_factor = SIMULATION_STEPS / experiment_steps
expression_z = f"{1 + SAFETY_FRACTION}*{scale_up_factor}*({a:.2f}+{b:.2f}*({expression_x})+{c:.2f}*p**(1/{e:.2f})+{d:.2f}*({expression_x})*p**(1/{e:.2f}))"
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
residuals = Z_sample - (eval_expression_z((X, Y)) / scale_up_factor)
root_mean_square_error = (np.sum(residuals) ** 2 / len(Z_sample)) ** 0.5
print(
    f"RMSE: {int(np.ceil(root_mean_square_error))} sec ({root_mean_square_error / 60:.2f} min)"
)
n_cores = 48
t_min = int(np.ceil(eval_expression_z((np.min(X_surface), n_cores))))  # type: ignore[no-untyped-call]
t_max = int(np.ceil(eval_expression_z((np.max(X_surface), n_cores))))  # type: ignore[no-untyped-call]
print(
    f"Estimated wall time range with {n_cores} cores: {t_min} sec ({t_min / 3600:.2f} h) - {t_max} sec ({t_max / 3600:.2f} h)"
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
