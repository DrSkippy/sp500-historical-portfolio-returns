"""Historical fair premium per deductible: payouts / insured-value-years over the full history.

The scenario (cash fraction, premium, coverage, deductibles) is
``insurance_scan.fair_premium`` in config.yaml; other parameters come from
``backtest`` / ``models.insurance``.

Usage:
    poetry run python notebooks/insurance_scan/fair_premium.py sp500 qqq
"""

import datetime
import sys
from typing import Any

from returns.config import load_config
from returns.data import get_combined_data, load_dataset
from returns.models import DAYS_PER_YEAR, InsuranceModel, days_to_years
from returns.types import PriceBar


class Tracking(InsuranceModel):
    def __init__(self, **kw: Any) -> None:
        super().__init__(**kw)
        self.paid = 0.0
        self.exposure = 0.0  # insured value x years
        self.events: list[tuple[datetime.datetime, float]] = []

    def _charge_premium(self, date, price):  # type: ignore[no-untyped-def]
        days = (date - self.last_premium_date).days
        if days > 0:
            self.exposure += self.shares * price.price * days_to_years(days)
        super()._charge_premium(date, price)

    def _pay_out(self, date, price, loss_frac, start_price):  # type: ignore[no-untyped-def]
        amount = (
            self.coverage_ratio
            * self.shares
            * start_price
            * (-loss_frac - self.insurance_deductible)
        )
        self.paid += amount
        self.events.append((date, -loss_frac))
        super()._pay_out(date, price, loss_frac, start_price)


config = load_config()
scenario = config.insurance_scan.fair_premium
insurance = config.models.insurance
for ds in sys.argv[1:]:
    dataset = load_dataset(ds, config)
    rows, _ = get_combined_data(dataset)
    years = (rows[-1][0] - rows[0][0]).days // DAYS_PER_YEAR - 1
    print(
        f"\n{ds}: {rows[0][0]:%Y}-{rows[-1][0]:%Y}, one continuous {years}-year policy,"
        f" coverage {scenario.coverage_ratio}, premium {scenario.premium_rate:.2%}"
    )
    for d in scenario.deductibles:
        m = Tracking(
            capital=config.backtest.initial_capital,
            skip_padding=config.backtest.skip_padding,
            insurance_frac=scenario.insurance_frac,
            insurance_period=insurance.period_days,
            premium_rate=scenario.premium_rate,
            insurance_deductible=d,
            coverage_ratio=scenario.coverage_ratio,
            loss_window_days=insurance.loss_window_days,
        )
        m.model_config(rows[0][0], years=years)
        for r in rows:
            m.trade(r[0], PriceBar(r[dataset.price_index], r[dataset.interest_index]))
            if not m.last_trigger:
                break
        big = sorted(m.events, key=lambda e: -e[1])[:4]
        print(
            f"  deductible {d:4.0%}: {len(m.events):3d} payouts, fair premium {m.paid / m.exposure:6.3%}/yr"
            f"  largest: " + ", ".join(f"{e[0]:%Y-%m-%d} {e[1]:.0%}" for e in big)
        )
