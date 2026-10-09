"""InsuranceModel semantics: the policy insures the stock, not the cash reserve.

Decided 2026-10-07: payout = coverage_ratio x insured stock value x (|loss| - deductible),
premium = premium_rate x insured stock value per year (charged daily from cash),
at most one payout per policy period, renewed at the next scheduled rebalance.
"""

import datetime

import pytest

from returns.models import InsuranceModel
from returns.types import PriceBar
from tests.conftest import make_insurance

START = datetime.datetime(2020, 1, 1)
NO_INTEREST = 0.0


def day(n: int) -> datetime.datetime:
    return START + datetime.timedelta(days=n)


def make_model(**kwargs: float) -> InsuranceModel:
    """$12 cash reserve + 1 share of a $1000 asset, as in the worked scenario."""
    params: dict[str, float] = {
        "capital": 1012,
        "insurance_frac": 12 / 1012,
        "insurance_deductible": 0.18,
        "loss_window_days": 2,
    }
    params.update(kwargs)
    m = make_insurance(**params)
    m.model_config(START, years=2)
    m.first_trade(START, PriceBar(1000.0, NO_INTEREST))
    return m


def feed(m: InsuranceModel, start_day: int, prices: list[float]) -> None:
    for offset, price in enumerate(prices):
        m.daily_trade(day(start_day + offset), PriceBar(price, NO_INTEREST))


def payout_trades(m: InsuranceModel) -> list[int]:
    return [i for i, t in enumerate(m.trades) if i > 0 and t.delta_shares == 0]


def test_starting_position() -> None:
    m = make_model()
    assert m.shares == pytest.approx(1.0)
    assert m.capital == pytest.approx(12.0)


def test_premium_is_rate_on_insured_stock_value() -> None:
    m = make_model()
    feed(m, 30, [1000.0])
    # $1/month on $1000 at 1.2%/yr (30 days)
    assert m.capital == pytest.approx(12 - 0.012 * 1000 * 30 / 365)
    assert 12 - m.capital == pytest.approx(0.99, abs=0.01)


def test_crash_pays_the_insured_loss_beyond_the_deductible() -> None:
    # $1000 asset falls to $250 (75%): policy pays 1000 x (0.75 - 0.18) = $570
    m = make_model()
    feed(m, 1, [1000.0, 1000.0])
    cash_before = m.capital
    feed(m, 3, [250.0])
    premium_today = 0.012 * 250.0 * 1 / 365
    payout = m.trades[payout_trades(m)[0]]
    assert payout.capital == pytest.approx(cash_before - premium_today + 570.0)
    # after the same-day rebalance the portfolio is worth stock $250 + cash
    assert m.capital + m.shares * 250.0 == pytest.approx(payout.capital + 250.0)


def test_coverage_ratio_scales_the_payout() -> None:
    m = make_model(coverage_ratio=0.5)
    feed(m, 1, [1000.0, 1000.0])
    cash_before = m.capital
    feed(m, 3, [250.0])
    payout = m.trades[payout_trades(m)[0]]
    assert payout.capital == pytest.approx(
        cash_before - 0.012 * 250.0 / 365 + 0.5 * 570.0
    )


def test_payout_ignores_the_size_of_the_cash_reserve() -> None:
    # same insured stock, 10x the cash: the payout is identical
    small, large = make_model(), make_model(capital=1120, insurance_frac=120 / 1120)
    for m in (small, large):
        feed(m, 1, [1000.0, 1000.0])
    before = (small.capital, large.capital)
    for m in (small, large):
        feed(m, 3, [250.0])
    gains = [
        m.trades[payout_trades(m)[0]].capital - b
        for m, b in zip((small, large), before)
    ]
    assert gains[0] == pytest.approx(gains[1])


def test_no_payout_below_deductible() -> None:
    m = make_model()
    feed(m, 1, [1000.0, 1000.0, 830.0])  # 17% < 18%
    assert payout_trades(m) == []


def test_at_most_one_payout_per_period() -> None:
    m = make_model()
    feed(m, 1, [1000.0, 1000.0, 800.0])  # 20% drop: pays out on day 3
    feed(m, 4, [600.0, 400.0, 300.0])  # further crash inside the same period
    assert [m.trades[i].date for i in payout_trades(m)] == [day(3)]
    assert not m.policy_active


def test_policy_renews_at_next_scheduled_rebalance() -> None:
    m = make_model()
    feed(m, 1, [1000.0, 1000.0, 800.0])  # payout on day 3 restarts the schedule
    feed(m, 4, [800.0] * 89)  # quiet until day 92
    assert not m.policy_active
    feed(m, 93, [800.0])  # day 93 = payout day + 90: scheduled rebalance renews
    assert m.policy_active
    feed(m, 94, [600.0])  # 25% drop over the 2-day window
    assert [m.trades[i].date for i in payout_trades(m)] == [day(3), day(94)]


def test_new_window_resets_policy() -> None:
    m = make_model()
    feed(m, 1, [1000.0, 1000.0, 800.0])
    m.model_config(day(400), years=1)
    assert m.policy_active
