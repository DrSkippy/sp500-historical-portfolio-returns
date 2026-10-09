import unittest
import datetime
from collections import deque

from returns.types import PriceBar
from tests.conftest import make_insurance


class TestInsuranceModel(unittest.TestCase):

    def setUp(self) -> None:
        self.insurance_model = make_insurance()
        self.insurance_model.model_config(datetime.datetime(2020, 1, 1), years=2)

    def test_init(self) -> None:
        self.assertEqual(self.insurance_model.init_capital, 10000)
        self.assertEqual(self.insurance_model.insurance_frac, 0.10)
        self.assertEqual(self.insurance_model.policy.period_days, 90)
        self.assertEqual(self.insurance_model.policy.premium_rate, 0.012)
        self.assertEqual(self.insurance_model.policy.coverage_ratio, 1.0)
        self.assertEqual(self.insurance_model.insurance_deductible, 0.15)
        self.assertEqual(self.insurance_model.model_name, "Insurance_0.1_0.15_90")
        self.assertEqual(self.insurance_model.stock_frac, 0.90)

    def test_model_config(self) -> None:
        start_date = datetime.datetime(2020, 1, 1)
        self.insurance_model.model_config(start_date, years=2)
        self.assertEqual(self.insurance_model.capital, 10000)
        self.assertEqual(self.insurance_model.shares, 0)
        # Add more assertions here to test state after configuration

    def test_rebalance(self) -> None:
        self.insurance_model.shares = 900
        self.insurance_model.capital = 10000
        self.insurance_model.last_rebalance = datetime.datetime(2020, 1, 1)
        date = datetime.datetime(2020, 4, 1)
        price = PriceBar(100, -0.10)
        self.insurance_model.rebalance(date, price)
        # 9740.04 is capital after interest, sell ~ 2 shares
        self.assertAlmostEqual(self.insurance_model.capital, 9974.074037685497)
        self.assertEqual(self.insurance_model.shares, 897.6666633916948)

    def test_daily_trade_with_incomplete_history(self) -> None:
        self.insurance_model.shares = 900
        self.insurance_model.capital = 10000
        self.insurance_model.last_rebalance = datetime.datetime(2020, 1, 1)
        self.insurance_model.loss_window = deque([100, 100, 100])  # only 3 days
        date = datetime.datetime(2020, 1, 10)
        price = PriceBar(100, -0.10)  # interest rate should be irrelevant here!
        self.insurance_model.daily_trade(date, price)
        self.assertEqual(self.insurance_model.shares, 900)
        # 9 days of premium on $90,000 of insured stock
        self.assertAlmostEqual(
            self.insurance_model.capital, 10000 - 0.012 * 90000 * 9 / 365
        )
        self.assertEqual(len(self.insurance_model.trades), 0)
        self.assertEqual(
            self.insurance_model.last_rebalance, datetime.datetime(2020, 1, 1)
        )
        self.assertListEqual(list(self.insurance_model.loss_window), [100] * 4)

    def test_daily_trade_with_insurance_payout(self) -> None:
        self.insurance_model.shares = 900
        self.insurance_model.capital = 10000
        self.insurance_model.last_rebalance = datetime.datetime(2020, 1, 1)
        self.insurance_model.loss_window = deque(
            [100, 100, 100, 95, 90, 88]
        )  # only 6 days of history, 15% drop
        date = datetime.datetime(2020, 1, 10)
        price = PriceBar(84, 0.04)
        self.insurance_model.daily_trade(date, price)
        # 9 days of premium on the insured stock, 9 days of interest on the cash
        cash = (10000 - 0.012 * 900 * 84 * 9 / 365) * 1.04 ** (9 / 365)
        # the policy insures the stock: 900 shares worth $90,000 at the window start
        # lose 16%; it pays the 1% beyond the 15% deductible = $900
        cash += 90000 * (0.16 - 0.15)
        total = cash + 900 * 84
        self.assertAlmostEqual(self.insurance_model.trades[0].capital, cash)
        self.assertAlmostEqual(self.insurance_model.capital, 0.1 * total)
        self.assertAlmostEqual(self.insurance_model.shares, 0.9 * total / 84)
        self.assertEqual(
            len(self.insurance_model.trades), 2
        )  # one payout and one rebalance
        self.assertEqual(
            self.insurance_model.last_rebalance, datetime.datetime(2020, 1, 10)
        )
        self.assertListEqual(list(self.insurance_model.loss_window), [84])
        self.assertFalse(self.insurance_model.policy_active)

    def test_daily_trade_without_insurance_payout(self) -> None:
        self.insurance_model.shares = 900
        self.insurance_model.capital = 10000
        self.insurance_model.last_rebalance = datetime.datetime(2020, 1, 1)
        self.insurance_model.loss_window = deque([100, 100, 100, 100, 100, 100])
        date = datetime.datetime(2020, 1, 4)  # 3 days < 90-day rebalance period
        price = PriceBar(99, -0.005)  # 1% loss, below 15% deductible
        self.insurance_model.daily_trade(date, price)
        self.assertEqual(self.insurance_model.shares, 900)
        # 3 days of premium, no payout
        self.assertAlmostEqual(
            self.insurance_model.capital, 10000 - 0.012 * 900 * 99 * 3 / 365
        )
        self.assertEqual(len(self.insurance_model.trades), 0)
        self.assertEqual(
            self.insurance_model.last_rebalance, datetime.datetime(2020, 1, 1)
        )
        self.assertListEqual(
            list(self.insurance_model.loss_window), [100, 100, 100, 100, 100, 99]
        )


if __name__ == "__main__":
    unittest.main()
