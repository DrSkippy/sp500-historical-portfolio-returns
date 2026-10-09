"""Matplotlib plots of backtest summaries and return distributions (notebooks / scripts).

Kept apart from the statistics so backtest worker processes never import pyplot.
"""

from typing import Any

import pandas as pd
from matplotlib import pyplot as plt

from returns.monthly_returns import MonthlyReturns

FIGURE_WIDTH_INCHES = 8
PANEL_HEIGHT_INCHES = 4
"""Each stacked panel's height."""
SUMMARY_STAT_COLUMNS_START = 3
"""First summary column worth plotting (after sample_size, time_span, model_name)."""
MONTHLY_FIGSIZE = (10, 5)


def plot_df(
    df: pd.DataFrame,
    columns: list[str] | None = None,
    df2: pd.DataFrame | None = None,
) -> None:
    """Plot summary columns against window length, optionally overlaying ``df2``."""
    if columns is None:
        columns = df.columns.to_list()[SUMMARY_STAT_COLUMNS_START:]
    fig, axs = plt.subplots(nrows=len(columns), ncols=1)
    fig.set_size_inches(FIGURE_WIDTH_INCHES, PANEL_HEIGHT_INCHES * len(columns))
    for ax, column in zip(axs.reshape(-1), columns):
        df.plot(x="time_span", y=column, ax=ax)
        if df2 is not None:
            df2.plot(x="time_span", y=column, ax=ax)
        ax.set_ylabel(column.replace("_", " ").capitalize())
        ax.set_xlabel("Period (Years)")


def plot_histograms(total_returns_by_period: dict[Any, list[float]], bins: int) -> None:
    """Plot one histogram of total returns per window length."""
    fig, axs = plt.subplots(nrows=len(total_returns_by_period), ncols=1)
    fig.set_size_inches(
        FIGURE_WIDTH_INCHES, PANEL_HEIGHT_INCHES * len(total_returns_by_period)
    )
    for ax, (period, values) in zip(axs.reshape(-1), total_returns_by_period.items()):
        ax.hist(values, bins=bins)
        ax.set_title(f"Sample Returns {period}")


def plot_period_comparison_data(model_comparison: pd.DataFrame) -> None:
    """Scatter key statistics by model for one window length."""
    for column in [
        "mean_total_returns",
        "mean_yearly_compound_returns",
        "median_total_returns",
        "median_yearly_returns",
        "fraction_losing_starts",
    ]:
        model_comparison.plot.scatter(column, "model_name")


def plot_monthly_returns(monthly: MonthlyReturns, bins: int) -> None:
    """Show a histogram of the monthly returns.

    Args:
        monthly: Rolling returns to plot.
        bins: Number of histogram bins (``monthly_returns.histogram_bins``).
    """
    plt.figure(figsize=MONTHLY_FIGSIZE)
    plt.hist(
        monthly.returns.to_numpy(), bins=bins, label="Monthly Returns", color="blue"
    )
    plt.title("Monthly Returns Distribution")
    plt.xlabel("Returns")
    plt.ylabel("Frequency")
    plt.legend()
    plt.grid()
    plt.show()
