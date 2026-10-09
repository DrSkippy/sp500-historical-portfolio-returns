import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from returns.config import AppConfig

spec = importlib.util.spec_from_file_location(
    "download_qqq", Path(__file__).parent.parent / "bin" / "download_qqq.py"
)
assert spec is not None and spec.loader is not None
download_qqq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(download_qqq)


def make_chart(timestamps: list[int], closes: list[float | None]) -> dict[str, Any]:
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


def test_chart_to_rows_newest_first_and_formatted() -> None:
    # 1999-03-10 14:30 UTC and 1999-03-11 14:30 UTC (market open, US Eastern)
    rows = download_qqq.chart_to_rows(
        make_chart([921076200, 921162600], [51.0625, 51.3125])
    )
    assert [r[0] for r in rows] == ["Mar 11, 1999", "Mar 10, 1999"]
    assert rows[0][4:] == ["51.3125", "46.1812", "100"]


def test_chart_to_rows_skips_incomplete_days() -> None:
    rows = download_qqq.chart_to_rows(
        make_chart([921076200, 921162600], [51.0625, None])
    )
    assert len(rows) == 1


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, Any]:
        return self.payload


def test_main_uses_yahoo_config_and_dataset_defaults(
    synthetic_config: AppConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_get(url: str, **kwargs: Any) -> FakeResponse:
        calls.append({"url": url, **kwargs})
        chart = make_chart([921076200, 921162600], [51.0625, 51.3125])
        return FakeResponse({"chart": {"result": [chart]}})

    monkeypatch.setattr(download_qqq.requests, "get", fake_get)
    monkeypatch.setattr(download_qqq, "load_config", lambda: synthetic_config)
    monkeypatch.setattr(sys, "argv", ["download_qqq", "--dataset", "synthetic"])
    download_qqq.main()

    yahoo = synthetic_config.sources.yahoo
    assert calls[0]["url"] == "https://example.invalid/chart/SYN"
    assert calls[0]["params"]["period2"] == yahoo.period_end
    assert calls[0]["headers"] == {"User-Agent": yahoo.user_agent}
    assert calls[0]["timeout"] == yahoo.timeout_seconds
    lines = synthetic_config.datasets["synthetic"].price_path.read_text().splitlines()
    assert lines[0] == "\t".join(download_qqq.HEADER)
    assert [line.split("\t")[0] for line in lines[1:]] == [
        "Mar 11, 1999",
        "Mar 10, 1999",
    ]
