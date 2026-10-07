"""Portfolio strategies: Buy & Hold, Fractional Kelly, and Insurance.

Each model is configured for one backtest window with ``model_config`` and then
fed one ``PriceBar`` per trading day through ``trade``.
"""

import datetime
import logging
import math
from typing import Any

from returns.types import PriceBar, Trade, WindowReturn

logger = logging.getLogger(__name__)

DAYS_PER_YEAR = 365
STRIDE_DAYS = 3  # stride for data sampling
PADDING_TIME_DELTA = datetime.timedelta(
    days=2 * STRIDE_DAYS
)  # days to pad the jumps in the data

BUY_HOLD_NAME = "Buy_Hold"
KELLY_PREFIX = "Fractional_Kelly"
INSURANCE_PREFIX = "Insurance"


def years_to_timedelta(years: float) -> datetime.timedelta:
    """Convert a span in years to a timedelta using a 365-day year."""
    return datetime.timedelta(days=DAYS_PER_YEAR * years)


def days_to_years(days: int) -> float:
    """Convert a span in days to years using a 365-day year."""
    return days / DAYS_PER_YEAR


class Model:
    """Buy & Hold: buy with all capital on the first day, sell on the last.

    Attributes:
        model_name: Name written to output files; encodes the parameters for
            subclasses (see ``parse_model_name``).
        stock_frac: Fraction of total capital held in stock.
    """

    model_name = BUY_HOLD_NAME
    stock_frac = 1.0

    def __init__(
        self,
        capital: float = 10000,
        skip_padding: datetime.timedelta = PADDING_TIME_DELTA,
    ) -> None:
        """Create an unconfigured model.

        Args:
            capital: Starting cash for every window.
            skip_padding: How far before a scheduled trade date to resume daily
                processing when skipping ahead (must cover data gaps).
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

    def _build_model_name(self) -> str:
        """Return the name for this model's parameters (constant for Buy & Hold)."""
        return BUY_HOLD_NAME

    def model_config(self, start_date: datetime.datetime, years: int = 1) -> None:
        """Reset all state for a new backtest window.

        Args:
            start_date: First day of the window.
            years: Window length in years.
        """
        # assign, never append: model_config runs thousands of times per model
        self.model_name = self._build_model_name()
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


