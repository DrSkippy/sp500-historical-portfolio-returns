"""Rolling ~monthly returns sampled from daily prices."""

import logging
from typing import Any, Sequence

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class MonthlyReturns:
    """Distribution of returns over ``offset`` trading days.

    Returns use the formula ``(current - prior) / current``.
    """

    def __init__(
        self,
        daily_close: Sequence[Sequence[Any]],
        header: list[str],
        price_column: str,
        offset: int,
    ) -> None:
        """Compute the rolling returns.

        Args:
            daily_close: Daily rows, oldest first.
            header: Column names for ``daily_close``.
            price_column: Column holding the price (the dataset's ``price_column``).
            offset: Lookback in rows (trading days; ``monthly_returns.offset_days``).
        """
        self.df = pd.DataFrame(daily_close, columns=header)
        prices = self.df[price_column]
        self.returns = (prices - prices.shift(offset)) / prices
        self.returns = self.returns.dropna().reset_index(drop=True)
        logger.info("Monthly returns initialized with %s samples.", len(self.returns))

    def write_to_csv(self, filename: str) -> None:
        """Write the monthly returns to a CSV file.

        Args:
            filename: The name of the file to write the returns to.
        """
        self.returns.to_csv(filename, index=False)
        logger.info("Monthly returns written to %s", filename)

    def sample(self, rng: np.random.Generator | None = None) -> float:
        """Draw one return uniformly at random.

        Args:
            rng: Random generator; NumPy's global generator if None.
        """
        n = len(self.returns)
        index = np.random.randint(n) if rng is None else int(rng.integers(n))
        return float(self.returns[index])

    def summary(self) -> str:
        """Return descriptive statistics as a multi-line report."""
        return "\n".join(
            [
                "Monthly Returns Summary:",
                f"Total Samples: {len(self.returns)}",
                f"Mean Return: {self.returns.mean():.4f}",
                f"Standard Deviation: {self.returns.std():.4f}",
                f"Median Return: {self.returns.median():.4f}",
                f"Minimum Return: {self.returns.min():.4f}",
                f"Maximum Return: {self.returns.max():.4f}",
            ]
        )
