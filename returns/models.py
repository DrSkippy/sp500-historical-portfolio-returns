"""Portfolio strategies: Buy & Hold, Fractional Kelly, and Insurance.

Each model is configured for one backtest window with ``model_config`` and then
fed one ``PriceBar`` per trading day through ``trade``.
"""

import datetime
import logging
import math
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from enum import StrEnum

from returns.errors import ModelNameError
from returns.types import PriceBar, Trade, WindowReturn

logger = logging.getLogger(__name__)

# Bump whenever a change alters backtest results (and regenerate the golden snapshot in the
# same commit). runner.py records it in each run's manifest; summarize.py only processes runs
# from the current version. 1 = before 2026-10-07; 2 = mode fix + stock-insuring InsuranceModel.
MODEL_VERSION = 2

DAYS_PER_YEAR = 365

BUY_HOLD_NAME = "Buy_Hold"
KELLY_PREFIX = "Fractional_Kelly"
INSURANCE_PREFIX = "Insurance"
NAME_SEPARATOR = "_"

ModelParams = dict[str, float | int]
"""Model parameters recovered from a name, keyed as in the report JSON ``params``."""


class ModelFamily(StrEnum):
    """Strategy family; the value is the report JSON ``family`` (read by app.js)."""

    BUY_HOLD = "buy_hold"
    KELLY = "kelly"
    INSURANCE = "insurance"


def years_to_timedelta(years: float) -> datetime.timedelta:
    """Convert a span in years to a timedelta using a 365-day year."""
    return datetime.timedelta(days=DAYS_PER_YEAR * years)


def days_to_years(days: int) -> float:
    """Convert a span in days to years using a 365-day year."""
    return days / DAYS_PER_YEAR


