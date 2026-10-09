"""Historical fair premium per deductible: payouts / insured-value-years over the full history.

The scenario (cash fraction, premium, coverage, deductibles) is
``insurance_scan.fair_premium`` in config.yaml; other parameters come from
``backtest`` / ``models.insurance``.

Usage:
    poetry run python notebooks/insurance_scan/fair_premium.py sp500 qqq
"""

import argparse
import dataclasses
import datetime

from returns.backtest import insurance_policy
from returns.config import AppConfig, load_config
from returns.data import get_combined_data, load_dataset
from returns.models import (
    DAYS_PER_YEAR,
    InsuranceModel,
    InsurancePolicy,
    days_to_years,
)
from returns.types import PriceBar

LARGEST_EVENTS_SHOWN = 4


class TrackingInsuranceModel(InsuranceModel):
    """InsuranceModel that also totals payouts and insured exposure.

    Attributes:
        paid: Sum of all payouts.
        exposure: Insured value x years (the premium base).
        events: ``(date, loss)`` for each payout.
    """

    def __init__(
        self,
        *,
        capital: float,
        insurance_frac: float,
        insurance_deductible: float,
        policy: InsurancePolicy,
        skip_padding: datetime.timedelta,
    ) -> None:
        super().__init__(
            capital=capital,
            insurance_frac=insurance_frac,
            insurance_deductible=insurance_deductible,
            policy=policy,
            skip_padding=skip_padding,
        )
        self.paid = 0.0
        self.exposure = 0.0  # insured value x years
        self.events: list[tuple[datetime.datetime, float]] = []

    def _charge_premium(self, date: datetime.datetime, price: PriceBar) -> None:
        days = (date - self.last_premium_date).days
        if days > 0:
            self.exposure += self.shares * price.price * days_to_years(days)
        super()._charge_premium(date, price)

    def _pay_out(
        self,
        date: datetime.datetime,
        price: PriceBar,
        loss_frac: float,
        start_price: float,
    ) -> None:
        self.paid += self.payout_amount(loss_frac, start_price)
        self.events.append((date, -loss_frac))
        super()._pay_out(date, price, loss_frac, start_price)


def report_dataset(name: str, config: AppConfig) -> None:
    """Print the fair premium at each deductible for one continuous policy."""
    scenario = config.insurance_scan.fair_premium
    policy = dataclasses.replace(
        insurance_policy(config.models.insurance),
        premium_rate=scenario.premium_rate,
        coverage_ratio=scenario.coverage_ratio,
    )
    dataset = load_dataset(name, config)
    rows, _ = get_combined_data(dataset)
    first_date, last_date = rows[0][0], rows[-1][0]
    years = (last_date - first_date).days // DAYS_PER_YEAR - 1
    print(
        f"\n{name}: {first_date:%Y}-{last_date:%Y}, one continuous {years}-year policy,"
        f" coverage {scenario.coverage_ratio}, premium {scenario.premium_rate:.2%}"
    )
    for deductible in scenario.deductibles:
        model = TrackingInsuranceModel(
            capital=config.backtest.initial_capital,
            skip_padding=config.backtest.skip_padding,
            insurance_frac=scenario.insurance_frac,
            insurance_deductible=deductible,
            policy=policy,
        )
        model.model_config(first_date, years=years)
        for row in rows:
            model.trade(
                row[0], PriceBar(row[dataset.price_index], row[dataset.interest_index])
            )
            if not model.last_trigger:
                break
        largest = sorted(model.events, key=lambda event: -event[1])
        print(
            f"  deductible {deductible:4.0%}: {len(model.events):3d} payouts,"
            f" fair premium {model.paid / model.exposure:6.3%}/yr  largest: "
            + ", ".join(
                f"{date:%Y-%m-%d} {loss:.0%}"
                for date, loss in largest[:LARGEST_EVENTS_SHOWN]
            )
        )


def main() -> None:
    """Report each dataset named on the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("datasets", nargs="+", help="dataset keys from config.yaml")
    args = parser.parse_args()
    config = load_config()
    for name in args.datasets:
        report_dataset(name, config)


if __name__ == "__main__":
    main()
