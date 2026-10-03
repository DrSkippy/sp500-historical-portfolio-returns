import logging
import numpy as np
import pandas as pd
from matplotlib import pyplot as plt

logger = logging.getLogger(__name__)

OFFSET = 30


class MonthlyReturns:

    def __init__(self, daily_close, header):
        self.df = pd.DataFrame(daily_close, columns=header)
        self.returns = (
            self.df["Adj Close**"] - self.df["Adj Close**"].shift(OFFSET)
        ) / self.df["Adj Close**"]
        self.returns.dropna(inplace=True)
        self.returns = self.returns.reset_index(drop=True)
        logger.info(f"Monthly returns initialized with {len(self.returns)} samples.")

    def write_to_csv(self, filename):
        """
        Writes the monthly returns to a CSV file.

        Args:
            filename (str): The name of the file to write the returns to.
        """
        self.returns.to_csv(filename, index=False)
        logger.info(f"Monthly returns written to {filename}")

    def sample(self):
        return self.returns[np.random.randint(len(self.returns))]

    def summary(self):
        print("Monthly Returns Summary:")
        print(f"Total Samples: {len(self.returns)}")
        print(f"Mean Return: {self.returns.mean():.4f}")
        print(f"Standard Deviation: {self.returns.std():.4f}")
        print(f"Median Return: {self.returns.median():.4f}")
        print(f"Minimum Return: {self.returns.min():.4f}")
        print(f"Maximum Return: {self.returns.max():.4f}")

    def plot_returns(self):
        plt.figure(figsize=(10, 5))
        plt.hist(self.returns.values, bins=60, label="Monthly Returns", color="blue")
        plt.title("Monthly Returns Distribution")
        plt.xlabel("Returns")
        plt.ylabel("Frequency")
        plt.legend()
        plt.grid()
        plt.show()
