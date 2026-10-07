from pathlib import Path

import pytest

from returns.errors import EmptyReturnsError, NoModelOutputsError
from returns.types import SUMMARY_COLUMNS
from tests.conftest import load_bin_module

generate_report = load_bin_module("generate_report")


def write_summary(path: Path, rows: list[list[str]]) -> Path:
    path.write_text(
        "\n".join([",".join(SUMMARY_COLUMNS)] + [",".join(r) for r in rows]) + "\n"
    )
    return path


def summary_row(years: int, model: str = "Buy_Hold") -> list[str]:
    return [
        "100",
        f"{years}.0",
        model,
        "0.1",
        "0.05",
        "0.09",
        "0.04",
        "0.2",
        "0.1",
        "0.25",
        "0.08",
        "0.03",
    ]


def test_load_summary_maps_columns_and_sorts_by_year(tmp_path: Path) -> None:
    path = write_summary(tmp_path / "s.csv", [summary_row(2), summary_row(1)])
    name, rows = generate_report.load_summary(path)
    assert name == "Buy_Hold"
    assert [r["year"] for r in rows] == [1, 2]
    assert list(rows[0]) == [
        "year",
        "mean_total",
        "mean_yearly",
        "median_total",
        "median_yearly",
        "sdev_total",
        "sdev_yearly",
        "fraction_losing",
        "mode_total",
        "mode_yearly",
        "sample_size",
    ]
    assert rows[0]["sample_size"] == 100
    assert rows[0]["fraction_losing"] == 0.25


def test_load_summary_empty_raises(tmp_path: Path) -> None:
    with pytest.raises(EmptyReturnsError):
        generate_report.load_summary(write_summary(tmp_path / "s.csv", []))


def test_load_distributions_keeps_requested_years(tmp_path: Path) -> None:
    path = tmp_path / "t.json"
    path.write_text('{"1": [0.1], "2": [0.2], "5": [0.5]}')
    assert generate_report.load_distributions(path, [1, 5]) == {
        "1": [0.1],
        "5": [0.5],
    }


def test_find_latest_files_picks_latest_complete_pair(tmp_path: Path) -> None:
    for name in [
        "summary_Buy_Hold_2026-01-01_0000.csv",
        "summary_Buy_Hold_2026-02-01_0000.csv",
        "total_returns_Buy_Hold_2026-01-01_0000.json",
        "total_returns_Buy_Hold_2026-02-01_0000.json",
        "summary_Insurance_0.1_0.09_90_2026-01-01_0000.csv",  # no JSON partner
        "returns_1_Buy_Hold_2026-01-01_0000.csv",
    ]:
        (tmp_path / name).touch()
    found = generate_report.find_latest_files(tmp_path)
    assert list(found) == ["Buy_Hold"]
    assert found["Buy_Hold"][0].name == "summary_Buy_Hold_2026-02-01_0000.csv"
    assert found["Buy_Hold"][1].name == "total_returns_Buy_Hold_2026-02-01_0000.json"


def test_find_latest_files_raises_when_nothing_matches(tmp_path: Path) -> None:
    with pytest.raises(NoModelOutputsError):
        generate_report.find_latest_files(tmp_path)
