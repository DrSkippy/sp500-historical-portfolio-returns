import datetime

import pytest

from returns.models import (
    format_insurance_name,
    format_kelly_name,
    parse_model_name,
)
from returns.types import PriceBar
from tests.conftest import make_buy_hold, make_insurance, make_kelly


def test_buy_hold_name() -> None:
    assert parse_model_name("Buy_Hold") == ("buy_hold", {})


@pytest.mark.parametrize("bond_frac,days", [(0.1, 90), (0.25, 180), (0.15, 90)])
def test_kelly_name_round_trips(bond_frac: float, days: int) -> None:
    model = make_kelly(bond_frac=bond_frac, rebalance_period=days)
    model.model_config(datetime.datetime(2020, 1, 1))
    assert model.model_name == format_kelly_name(bond_frac, days)
    assert parse_model_name(model.model_name) == (
        "kelly",
        {"bond_frac": bond_frac, "rebalance": days},
    )


@pytest.mark.parametrize("frac,deductible", [(0.05, 0.09), (0.1, 0.18)])
def test_insurance_name_round_trips(frac: float, deductible: float) -> None:
    model = make_insurance(insurance_frac=frac, insurance_deductible=deductible)
    model.model_config(datetime.datetime(2020, 1, 1))
    assert model.model_name == format_insurance_name(frac, deductible, 90)
    assert parse_model_name(model.model_name) == (
        "insurance",
        {"ins_frac": frac, "deductible": deductible, "rebalance": 90},
    )


def test_unknown_name() -> None:
    assert parse_model_name("Mystery_1") == ("unknown", {})


def test_model_name_does_not_accumulate_across_windows() -> None:
    model = make_kelly(bond_frac=0.2, rebalance_period=90)
    for day in range(1, 4):
        model.model_config(datetime.datetime(2020, 1, day))
    assert model.model_name == "Fractional_Kelly_0.2_90"


def test_unconfigured_model_reports_zero_returns() -> None:
    result = make_buy_hold().total_returns()
    assert (result.frac_return, result.model_name) == (0, "Buy_Hold")


def test_skip_padding_is_configurable() -> None:
    model = make_buy_hold(skip_padding=datetime.timedelta(days=1))
    model.model_config(datetime.datetime(2020, 1, 1), years=1)
    skip = model.daily_trade(datetime.datetime(2020, 2, 1), PriceBar(100, 0))
    assert skip == datetime.datetime(2020, 12, 30)


def test_loss_window_is_configurable() -> None:
    model = make_insurance(loss_window_days=2, insurance_deductible=0.1)
    model.model_config(datetime.datetime(2020, 1, 1), years=1)
    model.shares, model.capital = 90.0, 1000.0
    for day, price in enumerate([100.0, 100.0, 85.0], start=2):
        model.daily_trade(datetime.datetime(2020, 1, day), PriceBar(price, 0.0))
    assert any(t.delta_shares == 0 for t in model.trades)  # paid out on day 3
