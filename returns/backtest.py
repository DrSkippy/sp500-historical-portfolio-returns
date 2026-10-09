"""Backtest engine: the model grid as typed specs, and the window-by-window tester.

``bin/runner.py`` runs every spec from ``all_model_specs`` for every window length;
the insurance-scan scripts in ``notebooks/`` reuse the same pieces.
"""

import bisect
import datetime
import logging
from collections import Counter
from dataclasses import dataclass

from returns.config import AppConfig, BacktestConfig, InsuranceGridConfig
from returns.errors import DuplicateModelNameError
from returns.models import (
    BuyHoldModel,
    InsuranceModel,
    InsurancePolicy,
    KellyModel,
    PortfolioModel,
    years_to_timedelta,
)
from returns.types import PriceBar, Row, WindowReturn

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BuyHoldSpec:
    """The Buy & Hold model (it has no parameters)."""

    def build(
        self, *, capital: float, skip_padding: datetime.timedelta
    ) -> BuyHoldModel:
        """Create the model.

        Args:
            capital: Starting cash for every window.
            skip_padding: See ``PortfolioModel.__init__``.
        """
        return BuyHoldModel(capital=capital, skip_padding=skip_padding)


@dataclass(frozen=True)
class KellySpec:
    """One fractional-Kelly variant."""

    bond_frac: float
    rebalance_days: int

    def build(self, *, capital: float, skip_padding: datetime.timedelta) -> KellyModel:
        """Create the model (see ``BuyHoldSpec.build``)."""
        return KellyModel(
            capital=capital,
            bond_frac=self.bond_frac,
            rebalance_days=self.rebalance_days,
            skip_padding=skip_padding,
        )


@dataclass(frozen=True)
class InsuranceSpec:
    """One insurance variant: a cash fraction and deductible under a shared policy."""

    insurance_frac: float
    deductible: float
    policy: InsurancePolicy

    def build(
        self, *, capital: float, skip_padding: datetime.timedelta
    ) -> InsuranceModel:
        """Create the model (see ``BuyHoldSpec.build``)."""
        return InsuranceModel(
            capital=capital,
            insurance_frac=self.insurance_frac,
            insurance_deductible=self.deductible,
            policy=self.policy,
            skip_padding=skip_padding,
        )


ModelSpec = BuyHoldSpec | KellySpec | InsuranceSpec
"""A model variant; frozen dataclasses, so they pickle cheaply to pool workers."""


def insurance_policy(insurance: InsuranceGridConfig) -> InsurancePolicy:
    """The policy terms shared by every insurance variant in the grid."""
    return InsurancePolicy(
        period_days=insurance.period_days,
        premium_rate=insurance.premium_rate,
        coverage_ratio=insurance.coverage_ratio,
        loss_window_days=insurance.loss_window_days,
    )


def build_model(spec: ModelSpec, backtest: BacktestConfig) -> PortfolioModel:
    """Create the model for a spec with the backtest's capital and skip padding."""
    return spec.build(
        capital=backtest.initial_capital, skip_padding=backtest.skip_padding
    )


def all_model_specs(config: AppConfig) -> list[ModelSpec]:
    """Every model variant in the configured grid (``models`` in config.yaml).

    Returns:
        Buy & Hold, then Kelly (bond_fracs x rebalance_days), then insurance
        (fracs x deductibles), in config order.
    """
    kelly = config.models.kelly
    insurance = config.models.insurance
    policy = insurance_policy(insurance)
    return [
        BuyHoldSpec(),
        *(
            KellySpec(bond_frac=bond_frac, rebalance_days=rebalance_days)
            for bond_frac in kelly.bond_fracs
            for rebalance_days in kelly.rebalance_days
        ),
        *(
            InsuranceSpec(insurance_frac=frac, deductible=deductible, policy=policy)
            for frac in insurance.fracs
            for deductible in insurance.deductibles
        ),
    ]


def unique_model_names(specs: list[ModelSpec], backtest: BacktestConfig) -> list[str]:
    """Names of the model variants, checked to be distinct.

    Output file names are built from model names, so two variants with the same
    name would overwrite each other's results in the parallel run.

    Args:
        specs: Model variants, e.g. from ``all_model_specs``.
        backtest: Backtest settings used to build each model.

    Returns:
        One name per spec, in order.

    Raises:
        DuplicateModelNameError: If any two specs produce the same name.
    """
    names = [build_model(spec, backtest).model_name for spec in specs]
    duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
    if duplicates:
        raise DuplicateModelNameError(
            f"Model variants share names {duplicates}; check the models grid in "
            "config.yaml for repeated values"
        )
    return names


def model_tester(
    model: PortfolioModel,
    data: list[Row],
    price_index: int,
    interest_index: int,
    *,
    years: int,
    stride_days: int,
) -> list[WindowReturn]:
    """Backtest a model over every window of ``years`` length in the data.

    Window start dates step forward by ``stride_days`` from the first date.

    Args:
        model: Strategy to test; reconfigured for each window.
        data: Combined rows sorted by date.
        price_index: Column of the traded price in each row.
        interest_index: Column of the annual interest rate in each row.
        years: Window length in years.
        stride_days: Days between successive window start dates.

    Returns:
        One result per window.
    """
    test_interval = datetime.timedelta(days=stride_days)
    test_start_date = data[0][0]  # first (oldest) date in data
    model_returns: list[WindowReturn] = []

    logger.info("Starting model testing")

    # Pre-compute date list once for bisect lookups
    dates = [row[0] for row in data]

    while test_start_date + years_to_timedelta(years) < data[-1][0]:
        model.model_config(test_start_date, years=years)

        start_idx = bisect.bisect_left(dates, test_start_date - model.skip_padding)
        skip_to_date = None
        for row in data[start_idx:]:
            if skip_to_date is not None and row[0] < skip_to_date:
                continue
            # data is (stock price, interest rate by years)
            bar = PriceBar(row[price_index], row[interest_index])
            skip_to_date = model.trade(row[0], bar)
            if not model.last_trigger:
                # last trade of this window is done; the rest of the data can't affect it
                break

        for log_line in model.status():
            logger.debug(log_line)

        result = model.total_returns()
        model_returns.append(result)
        logger.debug(
            f"frac_returns={result.frac_return:5.2%} yearly_return_rate={result.yearly_return_rate}"
            f" model={model.model_name} start_date={test_start_date}"
        )
        test_start_date += test_interval

    logger.info("End model testing")
    return model_returns
