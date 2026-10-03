"""Download QQQ daily price history from Yahoo Finance into data/QQQ.tab.

The output matches the SP500.tab layout (tab-separated, "Mon DD, YYYY" dates,
newest first) so it can be read by returns.data.get_sp500_data():

    Date  Open  High  Low  Close*  Adj Close**  Volume

Close* is split-adjusted only (price return); Adj Close** is split- and
dividend-adjusted (total return).

Usage:
    poetry run python bin/download_qqq.py [--symbol QQQ] [--out data/QQQ.tab]
"""

from __future__ import annotations

import argparse
import datetime
import logging
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
HEADER = ["Date", "Open", "High", "Low", "Close*", "Adj Close**", "Volume"]


def fetch_chart(symbol: str) -> dict[str, Any]:
    """Fetch the full daily chart history for a symbol from Yahoo Finance."""
    resp = requests.get(
        CHART_URL.format(symbol=symbol),
        params={
            "period1": 0,
            "period2": 9999999999,
            "interval": "1d",
            "events": "div,split",
        },
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
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
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--symbol", default="QQQ")
    parser.add_argument("--out", type=Path, default=Path("data/QQQ.tab"))
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    rows = chart_to_rows(fetch_chart(args.symbol))
    with args.out.open("w") as f:
        f.write("\t".join(HEADER) + "\n")
        for row in rows:
            f.write("\t".join(row) + "\n")
    logger.info(f"Wrote {len(rows)} rows ({rows[-1][0]} to {rows[0][0]}) to {args.out}")


if __name__ == "__main__":
    main()
