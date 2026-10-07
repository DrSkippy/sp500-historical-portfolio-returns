from typing import Any

import pytest

from returns.monthly_returns import OFFSET, MonthlyReturns


def _make_monthly_returns(
    n: int = 60, prices: list[float] | None = None
) -> MonthlyReturns:
    """Build a MonthlyReturns from synthetic price data."""
    if prices is None:
        prices = [float(i + 1) for i in range(n)]
    header = ["Date", "Open", "High", "Low", "Close", "Adj Close**", "Volume"]
    rows = [[None, None, None, None, None, p, None] for p in prices]
    return MonthlyReturns(rows, header)


class TestMonthlyReturns:
    def test_length(self) -> None:
        n = 60
        mr = _make_monthly_returns(n)
        assert len(mr.returns) == n - OFFSET

    def test_return_values(self) -> None:
        n = 60
        prices = [float(i + 1) for i in range(n)]
        mr = _make_monthly_returns(n, prices)
        # Formula: (current - prior) / current  where prior = price[index - OFFSET]
        expected = (prices[OFFSET] - prices[0]) / prices[OFFSET]
        assert abs(mr.returns.iloc[0] - expected) < 1e-10

    def test_sample_is_numeric(self) -> None:
        mr = _make_monthly_returns()
        s = mr.sample()
        assert isinstance(s, float)


def test_custom_price_column_and_offset() -> None:
    header = ["Date", "Close*"]
    rows = [[None, float(p)] for p in [100, 50, 100, 200]]
    mr = MonthlyReturns(rows, header, price_column="Close*", offset=1)
    assert mr.returns.tolist() == pytest.approx([-1.0, 0.5, 0.5])


def test_sample_with_seeded_generator_is_reproducible() -> None:
    import numpy as np

    mr = _make_monthly_returns(60)
    a = mr.sample(np.random.default_rng(1))
    b = mr.sample(np.random.default_rng(1))
    assert a == b and a in mr.returns.tolist()
    assert mr.sample() in mr.returns.tolist()


def test_summary_text() -> None:
    text = _make_monthly_returns(60).summary()
    assert text.splitlines()[0] == "Monthly Returns Summary:"
    assert "Total Samples: 30" in text


def test_write_and_plot(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import matplotlib
    from matplotlib import pyplot as plt

    matplotlib.use("Agg")
    monkeypatch.setattr(plt, "show", lambda: None)
    mr = _make_monthly_returns(60)
    mr.write_to_csv(str(tmp_path / "m.csv"))
    assert len((tmp_path / "m.csv").read_text().splitlines()) == 31
    mr.plot_returns()
