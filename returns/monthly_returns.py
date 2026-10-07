"""Rolling ~monthly returns sampled from daily prices."""

import logging
from typing import Any, Sequence

import numpy as np
import pandas as pd
from matplotlib import pyplot as plt

logger = logging.getLogger(__name__)

OFFSET = 30
DEFAULT_PRICE_COLUMN = "Adj Close**"
HISTOGRAM_BINS = 60


class MonthlyReturns:
    """Distribution of returns over ``offset`` trading days.

    Returns use the formula ``(current - prior) / current``.
    """

    def __init__(
        self,
        daily_close: Sequence[Sequence[Any]],
        header: list[str],
        price_column: str = DEFAULT_PRICE_COLUMN,
        offset: int = OFFSET,
    ) -> None:
        """Compute the rolling returns.

        Args:
            daily_close: Daily rows, oldest first.
            header: Column names for ``daily_close``.
            price_column: Column holding the price.
            offset: Lookback in rows (trading days).
        """
        self.df = pd.DataFrame(daily_close, columns=header)
        prices = self.df[price_column]
        self.returns = (prices - prices.shift(offset)) / prices
        self.returns = self.returns.dropna().reset_index(drop=True)
        logger.info(f"Monthly returns initialized with {len(self.returns)} samples.")

    def write_to_csv(self, filename: str) -> None:
        """Write the monthly returns to a CSV file.

        Args:
            filename: The name of the file to write the returns to.
        """
        self.returns.to_csv(filename, index=False)
        logger.info(f"Monthly returns written to {filename}")

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

    def plot_returns(self, bins: int = HISTOGRAM_BINS) -> None:
        """Show a histogram of the returns."""
        plt.figure(figsize=(10, 5))
        plt.hist(
            self.returns.to_numpy(), bins=bins, label="Monthly Returns", color="blue"
        )
        plt.title("Monthly Returns Distribution")
        plt.xlabel("Returns")
        plt.ylabel("Frequency")
        plt.legend()
        plt.grid()
        plt.show()
