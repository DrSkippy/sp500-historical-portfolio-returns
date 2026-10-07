"""InsuranceModel payout, premium and policy-period semantics (decided 2026-10-07)."""

import datetime

import pytest

from returns.models import InsuranceModel
from returns.types import PriceBar

START = datetime.datetime(2020, 1, 1)


def day(n: int) -> datetime.datetime:
    return START + datetime.timedelta(days=n)


@pytest.fixture
def model() -> InsuranceModel:
    m = InsuranceModel(
        insurance_frac=0.1,
        insurance_deductible=0.15,
        insurance_period=90,
        loss_window_days=2,
    )
    m.model_config(START, years=2)
    m.shares, m.capital = 90.0, 1000.0
    return m


def feed(m: InsuranceModel, start_day: int, prices: list[float]) -> None:
    for offset, price in enumerate(prices):
        m.daily_trade(day(start_day + offset), PriceBar(price, 0.05))


def payouts(m: InsuranceModel) -> list[datetime.datetime]:
    return [t.date for t in m.trades if t.delta_shares == 0]


def test_premium_is_a_cost(model: InsuranceModel) -> None:
    feed(model, 90, [100.0])  # scheduled rebalance after a full period
    cash_after_premium = 1000 * (1 - 0.005) ** (90 / 365)
    total = cash_after_premium + 90 * 100
    assert model.capital == pytest.approx(0.1 * total)
    assert cash_after_premium < 1000


def test_payout_adds_to_cash_even_below_one_over_factor() -> None:
    # deductible x factor < 1: the old "replace cash" rule made this payout a net loss
    m = InsuranceModel(insurance_deductible=0.09, loss_window_days=1)
    m.model_config(START, years=1)
    m.shares, m.capital = 90.0, 1000.0
    m.last_rebalance = day(1)
    feed(m, 1, [100.0, 90.5])
    payout_trade = m.trades[0]
    assert payout_trade.capital > 1000
    cash = 1000 * (1 - 0.005) ** (1 / 365)  # one day of premium first
    assert payout_trade.capital == pytest.approx(cash * (1 + 0.095 * 10))


def test_at_most_one_payout_per_period(model: InsuranceModel) -> None:
    feed(model, 1, [100.0, 100.0, 80.0])  # 20% drop: pays out on day 3
    feed(model, 4, [80.0, 60.0, 50.0, 40.0])  # further crash inside the same period
    assert payouts(model) == [day(3)]
    assert not model.policy_active


def test_policy_renews_at_next_scheduled_rebalance(model: InsuranceModel) -> None:
    feed(model, 1, [100.0, 100.0, 80.0])  # payout on day 3 restarts the schedule
    feed(model, 4, [80.0] * 89)  # quiet until day 92
    assert not model.policy_active
    feed(model, 93, [80.0])  # day 93 = payout day + 90: scheduled rebalance renews
    assert model.policy_active
    feed(model, 94, [60.0])  # 25% drop over the 2-day window
    assert payouts(model) == [day(3), day(94)]


def test_new_window_resets_policy(model: InsuranceModel) -> None:
    feed(model, 1, [100.0, 100.0, 80.0])
    model.model_config(day(400), years=1)
    assert model.policy_active
