import datetime
import json
from pathlib import Path

import pytest

from returns.config import load_config
from returns.data import (
    Dataset,
    create_combined_data_file,
    create_summary_file,
    create_summary_files,
    get_combined_data,
    get_interest_data,
    get_model_comparison_data,
    get_model_run_outputs,
    get_price_data,
    load_dataset,
    parse_number,
    read_summary_data,
    returns_file_suffix,
    total_returns_path,
)
from returns.errors import DatasetConfigError, MissingPriceColumnError
from returns.types import RETURNS_CSV_HEADER, SUMMARY_COLUMNS

PRICE_HEADER = "Date\tOpen\tHigh\tLow\tClose*\tAdj Close**\tVolume\n"


@pytest.fixture
def price_file(tmp_path: Path) -> Path:
    content = (
        PRICE_HEADER + "Jan 02, 2020\t101.0\t103.0\t100.0\t102.0\t90.0\t1,100\n"
        "Jan 01, 2020\t100.0\t102.0\t99.0\t101.0\t101.0\t1,000\n"
    )
    f = tmp_path / "prices.tab"
    f.write_text(content)
    return f


@pytest.fixture
def interest_file(tmp_path: Path) -> Path:
    f = tmp_path / "interest.tab"
    f.write_text("observation_date\tGS1\n2019-01-01\t2.50\n\n2020-01-01\t1.50\n")
    return f


def write_config(tmp_path: Path, price_column: str = "Close*") -> Path:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(f"""datasets:
  qqq:
    price_path: prices.tab
    combined_path: combined.csv
    out_dir: out/
    report_data: report_data_qqq.json
    price_column: "{price_column}"
    label: QQQ
    recent_source: file
    recent_symbol: QQQ
    recent_data: recent_qqq.json
sources:
  interest_path: interest.tab
""")
    return cfg


@pytest.fixture
def dataset(tmp_path: Path, price_file: Path, interest_file: Path) -> Dataset:
    return load_dataset("qqq", load_config(write_config(tmp_path)))


def test_parse_number_handles_thousands_separators() -> None:
    assert parse_number("6,790.09") == 6790.09
    assert parse_number("2,909,570,674") == 2909570674.0
    assert parse_number("-0.5") == -0.5


def test_get_price_data_sorts_oldest_first(price_file: Path) -> None:
    data, header = get_price_data(price_file)
    assert len(data) == 2
    assert data[0][0] == datetime.datetime(2020, 1, 1)
    assert data[0][5] == 101.0  # Adj Close**
    assert data[1][6] == 1100.0  # Volume with a thousands separator
    assert header[5] == "Adj Close**"


def test_get_interest_data_skips_blank_rows_and_converts_percent(
    interest_file: Path,
) -> None:
    data, header = get_interest_data(interest_file)
    assert header == ["GS1"]
    assert set(data) == {2019, 2020}
    assert data[2020][0] == pytest.approx(0.015)


def test_dataset_indices(dataset: Dataset) -> None:
    assert dataset.price_index == 4  # Close*
    assert dataset.interest_index == 7  # after the 7 price-file columns


def test_load_dataset_unknown_name_raises(tmp_path: Path, price_file: Path) -> None:
    with pytest.raises(DatasetConfigError, match="Unknown dataset 'nope'"):
        load_dataset("nope", load_config(write_config(tmp_path)))


def test_load_dataset_missing_price_column_raises(
    tmp_path: Path, price_file: Path
) -> None:
    config = load_config(write_config(tmp_path, price_column="Close"))
    with pytest.raises(MissingPriceColumnError, match="'Close'"):
        load_dataset("qqq", config)


def test_get_combined_data_appends_interest_for_the_row_year(dataset: Dataset) -> None:
    data, header = get_combined_data(dataset)
    assert len(data[0]) == 8  # 7 price columns + 1 interest
    assert header[-1] == "GS1"
    assert data[0][dataset.price_index] == pytest.approx(101.0)
    assert data[0][dataset.interest_index] == pytest.approx(0.015)