class PortfolioModel(ABC):
    """Base for every strategy: cash plus shares, traded over one window at a time.

    Subclasses define ``_build_model_name`` (their parameters) and ``daily_trade``
    (what happens between the first and last trade of a window).

    Attributes:
        stock_frac: Fraction of total capital held in stock.
    """

    stock_frac = 1.0

    def __init__(
        self,
        *,
        capital: float,
        skip_padding: datetime.timedelta,
    ) -> None:
        """Create an unconfigured model.

        Calibration (capital, padding, strategy parameters) comes from config.yaml
        via ``returns.backtest`` (``build_model``); there are no code defaults.

        Args:
            capital: Starting cash for every window.
            skip_padding: How far before a scheduled trade date to resume daily
                processing when skipping ahead (must cover data gaps; see
                ``BacktestConfig.skip_padding``).
        """
        self.init_capital = capital
        self.skip_padding = skip_padding
        self.capital = capital
        self.shares: float = 0
        self.trades: list[Trade] = []
        self.start_date = datetime.datetime.min
        self.end_date = datetime.datetime.min
        self.first_trigger = True
        self.last_trigger = True
        logger.info("Model initialized, but not configured")

    @property
    def model_name(self) -> str:
        """Name written to output files; encodes the model's parameters.

        Derived from the constructor parameters (which never change), so it is the
        same on every call; see ``parse_model_name`` for the inverse.
        """
        return self._build_model_name()

    @abstractmethod
    def _build_model_name(self) -> str:
        """Return the name for this model's parameters (see ``format_*_name``)."""

    def model_config(self, start_date: datetime.datetime, years: int = 1) -> None:
        """Reset all state for a new backtest window.

        Args:
            start_date: First day of the window.
            years: Window length in years.
        """
        # model_name is derived from the constructor parameters, so nothing here can
        # make it accumulate across the thousands of model_config calls per model
        self.capital = self.init_capital
        self.shares = 0
        self.trades = []
        #
        self.start_date = start_date
        self.end_date = start_date + years_to_timedelta(years)
        logger.info(f"Model configured with starting capital = {self.capital}")
        logger.info(f"Model configured start date = {start_date}")
        logger.info(f"Model configured for {years} years")
        #
        self.first_trigger = True
        self.last_trigger = True
        self._configure()

    def _configure(self) -> None:
        """Hook for subclasses to reset their own per-window state."""

    def _record_trade(
        self, date: datetime.datetime, bar: PriceBar, delta: float
    ) -> None:
        """Append a trade with the current capital and share count."""
        self.trades.append(Trade(date, bar, delta, self.capital, self.shares))

    def first_trade(self, date: datetime.datetime, price: PriceBar) -> None:
        """Buy stock with ``stock_frac`` of capital on the first day of the window."""
        # start by buying stocks
        self.shares = self.stock_frac * self.capital / price.price
        # reduce cash capital by the stock purchase
        self.capital -= self.shares * price.price
        self._record_trade(date, price, self.shares)

    def last_trade(self, date: datetime.datetime, price: PriceBar) -> None:
        """Sell all shares at the end of the window."""
        self.capital += self.shares * price.price
        delta_shares = -self.shares
        self.shares = 0
        self._record_trade(date, price, delta_shares)

    @abstractmethod
    def daily_trade(
        self, date: datetime.datetime, price: PriceBar
    ) -> datetime.datetime | None:
        """Handle a day inside the window (not the first or last trade).

        Returns:
            Date to skip ahead to, or None to keep processing every day.
        """

    @staticmethod
    def _skip_to(
        target: datetime.datetime, date: datetime.datetime
    ) -> datetime.datetime | None:
        """Return ``target`` if it is still ahead of ``date``, else None."""
        return None if date >= target else target

    def trade(
        self, date: datetime.datetime, price: PriceBar
    ) -> datetime.datetime | None:
        """Process one trading day.

        Args:
            date: Trading day.
            price: Price and interest rate for the day.

        Returns:
            Date the caller may skip ahead to, or None to deliver the next day.
        """
        skip_to_date = None
        if self.start_date <= date < self.end_date:
            # inside the trading window
            logger.info(f"In trading window on {date}")
            if self.first_trigger:
                logger.info(f"First trade ({date})")
                self.first_trigger = False
                self.first_trade(date, price)
            else:
                # inside the trading window, but not first or last
                skip_to_date = self.daily_trade(date, price)
        elif date >= self.end_date and self.last_trigger:
            logger.info(f"Last trade ({date})")
            self.last_trigger = False
            self.last_trade(date, price)
        else:
            return skip_to_date

        logger.info(
            f"After trading on {date}: ${self.capital} and {self.shares} shares"
        )
        return skip_to_date

    def status(self) -> list[str]:
        """Return a summary line followed by one line per trade."""
        status_str = (
            f"#### STATUS: Initial Capital={self.init_capital:10.2f} "
            f"Capital={self.capital:10.2f} Shares={self.shares:10.2f} "
            f"Trades={len(self.trades)}"
        )
        return [status_str] + [
            f"{t.date},({t.bar.price:10.2f},{t.bar.interest_rate:10.2f})"
            f",{t.delta_shares:10.2f},{t.capital:10.2f},{t.shares:10.2f}"
            for t in self.trades
        ]

    @staticmethod
    def yearly_returns(final_frac_capital: float, period_years: float) -> float:
        """Estimate the yearly compounding rate from total returns.

        Args:
            final_frac_capital: The final fraction of the initial capital after the
                investment period.
            period_years: The number of years over which the investment was held.

        Returns:
            The estimated yearly compounding rate, or 0 for invalid input.
        """
        # Check if there are no returns or the input is invalid
        if final_frac_capital <= 0.0 or period_years <= 0:
            return 0

        # Calculate and return the yearly compounding rate
        return math.exp(math.log(final_frac_capital) / period_years) - 1

    def total_returns(self) -> WindowReturn:
        """Summarize the completed window.

        Returns:
            Total and annualized returns; zeros if fewer than two trades happened.
        """
        # Ensure there are enough trades to calculate returns
        if len(self.trades) < 2 or self.init_capital <= 0:
            return WindowReturn(self.start_date, 0, 0, 0, self.model_name)

        # Calculate time span in years
        time_span_years = days_to_years(
            (self.trades[-1].date - self.trades[0].date).days
        )

        # Calculate fractional returns
        frac_returns = (self.capital - self.init_capital) / self.init_capital

        # Calculate yearly return rate
        yearly_return_rate = self.yearly_returns(1 + frac_returns, time_span_years)

        return WindowReturn(
            self.start_date,
            frac_returns,
            yearly_return_rate,
            time_span_years,
            self.model_name,
        )


class BuyHoldModel(PortfolioModel):
    """Buy & Hold: buy with all capital on the first day, sell on the last."""

    def _build_model_name(self) -> str:
        """Return the name for this model's parameters (constant for Buy & Hold)."""
        return BUY_HOLD_NAME

    def daily_trade(
        self, date: datetime.datetime, price: PriceBar
    ) -> datetime.datetime | None:
        """Handle a day inside the window (not the first or last trade).

        Buy & Hold never trades mid-window, so it asks to skip to just before the
        window ends.

        Returns:
            Date to skip ahead to, or None to keep processing every day.
        """
        return self._skip_to(self.end_date - self.skip_padding, date)