class RebalancingModel(Model):
    """Holds ``stock_frac`` in stock and the rest in interest-bearing cash, and
    rebalances back to that split periodically.
    """

    def __init__(
        self,
        capital: float = 10000,
        stock_frac: float = 1.0,
        rebalance_period_days: int = 90,
        skip_padding: datetime.timedelta = PADDING_TIME_DELTA,
    ) -> None:
        """Create an unconfigured rebalancing model.

        Args:
            capital: Starting cash for every window.
            stock_frac: Target fraction of total capital held in stock.
            rebalance_period_days: Days between scheduled rebalances.
            skip_padding: See ``Model.__init__``.
        """
        super().__init__(capital, skip_padding)
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

    model_name = KELLY_PREFIX

    def __init__(
        self,
        capital: float = 10000,
        bond_frac: float = 0.4,
        rebalance_period: int = 90,
        skip_padding: datetime.timedelta = PADDING_TIME_DELTA,
    ) -> None:
        """Create an unconfigured Kelly model.

        Args:
            capital: Starting cash for every window.
            bond_frac: Fraction of capital held as interest-bearing cash.
            rebalance_period: Days between rebalances.
            skip_padding: See ``Model.__init__``.
        """
        super().__init__(capital, 1.0 - bond_frac, rebalance_period, skip_padding)
        self.init_bond_frac = bond_frac
        self.bond_frac = bond_frac
        self.init_rebalance_period_days = rebalance_period

    def _build_model_name(self) -> str:
        return format_kelly_name(self.init_bond_frac, self.init_rebalance_period_days)

    def _configure(self) -> None:
        self.bond_frac = self.init_bond_frac
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

    model_name = INSURANCE_PREFIX

    def __init__(
        self,
        capital: float = 10000,
        insurance_frac: float = 0.10,
        insurance_period: int = 90,
        premium_rate: float = 0.012,
        insurance_deductible: float = 0.15,
        coverage_ratio: float = 1.0,
        loss_window_days: int = 6,
        skip_padding: datetime.timedelta = PADDING_TIME_DELTA,
    ) -> None:
        """Create an unconfigured insurance model.

        Args:
            capital: Starting cash for every window.
            insurance_frac: Fraction of capital kept as the cash reserve that pays
                premiums (the rest is the insured stock).
            insurance_period: Days between scheduled rebalances (policy period).
            premium_rate: Annual premium as a fraction of the insured stock value
                (0.012 = 1.2%/yr, i.e. $1/month on $1000).
            insurance_deductible: Loss fraction over the loss window that
                triggers a payout; the policy pays only the loss beyond it.
            coverage_ratio: Fraction of the loss beyond the deductible that the
                policy pays (1.0 = all of it).
            loss_window_days: Number of trading days over which losses are measured.
            skip_padding: See ``Model.__init__``.
        """
        super().__init__(capital, 1 - insurance_frac, insurance_period, skip_padding)
        self.init_insurance_frac = insurance_frac
        self.init_insurance_period = insurance_period
        self.init_insurance_deductible = insurance_deductible
        self.premium_rate = premium_rate
        self.coverage_ratio = coverage_ratio
        self.losses_days = loss_window_days
        self.insurance_frac = insurance_frac
        self.insurance_deductible = insurance_deductible
        self.last_price: list[float] = []  # list of prices for losses days
        self.policy_active = True
        self.last_premium_date = self.start_date

    def _build_model_name(self) -> str:
        return format_insurance_name(
            self.init_insurance_frac,
            self.init_insurance_deductible,
            self.init_insurance_period,
        )

    def _configure(self) -> None:
        self.insurance_frac = self.init_insurance_frac
        self.stock_frac = 1 - self.insurance_frac
        self.insurance_deductible = self.init_insurance_deductible
        self.last_price = []
        self.policy_active = True
        self.last_premium_date = self.start_date
        logger.info(f"Model configured with insurance fraction = {self.insurance_frac}")
        logger.info(f"Model configured with premium rate = {self.premium_rate}")
        logger.info(
            f"Model configured with insurance deductible = {self.insurance_deductible}"
        )
        super()._configure()
        logger.info(f"Model configured with coverage ratio = {self.coverage_ratio}")

    def _charge_premium(self, date: datetime.datetime, price: PriceBar) -> None:
        """Deduct the premium on the insured stock since the last charge from cash."""
        days = (date - self.last_premium_date).days
        if days > 0:
            insured_value = self.shares * price.price
            self.capital -= self.premium_rate * insured_value * days_to_years(days)
        self.last_premium_date = date

    def first_trade(self, date: datetime.datetime, price: PriceBar) -> None:
        """Buy the insured stock; the policy (and its premium) starts today."""
        super().first_trade(date, price)
        self.last_premium_date = date

    def last_trade(self, date: datetime.datetime, price: PriceBar) -> None:
        """Charge the final premium, then sell all shares."""
        self._charge_premium(date, price)
        super().last_trade(date, price)

    def _loss_triggered(self, price: PriceBar) -> tuple[float, float] | None:
        """Slide the loss window forward one day.

        Returns:
            ``(loss_frac, start_price)`` if the loss reaches the deductible while
            the policy is active, else None.
        """
        if len(self.last_price) < self.losses_days:
            # Not enough history to judge loss for payoff
            self.last_price.append(price.price)
            return None
        start_price = self.last_price.pop(0)
        loss_frac = (price.price - start_price) / start_price
        if not self.policy_active or loss_frac > -self.insurance_deductible:
            self.last_price.append(price.price)
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
        insured_value = self.shares * start_price
        payout = (
            self.coverage_ratio
            * insured_value
            * (-loss_frac - self.insurance_deductible)
        )
        self.capital += payout
        self.policy_active = False
        self._record_trade(date, price, 0)
        self.last_price = [price.price]  # starting over
        logger.info(
            f"Insurance payout on {date} of {payout} on insured {insured_value}"
        )
        logger.info(
            f"Triggered by loss of {loss_frac} based on {self.losses_days} days of history"
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
        trigger = self._loss_triggered(price)
        if trigger is not None:
            self._pay_out(date, price, *trigger)
        if scheduled or trigger is not None:
            self.rebalance(date, price)
            self.last_rebalance = date
        return None


def format_kelly_name(bond_frac: float, rebalance_days: int) -> str:
    """Return the KellyModel name, e.g. ``Fractional_Kelly_0.2_90``."""
    return f"{KELLY_PREFIX}_{bond_frac:.2}_{rebalance_days}"


def format_insurance_name(frac: float, deductible: float, period_days: int) -> str:
    """Return the InsuranceModel name, e.g. ``Insurance_0.1_0.15_90``."""
    return f"{INSURANCE_PREFIX}_{frac:.2}_{deductible:.2}_{period_days}"


def parse_model_name(name: str) -> tuple[str, dict[str, Any]]:
    """Recover the model family and parameters from a model name.

    The inverse of ``format_kelly_name`` / ``format_insurance_name``.

    Args:
        name: A model name as written to output files.

    Returns:
        ``(family, params)`` where family is "buy_hold", "kelly", "insurance",
        or "unknown" (with empty params).
    """
    if name == BUY_HOLD_NAME:
        return "buy_hold", {}
    if name.startswith(f"{KELLY_PREFIX}_"):
        # Fractional_Kelly_{bond_frac}_{rebalance}
        parts = name.split("_")
        return "kelly", {
            "bond_frac": float(parts[2]),
            "rebalance": int(parts[3]),
        }
    if name.startswith(f"{INSURANCE_PREFIX}_"):
        # Insurance_{ins_frac}_{deductible}_{rebalance}
        parts = name.split("_")
        return "insurance", {
            "ins_frac": float(parts[1]),
            "deductible": float(parts[2]),
            "rebalance": int(parts[3]),
        }
    return "unknown", {}
