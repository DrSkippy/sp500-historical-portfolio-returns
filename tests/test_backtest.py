import bisect
import datetime
import math
import pickle
from typing import Any, Callable

import pytest

from returns.backtest import (
    BuyHoldSpec,
    InsuranceSpec,
    KellySpec,
    all_model_specs,
    build_model,
    model_tester,
    unique_model_names,
)
from returns.config import AppConfig
from returns.errors import DuplicateModelNameError
from returns.models import PortfolioModel
from returns.types import PriceBar
from tests.conftest import make_buy_hold, make_insurance, make_kelly

PRICE_IDX = 5
INTEREST_IDX = 7
STRIDE_DAYS = 3


@pytest.fixture
def data() -> list[list[Any]]:
    """~3 years of daily rows shaped like combined data: [date, ..., price @5, ..., interest @7]."""
    start = datetime.datetime(2000, 1, 3)
    rows = []
    for i in range(3 * 365):
        # trend plus a ~10% swing every ~60 days so Insurance payouts and rebalances happen
        price = 100 * (1.0003**i) * (1 + 0.1 * math.sin(i / 10))
        rows.append([start + datetime.timedelta(days=i), 0, 0, 0, 0, price, 0, 0.03])
    return rows


def reference_tester(
    model: PortfolioModel, data: list[list[Any]], years: int
) -> list[Any]:
    """Original model_tester loop: scans to the end of the data for every window (no early exit)."""
    test_start_date = data[0][0]
    dates = [d[0] for d in data]
    out: list[Any] = []
    while test_start_date + datetime.timedelta(days=365 * years) < data[-1][0]:
        model.model_config(test_start_date, years=years)
        start_idx = bisect.bisect_left(dates, test_start_date - model.skip_padding)
        skip_to_date = None
        for d in data[start_idx:]:
            if skip_to_date is not None and d[0] < skip_to_date:
                continue
            skip_to_date = model.trade(d[0], PriceBar(d[PRICE_IDX], d[INTEREST_IDX]))
        out.append(model.total_returns())
        test_start_date += datetime.timedelta(days=STRIDE_DAYS)
    return out


@pytest.mark.parametrize(
    "make_model",
    [
        lambda: make_buy_hold(),
        lambda: make_kelly(bond_frac=0.2, rebalance_days=90),
        lambda: make_insurance(insurance_frac=0.1, insurance_deductible=0.09),
    ],
)
def test_early_exit_matches_full_scan(
    data: list[list[Any]], make_model: Callable[[], PortfolioModel]
) -> None:
    got = model_tester(
        make_model(), data, PRICE_IDX, INTEREST_IDX, years=1, stride_days=STRIDE_DAYS
    )
    want = reference_tester(make_model(), data, years=1)
    assert len(got) > 100
    assert got == want


def test_stops_trading_after_window_end(
    data: list[list[Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    model = make_kelly(bond_frac=0.2, rebalance_days=90)
    calls_after_end: list[datetime.datetime] = []
    orig_trade = model.trade

    def counting_trade(
        date: datetime.datetime, price: PriceBar
    ) -> datetime.datetime | None:
        if date >= model.end_date:
            calls_after_end.append(date)
        return orig_trade(date, price)

    monkeypatch.setattr(model, "trade", counting_trade)
    rets = model_tester(
        model, data, PRICE_IDX, INTEREST_IDX, years=1, stride_days=STRIDE_DAYS
    )
    # exactly one post-window call per window: the one that makes the last trade
    assert len(calls_after_end) == len(rets)


def test_all_model_specs_matches_original_grid(synthetic_config: AppConfig) -> None:
    specs = all_model_specs(synthetic_config)
    assert len(specs) == 15
    assert [type(s) for s in specs] == [BuyHoldSpec] + [KellySpec] * 8 + [
        InsuranceSpec
    ] * 6
    assert specs[1] == KellySpec(bond_frac=0.1, rebalance_days=90)
    last = specs[-1]
    assert isinstance(last, InsuranceSpec)
    assert (last.insurance_frac, last.deductible) == (0.1, 0.18)
    assert last.policy.premium_rate == 0.012
    assert last.policy.loss_window_days == 6
    for spec in specs:
        model = build_model(spec, synthetic_config.backtest)
        assert model.init_capital == 10000
        assert model.skip_padding == datetime.timedelta(days=6)


def test_specs_pickle_for_the_process_pool(synthetic_config: AppConfig) -> None:
    specs = all_model_specs(synthetic_config)
    assert pickle.loads(pickle.dumps(specs)) == specs


def test_unique_model_names_accepts_the_grid(synthetic_config: AppConfig) -> None:
    names = unique_model_names(
        all_model_specs(synthetic_config), synthetic_config.backtest
    )
    assert len(names) == len(set(names)) == 15
    assert names[0] == "Buy_Hold" and names[-1] == "Insurance_0.1_0.18_90"


def test_unique_model_names_rejects_repeated_grid_values(
    synthetic_config: AppConfig,
) -> None:
    kelly = synthetic_config.models.kelly.model_copy(
        update={"bond_fracs": [0.2, 0.2], "rebalance_days": [90]}
    )
    config = synthetic_config.model_copy(
        update={"models": synthetic_config.models.model_copy(update={"kelly": kelly})}
    )
    with pytest.raises(DuplicateModelNameError, match="Fractional_Kelly_0.2_90"):
        unique_model_names(all_model_specs(config), config.backtest)
