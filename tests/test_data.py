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
