import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "download_qqq", Path(__file__).parent.parent / "bin" / "download_qqq.py"
)
download_qqq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(download_qqq)


def make_chart(timestamps, closes):
    n = len(timestamps)
    return {
        "meta": {"gmtoffset": -18000},
        "timestamp": timestamps,
        "indicators": {
            "quote": [
                {
                    "open": [1.0] * n,
                    "high": [2.0] * n,
                    "low": [0.5] * n,
                    "close": closes,
                    "volume": [100] * n,
                }
            ],
            "adjclose": [
                {"adjclose": [c * 0.9 if c is not None else None for c in closes]}
            ],
        },
    }


def test_chart_to_rows_newest_first_and_formatted():
    # 1999-03-10 14:30 UTC and 1999-03-11 14:30 UTC (market open, US Eastern)
    rows = download_qqq.chart_to_rows(
        make_chart([921076200, 921162600], [51.0625, 51.3125])
    )
    assert [r[0] for r in rows] == ["Mar 11, 1999", "Mar 10, 1999"]
    assert rows[0][4:] == ["51.3125", "46.1812", "100"]


def test_chart_to_rows_skips_incomplete_days():
    rows = download_qqq.chart_to_rows(
        make_chart([921076200, 921162600], [51.0625, None])
    )
    assert len(rows) == 1
