import unittest
from returns.models import *

class TestInsuranceModel(unittest.TestCase):

    def setUp(self):
        self.insurance_model = InsuranceModel()
        self.insurance_model.model_config(datetime.datetime(2020, 1, 1), years=2)

    def test_init(self):
        self.assertEqual(self.insurance_model.init_capital, 10000)
        self.assertEqual(self.insurance_model.init_insurance_frac, 0.10)
        self.assertEqual(self.insurance_model.init_insurance_period, 90)
        self.assertEqual(self.insurance_model.init_insurance_rate, -0.005)
        self.assertEqual(self.insurance_model.init_insurance_deductible, 0.15)
        self.assertEqual(self.insurance_model.model_name, "Insurance_0.1_0.15_90")
        self.assertEqual(self.insurance_model.stock_frac, 0.90)
    def test_model_config(self):
        start_date = datetime.datetime(2020, 1, 1)
        self.insurance_model.model_config(start_date, years=2)
        self.assertEqual(self.insurance_model.capital, 10000)
        self.assertEqual(self.insurance_model.shares, 0)
        # Add more assertions here to test state after configuration
    def test_rebalance(self):
        self.insurance_model.shares = 900
        self.insurance_model.capital = 10000
        self.insurance_model.last_rebalance = datetime.datetime(2020, 1, 1)
        date = datetime.datetime(2020, 4, 1)
        price = [100, -0.10]
        self.insurance_model.rebalance(date, price)
        # 9740.04 is capital after interest, sell ~ 2 shares
        self.assertAlmostEqual(self.insurance_model.capital,  9974.074037685497)
        self.assertEqual(self.insurance_model.shares, 897.6666633916948)
    def test_daily_trade_with_incomplete_history(self):
        self.insurance_model.shares = 900
        self.insurance_model.capital = 10000
        self.insurance_model.last_rebalance = datetime.datetime(2020, 1, 1)
        self.insurance_model.last_price = [100, 100, 100] # only 3 days of history
        date = datetime.datetime(2020, 1, 10)
        price = [100, -0.10]  # interest rate should be irrelevant here!
        self.insurance_model.daily_trade(date, price)
        self.assertEqual(self.insurance_model.shares, 900)
        self.assertEqual(self.insurance_model.capital, 10000)
        self.assertEqual(len(self.insurance_model.trades), 0)
        self.assertEqual(self.insurance_model.last_rebalance, datetime.datetime(2020, 1, 1))
        self.assertListEqual(self.insurance_model.last_price, [100, 100, 100, 100])

    def test_daily_trade_with_insurance_payout(self):
        self.insurance_model.shares = 900
        self.insurance_model.capital = 10000
        self.insurance_model.last_rebalance = datetime.datetime(2020, 1, 1)
        self.insurance_model.last_price = [100, 100, 100, 95, 90, 88] # only 6 days of history, 15% drop
        date = datetime.datetime(2020, 1, 10)
        price = [84, -0.10]  # interest rate should be irrelevant here!
        self.insurance_model.daily_trade(date, price)
        # 16% drop, 10x payout on 10000 ~ 16000
        # 90000 -> 84000 stock value is a loss of 15000 so by 8000/84 ~ 96 shares
        self.assertEqual(self.insurance_model.capital, 9160.19678086083)
        self.assertEqual(self.insurance_model.shares, 981.4496550922327)
        self.assertEqual(len(self.insurance_model.trades), 2) # one payout and one rebalance
        self.assertEqual(self.insurance_model.last_rebalance, datetime.datetime(2020, 1, 10))
        self.assertListEqual(self.insurance_model.last_price, [84])

    def test_daily_trade_without_insurance_payout(self):
        self.insurance_model.shares = 900
        self.insurance_model.capital = 10000
        self.insurance_model.last_rebalance = datetime.datetime(2020, 1, 1)
        self.insurance_model.last_price = [100, 100, 100, 100, 100, 100]
        date = datetime.datetime(2020, 1, 4)  # 3 days < 90-day rebalance period
        price = [99, -0.005]                  # 1% loss, below 15% deductible
        self.insurance_model.daily_trade(date, price)
        self.assertEqual(self.insurance_model.shares, 900)
        self.assertEqual(self.insurance_model.capital, 10000)
        self.assertEqual(len(self.insurance_model.trades), 0)
        self.assertEqual(self.insurance_model.last_rebalance, datetime.datetime(2020, 1, 1))
        self.assertListEqual(self.insurance_model.last_price, [100, 100, 100, 100, 100, 99])


if __name__ == '__main__':
    unittest.main()
