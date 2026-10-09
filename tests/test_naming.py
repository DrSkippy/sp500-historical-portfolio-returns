import datetime
from pathlib import Path

from returns.naming import (
    new_run_timestamp,
    returns_file_path,
    returns_file_suffix,
    run_manifest_path,
    run_suffix,
    summary_file_path,
    summary_model_name,
    total_returns_path,
)

OUT = Path("out")
STAMP = "2026-10-07_1550"


def test_run_timestamp_format() -> None:
    assert new_run_timestamp(datetime.datetime(2026, 10, 7, 15, 50)) == STAMP


def test_names_round_trip_for_a_model_with_underscores() -> None:
    model = "Insurance_0.05_0.09_90"
    suffix = run_suffix(model, STAMP)
    returns_path = returns_file_path(OUT, 15, suffix)
    assert returns_path == OUT / f"returns_15_{model}_{STAMP}.csv"
    assert returns_file_suffix(returns_path) == suffix
    summary = summary_file_path(OUT, suffix)
    assert summary == OUT / f"summary_{model}_{STAMP}.csv"
    assert summary_model_name(summary, STAMP) == model
    assert total_returns_path(summary) == OUT / f"total_returns_{model}_{STAMP}.json"
    assert run_manifest_path(OUT, STAMP) == OUT / f"run_{STAMP}.json"
