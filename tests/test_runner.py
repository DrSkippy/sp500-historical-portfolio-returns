import bisect
import datetime
import importlib.util
import math
from pathlib import Path

import pytest

from returns.models import InsuranceModel, KellyModel, Model

spec = importlib.util.spec_from_file_location(
    "runner", Path(__file__).parent.parent / "bin" / "runner.py"
)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

PRICE_IDX = 5
INTEREST_IDX = 7


@pytest.fixture
def data():
    """~3 years of daily rows shaped like combined data: [date, ..., price @5, ..., interest @7]."""
    start = datetime.datetime(2000, 1, 3)
    rows = []
    for i in range(3 * 365):
        # trend plus a ~10% swing every ~60 days so Insurance payouts and rebalances happen
        price = 100 * (1.0003**i) * (1 + 0.1 * math.sin(i / 10))
        rows.append([start + datetime.timedelta(days=i), 0, 0, 0, 0, price, 0, 0.03])
    return rows


def reference_tester(model, data, years):
    """Original model_tester loop: scans to the end of the data for every window (no early exit)."""
    test_start_date = data[0][0]
    dates = [d[0] for d in data]
    out = []
    while test_start_date + datetime.timedelta(days=365 * years) < data[-1][0]:
        model.model_config(test_start_date, years=years)
        start_idx = bisect.bisect_left(
            dates, test_start_date - runner.PADDING_TIME_DELTA
        )
        skip_to_date = None
        for d in data[start_idx:]:
            if skip_to_date is not None and d[0] < skip_to_date:
                continue
            skip_to_date = model.trade(d[0], (d[PRICE_IDX], d[INTEREST_IDX]))
        out.append(model.total_returns())
        test_start_date += datetime.timedelta(days=runner.STRIDE_DAYS)
    return out


@pytest.mark.parametrize(
    "make_model",
    [
        lambda: Model(),
        lambda: KellyModel(bond_fract=0.2, rebalance_period=90),
        lambda: InsuranceModel(insurance_frac=0.1, insurance_deductible=0.09),
    ],
)
def test_early_exit_matches_full_scan(data, make_model):
    got = runner.model_tester(make_model(), data, years=1, price_index=PRICE_IDX)
    want = reference_tester(make_model(), data, years=1)
    assert len(got) > 100
    assert got == want


def test_stops_trading_after_window_end(data):
    model = KellyModel(bond_fract=0.2, rebalance_period=90)
    calls_after_end = []
    orig_trade = model.trade

    def counting_trade(date, price):
        if date >= model.end_date:
            calls_after_end.append(date)
        return orig_trade(date, price)

    model.trade = counting_trade
    rets = runner.model_tester(model, data, years=1, price_index=PRICE_IDX)
    # exactly one post-window call per window: the one that makes the last trade
    assert len(calls_after_end) == len(rets)
