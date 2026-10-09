"""
generate_recent_returns.py

Reads a dataset's historical prices (default: S&P 500, SP500.tab) and its recent
quotes (SPY from PostgreSQL, or the tail of the price file), computes daily/weekly/monthly
return distributions, and writes trading_strategies_report/data/<recent_data>.json.

Usage:
    poetry run python bin/generate_recent_returns.py [--dataset qqq]
"""

import argparse
import datetime
import logging
from typing import Any, Sequence

import numpy as np

from returns.cli import add_dataset_argument
from returns.config import AppConfig, RecentPeriodConfig, load_config
from returns.db import get_db_settings, get_quotes
from returns.errors import EmptyHistoryError
from returns.finance import simple_return
from returns.io_utils import write_compact_json
from returns.logging_setup import configure_logging
from returns.naming import ISO_DATE_FORMAT
from returns.prices import Dataset, get_price_data, load_dataset
from returns.types import Row

logger = logging.getLogger(__name__)

DatedPrice = tuple[Any, float]
PERCENTILES = (10, 25, 75, 90)


def format_date(value: Any) -> str:
    """Format a date/datetime as YYYY-MM-DD; other values with str()."""
    return value.strftime(ISO_DATE_FORMAT) if hasattr(value, "strftime") else str(value)


def compute_returns(prices: Sequence[float], window: int) -> list[float]:
    """Compute rolling return: (close[i] - close[i-window]) / close[i-window]."""
    return [
        simple_return(prices[i - window], prices[i]) for i in range(window, len(prices))
    ]


def compute_stats(values: Sequence[float]) -> dict[str, float]:
    """Compute mean, median, population std, and the p10/p25/p75/p90 percentiles.

    Percentiles interpolate linearly between ranks. Empty input gives ``{}``.
    """
    if not values:
        return {}
    array = np.asarray(values, dtype=float)
    stats = {
        "mean": float(np.mean(array)),
        "median": float(np.median(array)),
        "std": float(np.std(array)),
    }
    for p, value in zip(PERCENTILES, np.percentile(array, PERCENTILES)):
        stats[f"p{p}"] = float(value)
    return stats


def percentile_rank(hist_values: Sequence[float], recent_value: float) -> float:
    """Fraction of historical values strictly less than recent_value, * 100.

    Raises:
        EmptyHistoryError: If there are no historical values to rank against.
    """
    if not hist_values:
        raise EmptyHistoryError("No historical returns to rank a recent return in")
    count = sum(1 for v in hist_values if v < recent_value)
    return count / len(hist_values) * 100.0


def build_recent_entries(
    dated_prices: Sequence[DatedPrice],
    window: int,
    n_recent: int,
    hist_values: Sequence[float],
) -> list[dict[str, Any]]:
    """
    Compute non-overlapping recent returns from the tail of dated_prices.

    Args:
        dated_prices: list of (date, price), sorted ascending
        window: lookback in trading days
        n_recent: number of non-overlapping periods to return
        hist_values: historical distribution for percentile ranking

    Returns:
        ``{"date", "value", "percentile"}`` dicts, oldest first.
    """
    if len(dated_prices) < window + 1:
        return []

    # Take non-overlapping periods from the end: every `window`-th point
    prices = [p for _, p in dated_prices]
    dates = [d for d, _ in dated_prices]

    # Build indices: start from the last valid point, step back by window
    indices: list[int] = []
    i = len(prices) - 1
    while i >= window and len(indices) < n_recent:
        indices.append(i)
        i -= window
    indices.reverse()

    entries = []
    for idx in indices:
        ret = simple_return(prices[idx - window], prices[idx])
        entries.append(
            {
                "date": format_date(dates[idx]),
                "value": ret,
                "percentile": percentile_rank(hist_values, ret),
            }
        )
    return entries


def load_recent_quotes(
    dataset: Dataset, history: list[Row], config: AppConfig
) -> list[DatedPrice]:
    """Recent (date, close) quotes from PostgreSQL or the price history itself."""
    symbol = dataset.config.recent_symbol
    if dataset.config.recent_source == "db":
        db = get_db_settings()
        logger.info(
            "Connecting to PostgreSQL at %s:%s/%s...",
            db["host"],
            db["port"],
            db["dbname"],
        )
        return list(get_quotes(symbol, config.sources.db_namespace))
    return [(row[0].date(), row[dataset.price_index]) for row in history]


def build_period_section(
    period: RecentPeriodConfig,
    hist_prices: Sequence[float],
    recent_quotes: Sequence[DatedPrice],
) -> dict[str, Any]:
    """Historical distribution, its stats, and recent entries for one horizon."""
    values = compute_returns(hist_prices, period.window)
    return {
        "values": values,
        "stats": compute_stats(values),
        "recent": build_recent_entries(
            recent_quotes, period.window, period.recent, values
        ),
    }


def build_output(dataset: Dataset, config: AppConfig) -> dict[str, Any]:
    """Assemble the full recent-returns JSON structure for a dataset."""
    # ── 1. Historical data ──────────────────────────────────────────────────
    logger.info("Loading %s...", dataset.config.price_path)
    history, _ = get_price_data(dataset.config.price_path)
    hist_prices = [row[dataset.price_index] for row in history]
    logger.info("  %s historical prices loaded", len(hist_prices))

    # ── 2. Recent quotes ────────────────────────────────────────────────────
    recent_quotes = load_recent_quotes(dataset, history, config)
    latest = recent_quotes[-1] if recent_quotes else None
    logger.info(
        "  %s %s rows loaded (latest: %s)",
        len(recent_quotes),
        dataset.config.recent_symbol,
        latest[0] if latest else "none",
    )

    # ── 3. Assemble output ──────────────────────────────────────────────────
    output: dict[str, Any] = {
        "generated_at": datetime.date.today().isoformat(),
        "label": dataset.config.label,
        "symbol": dataset.config.recent_symbol,
        "history_start": history[0][0].year,
        "latest_spy_date": format_date(latest[0]) if latest and latest[0] else "",
        "latest_spy_close": latest[1] if latest else None,
    }
    for period in config.recent_returns.periods:
        output[period.name] = build_period_section(period, hist_prices, recent_quotes)
    return output


def main() -> None:
    """Build and write the recent-returns JSON for one dataset."""
    parser = argparse.ArgumentParser(
        description="Build recent returns data for the report site."
    )
    add_dataset_argument(parser)
    args = parser.parse_args()
    configure_logging("INFO", ["console"])
    config = load_config()
    dataset = load_dataset(args.dataset, config)

    output = build_output(dataset, config)

    output_dir = config.report.output_dir
    output_path = output_dir / dataset.config.recent_data
    output_dir.mkdir(parents=True, exist_ok=True)
    write_compact_json(output_path, output)
    logger.info("Written: %s", output_path)
    for period in config.recent_returns.periods:
        section = output[period.name]
        logger.info(
            "  %s values: %s, recent: %s",
            period.name,
            len(section["values"]),
            len(section["recent"]),
        )


if __name__ == "__main__":
    main()