class RebalancingModel(PortfolioModel):
    """Holds ``stock_frac`` in stock and the rest in interest-bearing cash, and
    rebalances back to that split periodically.
    """

    def __init__(
        self,
        *,
        capital: float,
        stock_frac: float,
        rebalance_period_days: int,
        skip_padding: datetime.timedelta,
    ) -> None:
        """Create an unconfigured rebalancing model.

        Args:
            capital: Starting cash for every window.
            stock_frac: Target fraction of total capital held in stock.
            rebalance_period_days: Days between scheduled rebalances.
            skip_padding: See ``PortfolioModel.__init__``.
        """
        super().__init__(capital=capital, skip_padding=skip_padding)
        self.stock_frac = stock_frac
        self.rebalance_period = datetime.timedelta(days=rebalance_period_days)
        self.last_rebalance = self.start_date

    def _configure(self) -> None:
        self.last_rebalance = self.start_date
        logger.info(
            f"Model configured with re-balance period = {self.rebalance_period}"
        )

    def _accrue_interest(self, date: datetime.datetime, rate: float) -> None:
        """Compound cash at ``rate`` from the last rebalance to ``date``."""
        # interest on capital, compound daily
        self.capital *= (1.0 + rate) ** days_to_years((date - self.last_rebalance).days)

    def last_trade(self, date: datetime.datetime, price: PriceBar) -> None:
        """Credit interest since the last rebalance, then sell all shares."""
        if (date - self.last_rebalance).days > 0:
            self._accrue_interest(date, price.interest_rate)
        super().last_trade(date, price)

    def rebalance(
        self, date: datetime.datetime, price: PriceBar, rate: float | None = None
    ) -> None:
        """Credit interest, then trade back to ``stock_frac`` of total capital.

        Args:
            date: Trading day.
            price: Price for the day.
            rate: Annual rate earned by cash since the last rebalance; defaults
                to ``price.interest_rate``.
        """
        logger.info(f"Trading to re-balance on {date}")
        self._accrue_interest(date, price.interest_rate if rate is None else rate)
        # current stock value
        stock_value = self.shares * price.price
        # daily total capital
        total_capital = self.capital + stock_value
        delta_shares = (self.stock_frac * total_capital / price.price) - self.shares
        self.capital -= delta_shares * price.price
        self.shares += delta_shares
        self._record_trade(date, price, delta_shares)


class KellyModel(RebalancingModel):
    """Fractional Kelly: fixed stock/bond split, rebalanced every period."""

    def __init__(
        self,
        *,
        capital: float,
        bond_frac: float,
        rebalance_days: int,
        skip_padding: datetime.timedelta,
    ) -> None:
        """Create an unconfigured Kelly model.

        Args:
            capital: Starting cash for every window.
            bond_frac: Fraction of capital held as interest-bearing cash.
            rebalance_days: Days between rebalances.
            skip_padding: See ``PortfolioModel.__init__``.
        """
        super().__init__(
            capital=capital,
            stock_frac=1.0 - bond_frac,
            rebalance_period_days=rebalance_days,
            skip_padding=skip_padding,
        )
        self.bond_frac = bond_frac
        self.rebalance_days = rebalance_days

    def _build_model_name(self) -> str:
        return format_kelly_name(self.bond_frac, self.rebalance_days)

    def _configure(self) -> None:
        self.stock_frac = 1.0 - self.bond_frac
        logger.info(f"Model configured with bond fraction = {self.bond_frac}")
        super()._configure()

    def daily_trade(
        self, date: datetime.datetime, price: PriceBar
    ) -> datetime.datetime | None:
        """Rebalance when the period has elapsed, then skip to the next one."""
        # Only trade if rebalance period has passed
        if date >= self.last_rebalance + self.rebalance_period:
            self.rebalance(date, price)
            self.last_rebalance = date
        # skip forward to next rebalance period
        next_event = min(self.last_rebalance + self.rebalance_period, self.end_date)
        return self._skip_to(next_event - self.skip_padding, date)


@dataclass(frozen=True)
class InsurancePolicy:
    """Terms shared by every insurance variant in a run (``models.insurance``).

    Attributes:
        period_days: Days between scheduled rebalances (the policy period).
        premium_rate: Annual premium as a fraction of the insured stock value
            (0.012 = 1.2%/yr, i.e. $1/month on $1000).
        coverage_ratio: Fraction of the loss beyond the deductible that the
            policy pays (1.0 = all of it).
        loss_window_days: Number of trading days over which losses are measured.
    """

    period_days: int
    premium_rate: float
    coverage_ratio: float
    loss_window_days: int


