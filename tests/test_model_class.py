import unittest
import datetime
import math
from returns.models import Model


class TestModel(unittest.TestCase):

    def setUp(self) -> None:
        self.model = Model()
        self.model.model_config(datetime.datetime(2020, 1, 1), years=2)

    def test_init(self) -> None:
        self.assertEqual(self.model.init_capital, 10000)
        # Add more assertions here to test initial state

    def test_model_config(self) -> None:
        start_date = datetime.datetime(2020, 1, 1)
        self.model.model_config(start_date, years=2)
        self.assertEqual(self.model.capital, 10000)
        self.assertEqual(self.model.shares, 0)
        self.assertEqual(self.model.start_date, start_date)
        self.assertEqual(self.model.end_date, datetime.datetime(2021, 12, 31))
        # Add more assertions here to test state after configuration

    def test_first_trade(self) -> None:
        self.model.capital = 10000
        date = datetime.datetime(2020, 1, 1)
        price = [100, 0]  # Example price
        self.model.first_trade(date, price)
        self.assertEqual(self.model.shares, 100)
        self.assertEqual(self.model.capital, 0)
        self.assertEqual(len(self.model.trades), 1)
        self.assertTupleEqual(self.model.trades[0], (date, [100, 0], 100, 0, 100))

    def test_last_trade(self) -> None:
        self.model.shares = 100
        self.model.capital = 0
        date = datetime.datetime(2021, 1, 1)
        price = [100, 0]  # Example price
        self.model.last_trade(date, price)
        self.assertEqual(self.model.shares, 0)
        self.assertEqual(self.model.capital, 10000)
        self.assertEqual(len(self.model.trades), 1)
        self.assertTupleEqual(self.model.trades[0], (date, [100, 0], -100, 10000, 0))

    def test_daily_trade(self) -> None:
        # Window 1 year
        self.model.end_date = datetime.datetime(2021, 1, 1)
        _shares = self.model.shares
        _capital = self.model.capital
        _len_trades = len(self.model.trades)
        # Daily trade does nothing except move to end of window!
        result = self.model.daily_trade(datetime.datetime(2020, 6, 1), [100, 0])
        # Jump to end of window - 6 days padding
        self.assertEqual(result, datetime.datetime(2020, 12, 26, 0, 0))
        # Daily trade does nothing except move to end of window!
        result = self.model.daily_trade(datetime.datetime(2020, 12, 27), [100, 0])
        # Already in the padding period
        self.assertEqual(result, None)
        # Daily trade does nothing except move to end of window, so no changes to model
        self.assertEqual(self.model.shares, _shares)
        self.assertEqual(self.model.capital, _capital)
        self.assertEqual(len(self.model.trades), _len_trades)

    def test_trade_first(self) -> None:
        # Test the 'trade' method by simulating different scenarios
        # Example: self.model.trade(date, price)
        # Add assertions here
        self.model.first_trigger = True
        self.model.last_trigger = True
        self.model.shares = 0
        self.model.capital = 10000
        date = datetime.datetime(2020, 1, 1)
        price = [100, 0]
        skip = self.model.trade(date, price)
        self.assertEqual(self.model.shares, 100)
        self.assertEqual(self.model.capital, 0)
        self.assertEqual(len(self.model.trades), 1)
        self.assertTupleEqual(self.model.trades[0], (date, [100, 0], 100, 0, 100))
        self.assertFalse(self.model.first_trigger)
        self.assertTrue(self.model.last_trigger)
        self.assertIsNone(skip)

    def test_trade_daily(self) -> None:
        # Test the 'trade' method by simulating different scenarios
        # Example: self.model.trade(date, price)
        # Add assertions here
        self.model.first_trigger = False
        self.model.last_trigger = True
        self.model.shares = 100
        self.model.capital = 0
        date = datetime.datetime(2020, 1, 15)
        price = [100, 0]
        skip = self.model.trade(date, price)
        self.assertEqual(self.model.shares, 100)
        self.assertEqual(self.model.capital, 0)
        self.assertEqual(len(self.model.trades), 0)
        self.assertTrue(self.model.last_trigger)
        self.assertEqual(skip, datetime.datetime(2021, 12, 25, 0, 0))

    def test_trade_last(self) -> None:
        # Test the 'trade' method by simulating different scenarios
        # Example: self.model.trade(date, price)
        # Add assertions here
        self.model.first_trigger = False
        self.model.last_trigger = True
        self.model.shares = 100
        self.model.capital = 0
        date = datetime.datetime(2021, 12, 31)
        price = [100, 0]
        skip = self.model.trade(date, price)
        self.assertEqual(self.model.shares, 0)
        self.assertEqual(self.model.capital, 10000)
        self.assertEqual(len(self.model.trades), 1)
        self.assertFalse(self.model.last_trigger)
        self.assertIsNone(skip)

    def test_status(self) -> None:
        # Test the 'status' method by checking its output
        self.model.capital = 10000
        date = datetime.datetime(2020, 1, 1)
        price = [100, 0]  # Example price
        self.model.first_trade(date, price)
        self.assertEqual(len(self.model.status()), 2)
        self.assertEqual(
            self.model.status()[1],
            "2020-01-01 00:00:00,(    100.00,      0.00),    100.00,      0.00,    100.00",
        )
        self.assertEqual(
            self.model.status()[0],
            "#### STATUS: Initial Capital=  10000.00 Capital=      0.00 Shares=    100.00 Trades=1",
        )
        print(" ".join(self.model.status()))

    def test_yearly_returns(self) -> None:
        result = self.model.yearly_returns(1.5, 1)
        self.assertAlmostEqual(result, math.exp(math.log(1.5)) - 1)
        self.assertAlmostEqual(self.model.yearly_returns(1.5, 2), math.sqrt(1.5) - 1)
        self.assertAlmostEqual(self.model.yearly_returns(-1.5, 2), 0)
        self.assertAlmostEqual(self.model.yearly_returns(1.5, 0), 0)

    def test_total_returns(self) -> None:
        # Test the 'total_returns' method by simulating trades
        # Example: self.model.total_returns()
        # Add assertions here
        self.model.first_trade(datetime.datetime(2020, 1, 1), [100, 0])
        self.model.last_trade(datetime.datetime(2020, 12, 31), [100, 0])
        result = self.model.total_returns()
        self.assertEqual(len(self.model.trades), 2)
        self.assertEqual(result[0], datetime.datetime(2020, 1, 1))
        self.assertAlmostEqual(result[1], 0)
        self.assertAlmostEqual(result[2], 0)
        self.assertAlmostEqual(result[3], 1)
        self.assertEqual(result[4], "Buy_Hold")


if __name__ == "__main__":
    unittest.main()
