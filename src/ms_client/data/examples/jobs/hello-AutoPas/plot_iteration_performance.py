#! /usr/bin/env python3

"""Plot iteration performance of AutoPas (CSV)."""

import sys
from pathlib import Path
from typing import Union

import matplotlib.pyplot as plt  # type:ignore[import-not-found]
import pandas as pd
from matplotlib.lines import Line2D  # type:ignore[import-not-found]


def plot_tuning_phases(
    csv_path: Union[str, Path],
    x_col: str = "ThreadCount",
    y_col: str = "energyJoules[J]",
    num_plots: int = 4,
) -> None:
    """
    Plot tuning phases.

    Parameters
    ----------
    csv_path : str | Path
        Path to the CSV file to plot
    x_col : str
        Column name for the x-axis data
    y_col : str
        Column name for the y-axis data
    num_plots : int
        Number of subplots
    """

    df = pd.read_csv(csv_path)
    df["inTuningPhase"] = df["inTuningPhase"].astype(bool)

    df["phase"] = (
        df["inTuningPhase"] & ~df["inTuningPhase"].shift(fill_value=False)
    ).cumsum()

    tuning_df = df[df["inTuningPhase"]].copy()

    config_cols = list(
        df.columns[df.columns.get_loc("Container") : df.columns.get_loc("ThreadCount")]
    )

    tuning_df["cluster"] = tuning_df[config_cols].astype(str).agg("|".join, axis=1)

    phases = tuning_df["phase"].unique()[:num_plots]

    _, axes = plt.subplots(len(phases), 1, figsize=(7, 4 * len(phases)), sharex=True)

    if len(phases) == 1:
        axes = [axes]

    cmap = plt.cm.tab20

    for i, (ax, phase_id) in enumerate(zip(axes, phases)):
        phase = tuning_df[tuning_df["phase"] == phase_id]

        clusters = phase["cluster"].unique()
        cluster_index = {c: idx for idx, c in enumerate(clusters)}

        means_config = phase.groupby(["cluster", x_col])[y_col].mean().reset_index()

        for cluster in clusters:
            ci = cluster_index[cluster]
            color = cmap(ci % 20)

            cluster_df = phase[phase["cluster"] == cluster]

            # jitter so configurations don't overlap
            jitter = (ci - len(clusters) / 2) * 0.15
            x_vals = cluster_df[x_col] + jitter

            ax.scatter(
                x_vals,
                cluster_df[y_col],
                edgecolors=color,
                facecolors="none",
                s=35,
                alpha=0.7,
            )

            means = means_config[means_config["cluster"] == cluster]

            ax.scatter(means[x_col] + jitter, means[y_col], color=color, s=35)

        best_idx = means_config[y_col].idxmin()
        best_row = means_config.loc[best_idx]

        best_cluster = best_row["cluster"]
        ci = cluster_index[best_cluster]
        jitter = (ci - len(clusters) / 2) * 0.15

        ax.scatter(
            best_row[x_col] + jitter,
            best_row[y_col],
            color="black",
            marker="*",
            s=80,
            zorder=5,
        )

        best_sample = phase.loc[phase[y_col].idxmin()]
        ci = cluster_index[best_sample["cluster"]]
        jitter = (ci - len(clusters) / 2) * 0.15

        ax.scatter(
            best_sample[x_col] + jitter,
            best_sample[y_col],
            edgecolors="black",
            facecolors="none",
            marker="*",
            s=80,
            zorder=5,
        )

        ax.set_title(f"Tuning phase {i + 1}")
        ax.set_ylabel(y_col)
        ax.grid(True)

    axes[-1].set_xlabel(x_col)

    legend_elements = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="black",
            markerfacecolor="none",
            markersize=8,
            linestyle="None",
            label="sample (outlined)",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="black",
            markerfacecolor="black",
            markersize=8,
            linestyle="None",
            label="mean (filled)",
        ),
        Line2D(
            [0],
            [0],
            marker="*",
            color="black",
            markersize=12,
            linestyle="None",
            label="best mean",
        ),
        Line2D(
            [0],
            [0],
            marker="*",
            color="black",
            markerfacecolor="none",
            markersize=12,
            linestyle="None",
            label="best sample",
        ),
        Line2D([0], [0], linestyle="None", label="colors = configurations"),
    ]

    axes[0].legend(handles=legend_elements, loc="upper right")

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    try:
        plot_tuning_phases(sys.argv[1])
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        print(f"Usage: {sys.argv[0]} path/to/iterationPerformance.csv", file=sys.stderr)
        sys.exit(1)