class InsuranceModel(RebalancingModel):
    """Stock insured against sharp short-term losses, plus a cash reserve.

    The policy insures the *stock*, not the cash. Its premium is
    ``premium_rate`` per year of the insured stock value, charged daily from the
    cash reserve (``insurance_frac`` of capital at each rebalance), which
    otherwise earns the market interest rate.

    When the price falls by at least ``insurance_deductible`` over
    ``loss_window_days`` trading days, the policy pays the loss beyond the
    deductible on the insured stock:
    ``coverage_ratio * insured_value * (|loss_frac| - insurance_deductible)``,
    where ``insured_value`` is the shares held valued at the start of the loss
    window. The payout goes to cash and the portfolio rebalances the same day.
    A policy pays out at most once; it is renewed at the next scheduled
    rebalance.
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
        """Create an unconfigured insurance model.

        Args:
            capital: Starting cash for every window.
            insurance_frac: Fraction of capital kept as the cash reserve that pays
                premiums (the rest is the insured stock).
            insurance_deductible: Loss fraction over the loss window that
                triggers a payout; the policy pays only the loss beyond it.
            policy: Period, premium, coverage and loss window.
            skip_padding: See ``PortfolioModel.__init__``.
        """
        super().__init__(
            capital=capital,
            stock_frac=1 - insurance_frac,
            rebalance_period_days=policy.period_days,
            skip_padding=skip_padding,
        )
        self.insurance_frac = insurance_frac
        self.insurance_deductible = insurance_deductible
        self.policy = policy
        # prices over the last loss_window_days trading days, oldest first
        self.loss_window: deque[float] = deque()
        self.policy_active = True
        self.last_premium_date = self.start_date

    def _build_model_name(self) -> str:
        return format_insurance_name(
            self.insurance_frac,
            self.insurance_deductible,
            self.policy.period_days,
        )

    def _configure(self) -> None:
        self.stock_frac = 1 - self.insurance_frac
        self.loss_window = deque()
        self.policy_active = True
        self.last_premium_date = self.start_date
        logger.info(f"Model configured with insurance fraction = {self.insurance_frac}")
        logger.info(f"Model configured with premium rate = {self.policy.premium_rate}")
        logger.info(
            f"Model configured with insurance deductible = {self.insurance_deductible}"
        )
        super()._configure()
        logger.info(
            f"Model configured with coverage ratio = {self.policy.coverage_ratio}"
        )

    def _charge_premium(self, date: datetime.datetime, price: PriceBar) -> None:
        """Deduct the premium on the insured stock since the last charge from cash."""
        days = (date - self.last_premium_date).days
        if days > 0:
            insured_value = self.shares * price.price
            self.capital -= (
                self.policy.premium_rate * insured_value * days_to_years(days)
            )
        self.last_premium_date = date

    def first_trade(self, date: datetime.datetime, price: PriceBar) -> None:
        """Buy the insured stock; the policy (and its premium) starts today."""
        super().first_trade(date, price)
        self.last_premium_date = date

    def last_trade(self, date: datetime.datetime, price: PriceBar) -> None:
        """Charge the final premium, then sell all shares."""
        self._charge_premium(date, price)
        super().last_trade(date, price)

    def is_covered_loss(self, loss_frac: float) -> bool:
        """Whether a loss over the window qualifies for a payout right now.

        Args:
            loss_frac: Price change over the loss window (negative for a loss).
        """
        return self.policy_active and loss_frac <= -self.insurance_deductible

    def payout_amount(self, loss_frac: float, start_price: float) -> float:
        """The payout for a covered loss: the loss beyond the deductible on the
        insured stock, valued at the start of the loss window, times coverage.

        Args:
            loss_frac: Price change over the loss window (negative).
            start_price: Price at the start of the loss window.
        """
        insured_value = self.shares * start_price
        return (
            self.policy.coverage_ratio
            * insured_value
            * (-loss_frac - self.insurance_deductible)
        )

    def _loss_claim(self, price: PriceBar) -> tuple[float, float] | None:
        """Slide the loss window forward one day.

        Returns:
            ``(loss_frac, start_price)`` if the loss reaches the deductible while
            the policy is active, else None.
        """
        if len(self.loss_window) < self.policy.loss_window_days:
            # Not enough history to judge loss for payoff
            self.loss_window.append(price.price)
            return None
        start_price = self.loss_window.popleft()
        loss_frac = (price.price - start_price) / start_price
        if not self.is_covered_loss(loss_frac):
            self.loss_window.append(price.price)
            return None
        return loss_frac, start_price

    def _pay_out(
        self,
        date: datetime.datetime,
        price: PriceBar,
        loss_frac: float,
        start_price: float,
    ) -> None:
        """Pay the insured loss beyond the deductible into cash; use up the policy.

        Interest is credited up to ``date`` first, so the same-day rebalance
        doesn't credit it again.
        """
        self._accrue_interest(date, price.interest_rate)
        self.last_rebalance = date
        payout = self.payout_amount(loss_frac, start_price)
        self.capital += payout
        self.policy_active = False
        self._record_trade(date, price, 0)
        self.loss_window = deque([price.price])  # starting over
        logger.info(
            f"Insurance payout on {date} of {payout} on insured {self.shares * start_price}"
        )
        logger.info(
            f"Triggered by loss of {loss_frac} based on "
            f"{self.policy.loss_window_days} days of history"
        )

    def daily_trade(
        self, date: datetime.datetime, price: PriceBar
    ) -> datetime.datetime | None:
        """Charge the premium, renew the policy on schedule, check for a payout,
        and rebalance after a payout or when the period ends.

        Never skips ahead: losses must be checked every trading day.
        """
        self._charge_premium(date, price)
        scheduled = date >= self.last_rebalance + self.rebalance_period
        if scheduled:
            self.policy_active = True  # renew the policy
        # Loss insurance triggered?
        claim = self._loss_claim(price)
        if claim is not None:
            self._pay_out(date, price, *claim)
        if scheduled or claim is not None:
            self.rebalance(date, price)
            self.last_rebalance = date
        return None


def _format_float(value: float) -> str:
    """Shortest text that parses back to exactly ``value`` (``0.125`` -> "0.125").

    Lossless, unlike a fixed precision: ``f"{0.125:.2}"`` is "0.12", which would give
    two different variants the same name and output files.
    """
    return repr(float(value))


def format_kelly_name(bond_frac: float, rebalance_days: int) -> str:
    """Return the KellyModel name, e.g. ``Fractional_Kelly_0.2_90``."""
    return NAME_SEPARATOR.join(
        [KELLY_PREFIX, _format_float(bond_frac), str(rebalance_days)]
    )


def format_insurance_name(frac: float, deductible: float, period_days: int) -> str:
    """Return the InsuranceModel name, e.g. ``Insurance_0.1_0.15_90``.

    Premium rate, coverage ratio and loss window are not in the name; they are
    shared by every variant in a run and recorded in the run's manifest.
    """
    return NAME_SEPARATOR.join(
        [
            INSURANCE_PREFIX,
            _format_float(frac),
            _format_float(deductible),
            str(period_days),
        ]
    )


def _name_fields(name: str, prefix: str, count: int) -> list[str]:
    """Split the parameter fields after ``prefix``, requiring exactly ``count``."""
    fields = name.removeprefix(prefix + NAME_SEPARATOR).split(NAME_SEPARATOR)
    if len(fields) != count:
        raise ModelNameError(
            f"{name!r}: expected {count} parameters after {prefix!r}, got {len(fields)}"
        )
    return fields


def parse_model_name(name: str) -> tuple[ModelFamily, ModelParams]:
    """Recover the model family and parameters from a model name.

    The inverse of ``format_kelly_name`` / ``format_insurance_name``.

    Args:
        name: A model name as written to output files.

    Returns:
        ``(family, params)``; params are keyed as in the report JSON.

    Raises:
        ModelNameError: If the name is not one the ``format_*_name`` functions
            produce.
    """
    try:
        if name == BUY_HOLD_NAME:
            return ModelFamily.BUY_HOLD, {}
        if name.startswith(KELLY_PREFIX + NAME_SEPARATOR):
            # Fractional_Kelly_{bond_frac}_{rebalance}
            bond_frac, rebalance = _name_fields(name, KELLY_PREFIX, 2)
            return ModelFamily.KELLY, {
                "bond_frac": float(bond_frac),
                "rebalance": int(rebalance),
            }
        if name.startswith(INSURANCE_PREFIX + NAME_SEPARATOR):
            # Insurance_{ins_frac}_{deductible}_{rebalance}
            ins_frac, deductible, rebalance = _name_fields(name, INSURANCE_PREFIX, 3)
            return ModelFamily.INSURANCE, {
                "ins_frac": float(ins_frac),
                "deductible": float(deductible),
                "rebalance": int(rebalance),
            }
    except ValueError as e:
        raise ModelNameError(f"{name!r}: bad parameter value ({e})") from e
    raise ModelNameError(f"{name!r} is not a known model name")
