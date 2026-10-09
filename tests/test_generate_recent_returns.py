import datetime
import random
from typing import Sequence

import pytest

from returns.errors import EmptyHistoryError
from tests.conftest import load_bin_module

grr = load_bin_module("generate_recent_returns")


def reference_stats(values: Sequence[float]) -> dict[str, float]:
    """The original pure-Python compute_stats, kept as an oracle."""
    n = len(values)
    s = sorted(values)
    mean = sum(values) / n
    median = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    std = (sum((v - mean) ** 2 for v in values) / n) ** 0.5

    def percentile(p: float) -> float:
        idx = p / 100.0 * (n - 1)
        lo, hi = int(idx), min(int(idx) + 1, n - 1)
        return s[lo] + (s[hi] - s[lo]) * (idx - lo)

    return {
        "mean": mean,
        "median": median,
        "std": std,
        "p10": percentile(10),
        "p25": percentile(25),
        "p75": percentile(75),
        "p90": percentile(90),
    }


@pytest.mark.parametrize("n", [1, 2, 7, 100, 1001])
def test_compute_stats_matches_original_implementation(n: int) -> None:
    rng = random.Random(n)
    values = [rng.gauss(0, 0.02) for _ in range(n)]
    got = grr.compute_stats(values)
    want = reference_stats(values)
    assert list(got) == list(want)
    for key in want:
        assert got[key] == pytest.approx(want[key], rel=1e-12, abs=1e-15)


def test_compute_stats_empty() -> None:
    assert grr.compute_stats([]) == {}


def test_compute_returns() -> None:
    assert grr.compute_returns([100, 110, 99], 1) == pytest.approx([0.1, -0.1])
    assert grr.compute_returns([100, 110, 99], 2) == pytest.approx([-0.01])


def test_percentile_rank_without_history_raises() -> None:
    with pytest.raises(EmptyHistoryError):
        grr.percentile_rank([], 0.1)


def test_percentile_rank_is_strictly_less() -> None:
    assert grr.percentile_rank([1, 2, 3, 4], 3) == 50.0


def test_build_recent_entries_takes_non_overlapping_periods_from_the_end() -> None:
    start = datetime.date(2026, 1, 1)
    quotes = [(start + datetime.timedelta(days=i), 100.0 + i) for i in range(10)]
    entries = grr.build_recent_entries(quotes, window=3, n_recent=2, hist_values=[0])
    assert [e["date"] for e in entries] == ["2026-01-07", "2026-01-10"]
    assert entries[-1]["value"] == pytest.approx(3 / 106)
    assert entries[-1]["percentile"] == 100.0


def test_build_recent_entries_stops_at_start_of_data() -> None:
    quotes = [(f"d{i}", 100.0) for i in range(5)]
    entries = grr.build_recent_entries(quotes, window=2, n_recent=10, hist_values=[1])
    assert [e["date"] for e in entries] == ["d2", "d4"]


def test_build_recent_entries_too_short() -> None:
    assert grr.build_recent_entries([("d", 1.0)], 1, 5, [0.0]) == []


def test_format_date() -> None:
    assert grr.format_date(datetime.date(2026, 3, 4)) == "2026-03-04"
    assert grr.format_date("2026-03-04") == "2026-03-04"
