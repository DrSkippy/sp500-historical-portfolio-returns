"""Typed application configuration loaded from config.yaml.

Relative paths in the file are resolved against the directory containing it, so
scripts behave the same whatever directory they are run from.
"""

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from returns.errors import DatasetConfigError

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


class _Strict(BaseModel):
    """Base for config sections: unknown keys are errors, instances are immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class DatasetConfig(_Strict):
    """One price dataset (S&P 500, QQQ, ...)."""

    price_path: Path
    combined_path: Path
    out_dir: Path
    report_data: str
    price_column: str
    label: str
    recent_source: Literal["db", "file"]
    recent_symbol: str
    recent_data: str


class BacktestConfig(_Strict):
    """Backtest sampling and aggregation parameters."""

    stride_days: int = 3
    """Days between successive window start dates."""
    padding_strides: int = 2
    """Skip-ahead padding before a scheduled trade, in strides."""
    initial_capital: float = 10000
    min_years: int = 1
    max_years: int = 15
    histogram_bins: int = 45

    @property
    def years(self) -> range:
        """Window lengths (in years) to backtest, inclusive of max_years."""
        return range(self.min_years, self.max_years + 1)


class KellyGridConfig(_Strict):
    """Fractional-Kelly variants: the cross product of the two lists."""

    bond_fracs: list[float] = [0.1, 0.2, 0.25, 0.15]
    rebalance_days: list[int] = [90, 180]


class InsuranceGridConfig(_Strict):
    """Insurance variants (cross product of fracs x deductibles) and shared parameters."""

    fracs: list[float] = [0.05, 0.1]
    deductibles: list[float] = [0.09, 0.12, 0.18]
    period_days: int = 90
    premium_rate: float = 0.012
    """Annual premium as a fraction of the insured stock value."""
    coverage_ratio: float = 1.0
    """Fraction of the loss beyond the deductible that the policy pays."""
    loss_window_days: int = 6


class ModelsConfig(_Strict):
    """Model grid for the full backtest run."""

    kelly: KellyGridConfig = KellyGridConfig()
    insurance: InsuranceGridConfig = InsuranceGridConfig()


class RecentPeriodConfig(_Strict):
    """One return horizon in the recent-returns report."""

    name: str
    window: int
    """Lookback in trading days."""
    recent: int
    """Number of non-overlapping recent periods to report."""


class RecentReturnsConfig(_Strict):
    """Horizons for bin/generate_recent_returns.py."""

    periods: list[RecentPeriodConfig] = [
        RecentPeriodConfig(name="daily", window=1, recent=30),
        RecentPeriodConfig(name="weekly", window=5, recent=10),
        RecentPeriodConfig(name="monthly", window=21, recent=4),
    ]


class ReportConfig(_Strict):
    """Report site output."""

    output_dir: Path = Path("trading_strategies_report/data")
    dist_years: list[int] = [1, 5, 10, 15]
    """Window lengths whose full return distributions go into the report JSON."""


class MonthlyReturnsConfig(_Strict):
    """bin/get_monthly_returns.py parameters."""

    offset_days: int = 30
    histogram_bins: int = 60
    output_path: Path = Path("out_data/monthly_returns.csv")


class SourcesConfig(_Strict):
    """External data sources."""

    interest_path: Path = Path("data/interest.tab")
    db_namespace: str = "NASDAQ"


class AppConfig(_Strict):
    """Root of config.yaml."""

    datasets: dict[str, DatasetConfig]
    backtest: BacktestConfig = BacktestConfig()
    models: ModelsConfig = ModelsConfig()
    recent_returns: RecentReturnsConfig = RecentReturnsConfig()
    report: ReportConfig = ReportConfig()
    monthly_returns: MonthlyReturnsConfig = MonthlyReturnsConfig()
    sources: SourcesConfig = SourcesConfig()

    def dataset(self, name: str) -> DatasetConfig:
        """Look up a dataset by name.

        Args:
            name: Key under ``datasets`` (e.g. "sp500", "qqq").

        Returns:
            The dataset's configuration.

        Raises:
            DatasetConfigError: If no dataset has that name.
        """
        try:
            return self.datasets[name]
        except KeyError:
            known = ", ".join(sorted(self.datasets))
            raise DatasetConfigError(
                f"Unknown dataset {name!r}; config.yaml defines: {known}"
            ) from None


def _resolve_paths(node: Any, base: Path) -> Any:
    """Return a copy of a config model with every relative Path made absolute."""
    if isinstance(node, Path):
        return node if node.is_absolute() else (base / node).resolve()
    if isinstance(node, BaseModel):
        updates = {
            field: _resolve_paths(getattr(node, field), base)
            for field in type(node).model_fields
        }
        return node.model_copy(update=updates)
    if isinstance(node, dict):
        return {k: _resolve_paths(v, base) for k, v in node.items()}
    if isinstance(node, list):
        return [_resolve_paths(v, base) for v in node]
    return node


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    """Load and validate config.yaml.

    Args:
        path: Location of the YAML file.

    Returns:
        The validated configuration, with relative paths resolved against the
        file's directory.

    Raises:
        DatasetConfigError: If the file is missing or fails validation.
    """
    try:
        raw = yaml.safe_load(path.read_text())
        config = AppConfig.model_validate(raw)
    except FileNotFoundError:
        raise DatasetConfigError(f"Config file not found: {path}") from None
    except ValidationError as e:
        raise DatasetConfigError(f"Invalid config {path}:\n{e}") from e
    resolved: AppConfig = _resolve_paths(config, path.resolve().parent)
    return resolved
