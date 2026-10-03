import datetime

import pytest

import returns.data
from returns.data import (
    combined_interest_index,
    combined_sp500_index,
    get_combined_sp500_interest_data,
    get_interest_data,
    get_sp500_data,
)


@pytest.fixture
def sp500_file(tmp_path):
    content = (
        "Date\tOpen\tHigh\tLow\tClose\tAdj Close**\tVolume\n"
        "Jan 01, 2020\t100.0\t102.0\t99.0\t101.0\t101.0\t1000\n"
        "Jan 02, 2020\t101.0\t103.0\t100.0\t102.0\t102.0\t1100\n"
    )
    f = tmp_path / "SP500.tab"
    f.write_text(content)
    return f


@pytest.fixture
def interest_file(tmp_path):
    content = (
        "observation_date\tGS1\n"
        "2020-01-01\t1.50\n"
    )
    f = tmp_path / "interest.tab"
    f.write_text(content)
    return f


def test_get_sp500_data_row_count(sp500_file, monkeypatch):
    monkeypatch.setattr(returns.data, "sp500_input_path", str(sp500_file))
    data, _ = get_sp500_data()
    assert len(data) == 2


def test_get_sp500_data_date_parsed(sp500_file, monkeypatch):
    monkeypatch.setattr(returns.data, "sp500_input_path", str(sp500_file))
    data, _ = get_sp500_data()
    assert data[0][0] == datetime.datetime(2020, 1, 1)


def test_get_sp500_data_adj_close(sp500_file, monkeypatch):
    monkeypatch.setattr(returns.data, "sp500_input_path", str(sp500_file))
    data, _ = get_sp500_data()
    assert data[0][5] == 101.0  # Adj Close** at sp500_index=5


def test_get_interest_data_year_key(interest_file, monkeypatch):
    monkeypatch.setattr(returns.data, "interest_input_path", str(interest_file))
    data, _ = get_interest_data()
    assert 2020 in data


def test_get_interest_data_value_count(interest_file, monkeypatch):
    monkeypatch.setattr(returns.data, "interest_input_path", str(interest_file))
    data, _ = get_interest_data()
    assert len(data[2020]) == 1


def test_get_interest_data_value_parsed(interest_file, monkeypatch):
    monkeypatch.setattr(returns.data, "interest_input_path", str(interest_file))
    data, _ = get_interest_data()
    assert abs(data[2020][0] - 0.015) < 1e-10


def test_combined_row_length(sp500_file, interest_file, monkeypatch):
    monkeypatch.setattr(returns.data, "sp500_input_path", str(sp500_file))
    monkeypatch.setattr(returns.data, "interest_input_path", str(interest_file))
    data, _ = get_combined_sp500_interest_data()
    assert len(data) == 2
    assert len(data[0]) == 8  # 7 SP500 + 1 interest


def test_combined_sp500_index(sp500_file, interest_file, monkeypatch):
    monkeypatch.setattr(returns.data, "sp500_input_path", str(sp500_file))
    monkeypatch.setattr(returns.data, "interest_input_path", str(interest_file))
    data, _ = get_combined_sp500_interest_data()
    assert data[0][combined_sp500_index] == 101.0


def test_combined_interest_index(sp500_file, interest_file, monkeypatch):
    monkeypatch.setattr(returns.data, "sp500_input_path", str(sp500_file))
    monkeypatch.setattr(returns.data, "interest_input_path", str(interest_file))
    data, _ = get_combined_sp500_interest_data()
    assert abs(data[0][combined_interest_index] - 0.015) < 1e-10


@pytest.fixture
def dataset_config(tmp_path, monkeypatch):
    prices = tmp_path / "QQQ.tab"
    prices.write_text(
        "Date\tOpen\tHigh\tLow\tClose*\tAdj Close**\tVolume\n"
        "Jan 02, 2020\t101.0\t103.0\t100.0\t102.0\t90.0\t1100\n"
    )
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "datasets:\n"
        "  qqq:\n"
        f"    price_path: {prices}\n"
        f"    combined_path: {tmp_path / 'combined.csv'}\n"
        f"    out_dir: {tmp_path}/out/\n"
        "    report_data: report_data_qqq.json\n"
        '    price_column: "Close*"\n'
    )
    monkeypatch.setattr(returns.data, "config_path", str(cfg))
    # use_dataset mutates module globals; monkeypatch restores them after the test
    for name in ["sp500_input_path", "combined_output_path", "out_data_path", "sp500_index",
                 "combined_sp500_index"]:
        monkeypatch.setattr(returns.data, name, getattr(returns.data, name))
    return tmp_path, prices


def test_use_dataset_sets_paths(dataset_config):
    tmp_path, prices = dataset_config
    returns.data.use_dataset("qqq")
    assert returns.data.sp500_input_path == str(prices)
    assert returns.data.combined_output_path == str(tmp_path / "combined.csv")
    assert returns.data.out_data_path == f"{tmp_path}/out/"


def test_use_dataset_selects_price_column(dataset_config, interest_file, monkeypatch):
    monkeypatch.setattr(returns.data, "interest_input_path", str(interest_file))
    returns.data.use_dataset("qqq")
    assert returns.data.combined_sp500_index == 4
    data, _ = get_combined_sp500_interest_data()
    assert data[0][returns.data.combined_sp500_index] == pytest.approx(102.0)


def test_create_combined_data_file_writes_dataset_path(dataset_config, interest_file, monkeypatch):
    tmp_path, _ = dataset_config
    monkeypatch.setattr(returns.data, "interest_input_path", str(interest_file))
    returns.data.use_dataset("qqq")
    returns.data.create_combined_data_file()
    lines = (tmp_path / "combined.csv").read_text().splitlines()
    assert lines[0] == "Date,Open,High,Low,Close*,Adj Close**,Volume,GS1"
    assert len(lines) == 2
