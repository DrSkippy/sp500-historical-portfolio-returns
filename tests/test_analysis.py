import datetime

import numpy as np
import pytest

from returns.analysis import aggregate_returns, calculate_mode, get_aggregate_returns_by_period


class TestCalculateMode:
    def test_calculate_mode(self):
        # Cluster data at ~25 within [0, 50]; peak must NOT be in bin 0 to avoid edge case
        data = np.array([25.0] * 800 + [24.0] * 100 + [26.0] * 100)
        hist = np.histogram(data, bins=45, range=(0, 50))
        mode = calculate_mode(hist)
        assert 23 < mode < 26


class TestAggregateReturns:
    def _make_returns(self, n=5, time_span=1.0):
        values = [0.10, -0.05, 0.20, -0.10, 0.15]
        return [
            [datetime.datetime(2020, 1, i + 1), values[i], values[i], time_span, "Model"]
            for i in range(n)
        ]

    def test_sample_size(self):
        stats, _ = aggregate_returns(self._make_returns())
        assert stats[0] == 5

    def test_mean_total_returns(self):
        stats, _ = aggregate_returns(self._make_returns())
        # mean([0.10, -0.05, 0.20, -0.10, 0.15]) = 0.06
        assert abs(stats[3] - 0.06) < 1e-10

    def test_fraction_losing_starts(self):
        stats, _ = aggregate_returns(self._make_returns())
        # 2 negatives out of 5
        assert abs(stats[9] - 0.4) < 1e-10

    def test_total_returns_list(self):
        _, total_returns = aggregate_returns(self._make_returns())
        assert total_returns == pytest.approx([0.10, -0.05, 0.20, -0.10, 0.15])


class TestGetAggregateReturnsByPeriod:
    def _make_period_data(self, n=5, time_span=1.0):
        values = [0.10, -0.05, 0.20, -0.10, 0.15]
        return [
            [datetime.datetime(2020, 1, i + 1), values[i], values[i], time_span, "Model"]
            for i in range(n)
        ]

    def test_get_aggregate_returns_by_period(self):
        data = {
            1: self._make_period_data(time_span=1.0),
            2: self._make_period_data(time_span=2.0),
        }
        stats, totals = get_aggregate_returns_by_period(data)
        assert len(stats) == 2
        assert len(totals) == 2
