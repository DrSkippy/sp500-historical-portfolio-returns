import logging

from returns.data import get_combined_sp500_interest_data
from returns.monthly_returns import MonthlyReturns

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(process)d|%(asctime)s|%(levelname)s|%(funcName)20s()|%(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    filename="app1.log",
    filemode="w",
)

if __name__ == "__main__":
    d, h = get_combined_sp500_interest_data()

    m = MonthlyReturns(d, h)

    for i in range(20):
        print(m.sample())

    m.summary()

    m.plot_returns()

    m.write_to_csv("./out_data/monthly_returns.csv")
