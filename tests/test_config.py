from pathlib import Path

import pytest

from returns.config import DEFAULT_CONFIG_PATH, AppConfig, load_config
from returns.errors import DatasetConfigError
from returns.logging_setup import configure_logging

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


def test_relative_paths_resolve_against_config_dir(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text("datasets:\n" + DATASET)
    config = load_config(tmp_path / "config.yaml")
    assert config.dataset("d").price_path == tmp_path / "data" / "p.tab"
    assert config.sources.interest_path == tmp_path / "data" / "interest.tab"
    assert config.report.output_dir == tmp_path / "trading_strategies_report" / "data"


def test_defaults_match_original_calibration(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text("datasets:\n" + DATASET)
    config = load_config(tmp_path / "config.yaml")
    assert list(config.backtest.years) == list(range(1, 16))
    assert config.backtest.stride_days == 3
    assert config.models.insurance.loss_window_days == 6
    assert [p.window for p in config.recent_returns.periods] == [1, 5, 21]


def test_repo_config_values_equal_code_defaults() -> None:
    config = load_config()
    defaults = AppConfig(datasets=config.datasets)
    sections = ["backtest", "models", "recent_returns"]
    assert config.model_dump(include=set(sections)) == defaults.model_dump(
        include=set(sections)
    )
    assert DEFAULT_CONFIG_PATH.name == "config.yaml"


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(DatasetConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")


def test_unknown_key_raises(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text("datasets: {}\nbacktest:\n  strid_days: 3\n")
    with pytest.raises(DatasetConfigError, match="strid_days"):
        load_config(tmp_path / "config.yaml")


def test_bad_recent_source_raises(tmp_path: Path) -> None:
    text = "datasets:\n" + DATASET.replace("recent_source: file", "recent_source: web")
    (tmp_path / "config.yaml").write_text(text)
    with pytest.raises(DatasetConfigError, match="recent_source"):
        load_config(tmp_path / "config.yaml")


def test_configure_logging_overrides_level_and_handlers() -> None:
    import logging

    configure_logging("WARNING", ["console"])
    root = logging.getLogger()
    assert root.level == logging.WARNING
    assert [type(h).__name__ for h in root.handlers] == ["StreamHandler"]
