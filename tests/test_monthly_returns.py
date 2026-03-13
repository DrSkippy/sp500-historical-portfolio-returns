import pytest

from returns.monthly_returns import OFFSET, MonthlyReturns


def _make_monthly_returns(n: int = 60, prices: list | None = None) -> MonthlyReturns:
    """Build a MonthlyReturns from synthetic price data."""
    if prices is None:
        prices = [float(i + 1) for i in range(n)]
    header = ["Date", "Open", "High", "Low", "Close", "Adj Close**", "Volume"]
    rows = [[None, None, None, None, None, p, None] for p in prices]
    return MonthlyReturns(rows, header)


class TestMonthlyReturns:
    def test_length(self):
        n = 60
        mr = _make_monthly_returns(n)
        assert len(mr.returns) == n - OFFSET

    def test_return_values(self):
        n = 60
        prices = [float(i + 1) for i in range(n)]
        mr = _make_monthly_returns(n, prices)
        # Formula: (current - prior) / current  where prior = price[index - OFFSET]
        expected = (prices[OFFSET] - prices[0]) / prices[OFFSET]
        assert abs(mr.returns.iloc[0] - expected) < 1e-10

    def test_sample_is_numeric(self):
        mr = _make_monthly_returns()
        s = mr.sample()
        assert isinstance(s, float)