def test_get_combined_data_uses_last_interest_year_for_later_rows(
    tmp_path: Path, price_file: Path
) -> None:
    (tmp_path / "interest.tab").write_text("observation_date\tGS1\n2018-01-01\t4.0\n")
    dataset = load_dataset("qqq", load_config(write_config(tmp_path)))
    data, _ = get_combined_data(dataset)
    assert data[0][dataset.interest_index] == pytest.approx(0.04)


def test_create_combined_data_file_writes_dataset_path(
    tmp_path: Path, dataset: Dataset
) -> None:
    create_combined_data_file(dataset)
    lines = (tmp_path / "combined.csv").read_text().splitlines()
    assert lines[0] == "Date,Open,High,Low,Close*,Adj Close**,Volume,GS1"
    assert len(lines) == 3


def test_returns_file_suffix_and_total_returns_path() -> None:
    path = Path("out/returns_10_Fractional_Kelly_0.2_90_2026-01-01_0000.csv")
    assert returns_file_suffix(path) == "Fractional_Kelly_0.2_90_2026-01-01_0000.csv"
    assert total_returns_path(Path("out/summary_Buy_Hold_x.csv")) == Path(
        "out/total_returns_Buy_Hold_x.json"
    )


def write_returns(out_dir: Path, years: int, suffix: str, values: list[float]) -> Path:
    path = out_dir / f"returns_{years}_{suffix}"
    rows = [",".join(RETURNS_CSV_HEADER)] + [
        f"2020-01-{i + 1:02d} 00:00:00,{v},{v / years},{float(years)},Buy_Hold"
        for i, v in enumerate(values)
    ]
    path.write_text("\n".join(rows) + "\n")
    return path


SUFFIX = "Buy_Hold_2026-01-01_0000.csv"
VALUES = [0.10, -0.05, 0.20, -0.10, 0.15]


def test_get_model_run_outputs_reads_each_year(tmp_path: Path) -> None:
    for years in (1, 2):
        write_returns(tmp_path, years, SUFFIX, VALUES)
    results, header, summary_path = get_model_run_outputs(tmp_path, SUFFIX, [1, 2])
    assert set(results) == {1, 2}
    assert header == RETURNS_CSV_HEADER
    assert results[1][0][0] == datetime.datetime(2020, 1, 1)
    assert summary_path == tmp_path / f"summary_{SUFFIX}"


def test_create_summary_file_round_trips_through_read_summary_data(
    tmp_path: Path,
) -> None:
    for years in (1, 2):
        write_returns(tmp_path, years, SUFFIX, VALUES)
    csv_path, json_path = create_summary_file(
        *get_model_run_outputs(tmp_path, SUFFIX, [1, 2])
    )
    df, totals = read_summary_data(csv_path)
    assert list(df.columns) == SUMMARY_COLUMNS
    assert df["time_span"].tolist() == [1.0, 2.0]
    assert df["sample_size"].tolist() == [5, 5]
    assert totals["1"] == pytest.approx(VALUES)
    assert json.loads(json_path.read_text()).keys() == {"1", "2"}


def test_create_summary_files_one_summary_per_run(tmp_path: Path) -> None:
    other = "Buy_Hold_2026-02-01_0000.csv"
    files = [
        write_returns(tmp_path, years, suffix, VALUES)
        for years in (1, 2)
        for suffix in (SUFFIX, other)
    ]
    created = create_summary_files(tmp_path, files, [1, 2])
    assert sorted(p.name for p, _ in created) == [
        f"summary_{SUFFIX}",
        f"summary_{other}",
    ]


def test_get_model_comparison_data_selects_the_requested_year(tmp_path: Path) -> None:
    summaries = []
    for name, scale in (("A_2026-01-01_0000.csv", 1.0), ("B_2026-01-01_0000.csv", 2.0)):
        for years in (1, 2):
            write_returns(tmp_path, years, name, [v * scale for v in VALUES])
        summaries.append(
            create_summary_file(*get_model_run_outputs(tmp_path, name, [1, 2]))[0]
        )
    comparison = get_model_comparison_data(summaries, year=2)
    assert comparison["time_span"].tolist() == [2.0, 2.0]
    assert comparison["mean_total_returns"].tolist() == pytest.approx([0.06, 0.12])
