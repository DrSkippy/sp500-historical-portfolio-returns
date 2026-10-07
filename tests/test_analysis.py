import datetime
from typing import Any

import numpy as np
import pytest

from returns.analysis import (
    aggregate_returns,
    calculate_mode,
    format_metrics,
    get_aggregate_returns_by_period,
    get_df_aggregate_returns_by_period,
    plot_df,
    plot_histograms,
    plot_period_comparison_data,
)
from returns.errors import EmptyReturnsError
from returns.types import SUMMARY_COLUMNS


class TestCalculateMode:
    def test_calculate_mode(self) -> None:
        data = np.array([25.0] * 800 + [24.0] * 100 + [26.0] * 100)
        hist = np.histogram(data, bins=45, range=(0, 50))
        mode = calculate_mode(hist)
        assert 23 < mode < 26

    def test_mode_is_centre_of_peak_bin(self) -> None:
        counts = np.array([1, 5, 2])
        edges = np.array([0.0, 1.0, 2.0, 3.0])
        assert calculate_mode((counts, edges)) == 1.5

    def test_peak_in_first_bin(self) -> None:
        counts = np.array([9, 1, 1])
        edges = np.array([0.0, 1.0, 2.0, 3.0])
        assert calculate_mode((counts, edges)) == 0.5

    def test_peak_in_last_bin(self) -> None:
        counts = np.array([1, 1, 9])
        edges = np.array([0.0, 1.0, 2.0, 3.0])
        assert calculate_mode((counts, edges)) == 2.5


class TestAggregateReturns:
    def _make_returns(self, n: int = 5, time_span: float = 1.0) -> list[list[Any]]:
        values = [0.10, -0.05, 0.20, -0.10, 0.15]
        return [
            [
                datetime.datetime(2020, 1, i + 1),
                values[i],
                values[i],
                time_span,
                "Model",
            ]
            for i in range(n)
        ]

    def test_sample_size(self) -> None:
        stats, _ = aggregate_returns(self._make_returns())
        assert stats[0] == 5

    def test_mean_total_returns(self) -> None:
        stats, _ = aggregate_returns(self._make_returns())
        # mean([0.10, -0.05, 0.20, -0.10, 0.15]) = 0.06
        assert abs(stats[3] - 0.06) < 1e-10

    def test_fraction_losing_starts(self) -> None:
        stats, _ = aggregate_returns(self._make_returns())
        # 2 negatives out of 5
        assert abs(stats[9] - 0.4) < 1e-10

    def test_total_returns_list(self) -> None:
        _, total_returns = aggregate_returns(self._make_returns())
        assert total_returns == pytest.approx([0.10, -0.05, 0.20, -0.10, 0.15])


class TestGetAggregateReturnsByPeriod:
    def _make_period_data(self, n: int = 5, time_span: float = 1.0) -> list[list[Any]]:
        values = [0.10, -0.05, 0.20, -0.10, 0.15]
        return [
            [
                datetime.datetime(2020, 1, i + 1),
                values[i],
                values[i],
                time_span,
                "Model",
            ]
            for i in range(n)
        ]

    def test_get_aggregate_returns_by_period(self) -> None:
        data = {
            1: self._make_period_data(time_span=1.0),
            2: self._make_period_data(time_span=2.0),
        }
        stats, totals = get_aggregate_returns_by_period(data)
        assert len(stats) == 2
        assert len(totals) == 2


def _rows(values: list[float], years: float = 1.0) -> list[list[Any]]:
    return [
        [datetime.datetime(2020, 1, i + 1), v, v / years, years, "Model"]
        for i, v in enumerate(values)
    ]


def test_aggregate_returns_empty_raises() -> None:
    with pytest.raises(EmptyReturnsError):
        aggregate_returns([])


def test_format_metrics_lists_every_statistic() -> None:
    stats, _ = aggregate_returns(_rows([0.10, -0.05, 0.20, -0.10, 0.15]))
    text = format_metrics(stats)
    assert text.splitlines()[0] == "### AGGREGATE RETURNS ### Model ###"
    assert "Mean Returns             = 6.00%" in text
    assert "Losing start days        = 40.00%" in text
    assert len(text.splitlines()) == 12


def test_summary_table_and_plots_render(monkeypatch: pytest.MonkeyPatch) -> None:
    import matplotlib

    matplotlib.use("Agg")
    stats, totals = get_aggregate_returns_by_period(
        {2: _rows([0.2, 0.1, 0.3], 2.0), 1: _rows([0.1, -0.05, 0.2])}
    )
    df = get_df_aggregate_returns_by_period(stats)
    assert list(df.columns) == SUMMARY_COLUMNS
    assert df["time_span"].tolist() == [1.0, 2.0]
    plot_df(df, df2=df)
    plot_histograms(totals)
    plot_period_comparison_data(df)
