"""Aggregate statistics over backtest window returns (plots are in returns.plotting)."""

from typing import Any, Mapping, Sequence

import numpy as np
import numpy.typing as npt
import pandas as pd

from returns.errors import EmptyReturnsError
from returns.types import SUMMARY_COLUMNS, ReturnStats, WindowReturn


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
    returns_data: Sequence[WindowReturn], bins: int
) -> tuple[ReturnStats, list[float]]:
    """Summarize all backtest windows of one length for one model.

    Args:
        returns_data: Every window's result (from ``model_tester`` or
            ``returns.summaries.read_run_returns``).
        bins: Number of histogram bins used to estimate the modes
            (``backtest.histogram_bins``).

    Returns:
        The aggregate statistics and the list of total (fractional) returns.

    Raises:
        EmptyReturnsError: If ``returns_data`` is empty.
    """
    if not returns_data:
        raise EmptyReturnsError("No returns rows to aggregate")

    total_returns = np.array([float(r.frac_return) for r in returns_data])
    yearly_compounded_returns = np.array(
        [float(r.yearly_return_rate) for r in returns_data]
    )

    fraction_losing_starts = np.count_nonzero(total_returns < 0.0) / len(total_returns)

    stats = ReturnStats(
        sample_size=len(returns_data),
        time_span=round(float(returns_data[0].time_span), 0),
        model_name=str(returns_data[0].model_name),
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
    data: Mapping[Any, Sequence[WindowReturn]], bins: int
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
