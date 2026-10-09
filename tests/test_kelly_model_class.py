import unittest
import datetime

from returns.types import PriceBar
from tests.conftest import TEST_SKIP_PADDING, make_kelly


class TestKellyModel(unittest.TestCase):

    def setUp(self) -> None:
        self.kelly_model = make_kelly()
        self.kelly_model.model_config(datetime.datetime(2020, 1, 1), years=2)

    def test_init(self) -> None:
        self.assertEqual(self.kelly_model.init_capital, 10000)
        self.assertEqual(self.kelly_model.init_bond_frac, 0.4)
        self.assertEqual(self.kelly_model.init_rebalance_period_days, 90)
        self.assertEqual(self.kelly_model.stock_frac, 0.6)
        self.assertEqual(self.kelly_model.last_rebalance, datetime.datetime(2020, 1, 1))

    def test_model_config(self) -> None:
        start_date = datetime.datetime(2020, 1, 1)
        self.kelly_model.model_config(start_date, years=2)
        self.assertEqual(self.kelly_model.capital, 10000)
        self.assertEqual(self.kelly_model.shares, 0)
        self.assertEqual(self.kelly_model.bond_frac, 0.4)
        # Add more assertions here to test state after configuration

    def test_first_trade(self) -> None:
        self.kelly_model.capital = 10000
        self.kelly_model.stock_frac = 0.6  # Assuming 60% stock fraction
        date = datetime.datetime(2020, 1, 1)
        price = PriceBar(100, 1)  # Example price and interest rate
        self.kelly_model.first_trade(date, price)
        self.assertEqual(self.kelly_model.shares, 60)
        self.assertEqual(self.kelly_model.capital, 4000)

    def test_last_trade_no_interest(self) -> None:
        self.kelly_model.shares = 60
        self.kelly_model.capital = 4000
        self.kelly_model.last_rebalance = datetime.datetime(2020, 1, 1)
        date = datetime.datetime(2020, 12, 30)
        price = PriceBar(100, 0)  # Example price and interest rate
        self.kelly_model.last_trade(date, price)
        self.assertEqual(self.kelly_model.shares, 0)
        self.assertEqual(self.kelly_model.capital, 10000)

    def test_last_trade_interest(self) -> None:
        self.kelly_model.shares = 60
        self.kelly_model.capital = 1000
        self.kelly_model.last_rebalance = datetime.datetime(2020, 1, 1)
        date = datetime.datetime(2020, 12, 31)
        price = PriceBar(100, 0.10)  # Example price and interest rate
        self.kelly_model.last_trade(date, price)
        self.assertEqual(self.kelly_model.shares, 0)
        self.assertAlmostEqual(self.kelly_model.capital, 7100)

    def test_rebalance(self) -> None:
        self.kelly_model.shares = 150
        self.kelly_model.capital = 10000
        self.kelly_model.last_rebalance = datetime.datetime(2020, 1, 1)
        date = datetime.datetime(2020, 4, 1)
        price = PriceBar(100, 0.10)
        self.kelly_model.rebalance(date, price)
        # 10241.13 is capital after interest, 241 buys 2 shares at most
        self.assertAlmostEqual(self.kelly_model.capital, 10096.187344628)
        self.assertEqual(self.kelly_model.shares, 151.44281016942574)

    def test_daily_trade_no_rebalance(self) -> None:
        self.kelly_model.end_date = datetime.datetime(2022, 12, 31)
        skip = self.kelly_model.daily_trade(
            datetime.datetime(2020, 1, 2), PriceBar(100, 1)
        )
        self.assertEqual(self.kelly_model.last_rebalance, datetime.datetime(2020, 1, 1))
        self.assertEqual(
            skip,
            datetime.datetime(2020, 1, 1)
            + datetime.timedelta(days=90)
            - TEST_SKIP_PADDING,
        )

    def test_daily_trade_rebalance(self) -> None:
        self.kelly_model.shares = 150
        self.kelly_model.capital = 10000
        self.kelly_model.last_rebalance = datetime.datetime(2020, 1, 1)
        self.kelly_model.end_date = datetime.datetime(2022, 12, 31)
        skip = self.kelly_model.daily_trade(
            datetime.datetime(2020, 4, 1), PriceBar(100, 0.1)
        )
        self.assertEqual(self.kelly_model.last_rebalance, datetime.datetime(2020, 4, 1))
        self.assertEqual(skip, datetime.datetime(2020, 6, 24))
        self.assertAlmostEqual(self.kelly_model.capital, 10096.187344628)
        self.assertEqual(self.kelly_model.shares, 151.44281016942574)


if __name__ == "__main__":
    unittest.main()
