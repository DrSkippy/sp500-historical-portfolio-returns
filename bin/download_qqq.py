"""Download a dataset's daily price history from Yahoo Finance into its price file.

By default fetches the ``qqq`` dataset's ``recent_symbol`` into its ``price_path``
(data/QQQ.tab); the Yahoo endpoint and request settings are ``sources.yahoo`` in
config.yaml. The output matches the SP500.tab layout (tab-separated, "Mon DD, YYYY"
dates, newest first) so it can be read by returns.data.get_price_data():

    Date  Open  High  Low  Close*  Adj Close**  Volume

Close* is split-adjusted only (price return); Adj Close** is split- and
dividend-adjusted (total return).

Usage:
    poetry run python bin/download_qqq.py [--dataset qqq] [--symbol QQQ] [--out data/QQQ.tab]
"""

from __future__ import annotations

import argparse
import datetime
import logging
from pathlib import Path
from typing import Any

import requests

from returns.config import YahooConfig, load_config

logger = logging.getLogger(__name__)

HEADER = ["Date", "Open", "High", "Low", "Close*", "Adj Close**", "Volume"]


def fetch_chart(symbol: str, yahoo: YahooConfig) -> dict[str, Any]:
    """Fetch the full daily chart history for a symbol from Yahoo Finance.

    Args:
        symbol: Ticker symbol, e.g. "QQQ".
        yahoo: Endpoint and request settings (``sources.yahoo``).

    Returns:
        The chart ``result`` object.
    """
    params: dict[str, str | int] = {
        "period1": 0,
        "period2": yahoo.period_end,
        "interval": "1d",
        "events": "div,split",
    }
    resp = requests.get(
        yahoo.chart_url.format(symbol=symbol),
        params=params,
        headers={"User-Agent": yahoo.user_agent},
        timeout=yahoo.timeout_seconds,
    )
    resp.raise_for_status()
    result: dict[str, Any] = resp.json()["chart"]["result"][0]
    return result


def chart_to_rows(chart: dict[str, Any]) -> list[list[str]]:
    """Convert a Yahoo chart result into SP500.tab-style rows, newest first."""
    quote = chart["indicators"]["quote"][0]
    adjclose = chart["indicators"]["adjclose"][0]["adjclose"]
    rows = []
    for i, ts in enumerate(chart["timestamp"]):
        values = [
            quote["open"][i],
            quote["high"][i],
            quote["low"][i],
            quote["close"][i],
            adjclose[i],
        ]
        if any(v is None for v in values):
            continue  # skip incomplete days (e.g. partial current session)
        date = datetime.datetime.fromtimestamp(
            ts + chart["meta"]["gmtoffset"], tz=datetime.timezone.utc
        )
        rows.append(
            [date.strftime("%b %d, %Y")]
            + [f"{v:.4f}" for v in values]
            + [str(int(quote["volume"][i] or 0))]
        )
    rows.reverse()
    return rows


def main() -> None:
    """Download the history and write it in SP500.tab layout."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dataset", default="qqq", help="dataset key from config.yaml to refresh"
    )
    parser.add_argument("--symbol", help="ticker (default: dataset recent_symbol)")
    parser.add_argument("--out", type=Path, help="output (default: dataset price_path)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    config = load_config()
    dataset = config.dataset(args.dataset)
    symbol: str = args.symbol or dataset.recent_symbol
    out: Path = args.out or dataset.price_path
    rows = chart_to_rows(fetch_chart(symbol, config.sources.yahoo))
    with out.open("w") as f:
        f.write("\t".join(HEADER) + "\n")
        for row in rows:
            f.write("\t".join(row) + "\n")
    logger.info(f"Wrote {len(rows)} rows ({rows[-1][0]} to {rows[0][0]}) to {out}")


if __name__ == "__main__":
    main()
