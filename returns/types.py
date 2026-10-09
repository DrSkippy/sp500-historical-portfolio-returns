"""Typed records passed between the models, the runner and the analysis code.

All are NamedTuples, so they still unpack, compare equal to plain tuples, and
write directly with ``csv.writer``.
"""

import datetime
from typing import Any, NamedTuple

Row = list[Any]
"""A parsed data row: ``[date, values...]`` (combined rows append the interest values)."""


class PriceBar(NamedTuple):
    """Market inputs for one trading day."""

    price: float
    """Stock price."""
    interest_rate: float
    """Annual interest rate earned by cash (e.g. 0.03 for 3%)."""


class Trade(NamedTuple):
    """One executed trade (or insurance payout) and the portfolio state after it."""

    date: datetime.datetime
    bar: PriceBar
    delta_shares: float
    capital: float
    shares: float


class WindowReturn(NamedTuple):
    """Result of one backtest window. Field names are the returns CSV header."""

    date: datetime.datetime
    """Start date of the window."""
    frac_return: float
    yearly_return_rate: float
    time_span: float
    """Window length in years, measured between the first and last trades."""
    model_name: str


class ReturnStats(NamedTuple):
    """Aggregate statistics over all windows of one length for one model.

    Field names are the summary CSV columns.
    """

    sample_size: int
    time_span: float
    model_name: str
    mean_total_returns: float
    mean_yearly_compound_returns: float
    median_total_returns: float
    median_yearly_returns: float
    sdev_total_returns: float
    sdev_yearly_returns: float
    fraction_losing_starts: float
    mode_total_returns: float
    mode_yearly_returns: float


RETURNS_CSV_HEADER: list[str] = list(WindowReturn._fields)
SUMMARY_COLUMNS: list[str] = list(ReturnStats._fields)
