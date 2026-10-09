import datetime
from pathlib import Path

import pytest
import yaml

from returns.config import DEFAULT_CONFIG_PATH, load_config
from returns.errors import DatasetConfigError
from returns.logging_setup import configure_logging
from tests.conftest import SETTINGS_YAML

DATASET = """  d:
    price_path: data/p.tab
    combined_path: c.csv
    out_dir: out/
    report_data: r.json
    price_column: Close
    label: D
    recent_source: file
    recent_symbol: D
    recent_data: rr.json
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(text)
    return path


def test_relative_paths_resolve_against_config_dir(tmp_path: Path) -> None:
    config = load_config(write(tmp_path, "datasets:\n" + DATASET + SETTINGS_YAML))
    assert config.dataset("d").price_path == tmp_path / "data" / "p.tab"
    assert config.sources.interest_path == tmp_path / "data" / "interest.tab"
    assert config.report.output_dir == tmp_path / "trading_strategies_report" / "data"


def test_repo_config_has_original_calibration() -> None:
    config = load_config()
    assert DEFAULT_CONFIG_PATH.name == "config.yaml"
    assert list(config.backtest.years) == list(range(1, 16))
    assert config.backtest.stride_days == 3
    assert config.backtest.skip_padding == datetime.timedelta(days=6)
    assert config.models.insurance.loss_window_days == 6
    assert [p.window for p in config.recent_returns.periods] == [1, 5, 21]
    assert set(config.datasets) == {"sp500", "qqq"}


@pytest.mark.parametrize(
    "section",
    [
        "backtest",
        "models",
        "recent_returns",
        "report",
        "monthly_returns",
        "sources",
        "insurance_scan",
    ],
)
def test_every_section_is_required(tmp_path: Path, section: str) -> None:
    # no code defaults: leaving a section out of config.yaml is an error
    settings = yaml.safe_load(SETTINGS_YAML)
    del settings[section]
    text = "datasets:\n" + DATASET + yaml.safe_dump(settings)
    with pytest.raises(DatasetConfigError, match=f"{section}\n  Field required"):
        load_config(write(tmp_path, text))


def test_skip_padding_is_padding_strides_times_stride(tmp_path: Path) -> None:
    text = SETTINGS_YAML.replace("stride_days: 3", "stride_days: 5").replace(
        "padding_strides: 2", "padding_strides: 3"
    )
    config = load_config(write(tmp_path, "datasets:\n" + DATASET + text))
    assert config.backtest.skip_padding == datetime.timedelta(days=15)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(DatasetConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")


def test_unknown_key_raises(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text("datasets: {}\nbacktest:\n  strid_days: 3\n")
    with pytest.raises(DatasetConfigError, match="strid_days"):
        load_config(tmp_path / "config.yaml")


def test_bad_recent_source_raises(tmp_path: Path) -> None:
    text = (
        "datasets:\n"
        + DATASET.replace("recent_source: file", "recent_source: web")
        + SETTINGS_YAML
    )
    (tmp_path / "config.yaml").write_text(text)
    with pytest.raises(DatasetConfigError, match="recent_source"):
        load_config(tmp_path / "config.yaml")


def test_configure_logging_overrides_level_and_handlers() -> None:
    import logging

    configure_logging("WARNING", ["console"])
    root = logging.getLogger()
    assert root.level == logging.WARNING
    assert [type(h).__name__ for h in root.handlers] == ["StreamHandler"]
