"""Aggregate statistics and plots over backtest window returns."""

from typing import Any, Mapping, Sequence

import numpy as np
import numpy.typing as npt
import pandas as pd
from matplotlib import pyplot as plt

from returns.errors import EmptyReturnsError
from returns.types import SUMMARY_COLUMNS, ReturnStats

HISTOGRAM_BINS = 45

FRAC_RETURN_COLUMN = 1
YEARLY_RETURN_COLUMN = 2
TIME_SPAN_COLUMN = 3
MODEL_NAME_COLUMN = 4


def calculate_mode(hist_data: tuple[npt.NDArray[Any], npt.NDArray[Any]]) -> float:
    """Calculate the mode of a histogram as the centre of its highest-count bin.

    Args:
        hist_data: ``(counts, bin_edges)`` as returned by ``np.histogram``; bin
            ``i`` spans ``bin_edges[i]`` to ``bin_edges[i + 1]``.

    Returns:
        The midpoint of the peak bin (the first one, if several tie).
    """
    counts, edges = hist_data
    peak = int(np.argmax(counts))
    return float((edges[peak] + edges[peak + 1]) / 2)


def aggregate_returns(
    returns_data: Sequence[Sequence[Any]], bins: int = HISTOGRAM_BINS
) -> tuple[ReturnStats, list[float]]:
    """Summarize all backtest windows of one length for one model.

    Args:
        returns_data: Rows of ``[date, frac_return, yearly_return_rate, time_span,
            model_name]``; numeric fields may be strings (as read from CSV).
        bins: Number of histogram bins used to estimate the modes.

    Returns:
        The aggregate statistics and the list of total (fractional) returns.

    Raises:
        EmptyReturnsError: If ``returns_data`` is empty.
    """
    if not returns_data:
        raise EmptyReturnsError("No returns rows to aggregate")

    total_returns = np.array([float(r[FRAC_RETURN_COLUMN]) for r in returns_data])
    yearly_compounded_returns = np.array(
        [float(r[YEARLY_RETURN_COLUMN]) for r in returns_data]
    )

    fraction_losing_starts = np.count_nonzero(total_returns < 0.0) / len(total_returns)

    stats = ReturnStats(
        sample_size=len(returns_data),
        time_span=round(float(returns_data[0][TIME_SPAN_COLUMN]), 0),
        model_name=str(returns_data[0][MODEL_NAME_COLUMN]),
        mean_total_returns=float(np.mean(total_returns)),
        mean_yearly_compound_returns=float(np.mean(yearly_compounded_returns)),
        median_total_returns=float(np.median(total_returns)),
        median_yearly_returns=float(np.median(yearly_compounded_returns)),
        sdev_total_returns=float(np.std(total_returns)),
        sdev_yearly_returns=float(np.std(yearly_compounded_returns)),
        fraction_losing_starts=fraction_losing_starts,
        mode_total_returns=calculate_mode(np.histogram(total_returns, bins=bins)),
        mode_yearly_returns=calculate_mode(
            np.histogram(yearly_compounded_returns, bins=bins)
        ),
    )
    return stats, total_returns.tolist()


def format_metrics(return_stats: ReturnStats) -> str:
    """Render aggregate statistics as a multi-line report.

    Args:
        return_stats: Output of ``aggregate_returns``.

    Returns:
        The report text.
    """
    s = return_stats
    return "\n".join(
        [
            f"### AGGREGATE RETURNS ### {s.model_name} ###",
            f"Sample Size              = {s.sample_size}",
            f"Time span                = {s.time_span:5.1f} years",
            f"Mean Returns             = {s.mean_total_returns:5.2%}",
            f"Avg Yearly Return        = {s.mean_yearly_compound_returns:5.2%}",
            f"Median Returns           = {s.median_total_returns:5.2%}",
            f"Median Yearly Returns    = {s.median_yearly_returns:5.2%}",
            f"StdDev of Returns        = {s.sdev_total_returns:5.2%}",
            f"StdDev of Yearly Returns = {s.sdev_yearly_returns:5.2%}",
            f"Losing start days        = {s.fraction_losing_starts:5.2%}",
            f"Mode of Returns          = {s.mode_total_returns:5.2%}",
            f"Mode of Yearly Returns   = {s.mode_yearly_returns:5.2%}",
        ]
    )


def get_aggregate_returns_by_period(
    data: Mapping[Any, Sequence[Sequence[Any]]], bins: int = HISTOGRAM_BINS
) -> tuple[list[ReturnStats], dict[Any, list[float]]]:
    """Aggregate each window length's returns.

    Args:
        data: Returns rows keyed by window length in years.
        bins: Histogram bins for the mode estimates.

    Returns:
        One ``ReturnStats`` per key, and the total returns keyed the same way.
    """
    returns_stats_by_period = []
    total_returns_by_period = {}
    for period, rows in data.items():
        summary_vector, total_returns = aggregate_returns(rows, bins)
        total_returns_by_period[period] = total_returns
        returns_stats_by_period.append(summary_vector)
    return returns_stats_by_period, total_returns_by_period


def get_df_aggregate_returns_by_period(
    returns_stats_by_period: list[ReturnStats],
) -> pd.DataFrame:
    """Build the summary table, one row per window length, sorted by length."""
    df = pd.DataFrame(returns_stats_by_period, columns=SUMMARY_COLUMNS)
    return df.sort_values(by=["time_span"])


def plot_df(
    df: pd.DataFrame,
    columns: list[str] | None = None,
    df2: pd.DataFrame | None = None,
) -> None:
    """Plot summary columns against window length, optionally overlaying ``df2``."""
    if columns is None:
        columns = df.columns.to_list()[3:]
    fig, axs = plt.subplots(nrows=len(columns), ncols=1)
    fig.set_size_inches(8, 4 * len(columns))
    for ax, column in zip(axs.reshape(-1), columns):
        df.plot(x="time_span", y=column, ax=ax)
        if df2 is not None:
            df2.plot(x="time_span", y=column, ax=ax)
        ax.set_ylabel(column.replace("_", " ").capitalize())
        ax.set_xlabel("Period (Years)")


def plot_histograms(
    total_returns_by_period: dict[Any, list[float]], bins: int = HISTOGRAM_BINS
) -> None:
    """Plot one histogram of total returns per window length."""
    fig, axs = plt.subplots(nrows=len(total_returns_by_period), ncols=1)
    fig.set_size_inches(8, 4 * len(total_returns_by_period))
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
