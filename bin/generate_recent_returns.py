"""
generate_recent_returns.py

Reads a dataset's historical prices (default: S&P 500, SP500.tab) and its recent
quotes (SPY from PostgreSQL, or the tail of the price file), computes daily/weekly/monthly
return distributions, and writes trading_strategies_report/data/<recent_data>.json.

Usage:
    poetry run python bin/generate_recent_returns.py [--dataset qqq]
"""

import argparse
import json
import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import returns.data
from returns.data import get_sp500_data, use_dataset
from returns.db import get_db_settings, get_quotes

OUTPUT_DIR = "trading_strategies_report/data"


def compute_returns(prices, window):
    """Compute rolling return: (close[i] - close[i-window]) / close[i-window]."""
    return [
        (prices[i] - prices[i - window]) / prices[i - window]
        for i in range(window, len(prices))
    ]


def compute_stats(values):
    """Compute mean, median, std, p10, p25, p75, p90."""
    if not values:
        return {}
    n = len(values)
    sorted_vals = sorted(values)
    mean = sum(values) / n
    median = (
        sorted_vals[n // 2]
        if n % 2
        else (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
    )
    variance = sum((v - mean) ** 2 for v in values) / n
    std = variance**0.5

    def percentile(p):
        idx = p / 100.0 * (n - 1)
        lo, hi = int(idx), min(int(idx) + 1, n - 1)
        return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (idx - lo)

    return {
        "mean": mean,
        "median": median,
        "std": std,
        "p10": percentile(10),
        "p25": percentile(25),
        "p75": percentile(75),
        "p90": percentile(90),
    }


def percentile_rank(hist_values, recent_value):
    """Fraction of historical values strictly less than recent_value, * 100."""
    count = sum(1 for v in hist_values if v < recent_value)
    return count / len(hist_values) * 100.0


def build_recent_entries(dated_prices, window, n_recent, hist_values):
    """
    Compute non-overlapping recent returns from the tail of dated_prices.
    dated_prices: list of (date, price), sorted ascending
    window: lookback in trading days
    n_recent: number of non-overlapping periods to return
    hist_values: historical distribution for percentile ranking
    """
    if len(dated_prices) < window + 1:
        return []

    # Take non-overlapping periods from the end: every `window`-th point
    entries = []
    prices = [p for _, p in dated_prices]
    dates = [d for d, _ in dated_prices]
    n = len(prices)

    # Build indices: start from the last valid point, step back by window
    indices = []
    i = n - 1
    while i >= window and len(indices) < n_recent:
        indices.append(i)
        i -= window
    indices.reverse()

    for idx in indices:
        ret = (prices[idx] - prices[idx - window]) / prices[idx - window]
        d = dates[idx]
        date_str = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)
        entries.append(
            {
                "date": date_str,
                "value": ret,
                "percentile": percentile_rank(hist_values, ret),
            }
        )
    return entries


def main():
    parser = argparse.ArgumentParser(
        description="Build recent returns data for the report site."
    )
    parser.add_argument(
        "--dataset", default="sp500", help="dataset key from config.yaml (sp500, qqq)"
    )
    args = parser.parse_args()
    cfg = use_dataset(args.dataset)
    symbol = cfg["recent_symbol"]
    output_path = os.path.join(OUTPUT_DIR, cfg["recent_data"])

    # ── 1. Historical data ──────────────────────────────────────────────────
    print(f"Loading {returns.data.sp500_input_path}...")
    sp500_data, _ = get_sp500_data()
    # price column from config (0=date, 1=open, 2=high, 3=low, 4=close, 5=adj_close, 6=volume)
    hist_prices = [row[returns.data.sp500_index] for row in sp500_data]
    print(f"  {len(hist_prices)} historical prices loaded")

    hist_daily = compute_returns(hist_prices, 1)
    hist_weekly = compute_returns(hist_prices, 5)
    hist_monthly = compute_returns(hist_prices, 21)
    print(
        f"  Historical: {len(hist_daily)} daily, {len(hist_weekly)} weekly, {len(hist_monthly)} monthly"
    )

    # ── 2. Recent quotes ────────────────────────────────────────────────────
    if cfg["recent_source"] == "db":
        db = get_db_settings()
        print(
            f"Connecting to PostgreSQL at {db['host']}:{db['port']}/{db['dbname']}..."
        )
        spy_rows = get_quotes(symbol)
    else:
        spy_rows = [
            (row[0].date(), row[returns.data.sp500_index]) for row in sp500_data
        ]
    print(
        f"  {len(spy_rows)} {symbol} rows loaded (latest: {spy_rows[-1][0] if spy_rows else 'none'})"
    )

    latest_date = spy_rows[-1][0] if spy_rows else None
    latest_close = spy_rows[-1][1] if spy_rows else None
    latest_date_str = (
        (
            latest_date.strftime("%Y-%m-%d")
            if hasattr(latest_date, "strftime")
            else str(latest_date)
        )
        if latest_date
        else ""
    )

    # ── 3. Recent returns ───────────────────────────────────────────────────
    recent_daily = build_recent_entries(spy_rows, 1, 30, hist_daily)
    recent_weekly = build_recent_entries(spy_rows, 5, 10, hist_weekly)
    recent_monthly = build_recent_entries(spy_rows, 21, 4, hist_monthly)

    # ── 4. Assemble output ──────────────────────────────────────────────────
    output = {
        "generated_at": date.today().isoformat(),
        "label": cfg["label"],
        "symbol": symbol,
        "history_start": sp500_data[0][0].year,
        "latest_spy_date": latest_date_str,
        "latest_spy_close": latest_close,
        "daily": {
            "values": hist_daily,
            "stats": compute_stats(hist_daily),
            "recent": recent_daily,
        },
        "weekly": {
            "values": hist_weekly,
            "stats": compute_stats(hist_weekly),
            "recent": recent_weekly,
        },
        "monthly": {
            "values": hist_monthly,
            "stats": compute_stats(hist_monthly),
            "recent": recent_monthly,
        },
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, separators=(",", ":"))
    print(f"Written: {output_path}")
    print(
        f"  daily values: {len(output['daily']['values'])}, recent: {len(output['daily']['recent'])}"
    )
    print(
        f"  weekly values: {len(output['weekly']['values'])}, recent: {len(output['weekly']['recent'])}"
    )
    print(
        f"  monthly values: {len(output['monthly']['values'])}, recent: {len(output['monthly']['recent'])}"
    )


if __name__ == "__main__":
    main()
