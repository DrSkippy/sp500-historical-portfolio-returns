"""Typed application configuration loaded from config.yaml.

config.yaml is the single source of truth for calibration: every field is required
(no code defaults that could silently drift from the file). Relative paths in the
file are resolved against the directory containing it, so scripts behave the same
whatever directory they are run from.
"""

import datetime
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

    stride_days: int
    """Days between successive window start dates."""
    padding_strides: int
    """Skip-ahead padding before a scheduled trade, in strides."""
    initial_capital: float
    min_years: int
    max_years: int
    histogram_bins: int

    @property
    def years(self) -> range:
        """Window lengths (in years) to backtest, inclusive of max_years."""
        return range(self.min_years, self.max_years + 1)

    @property
    def skip_padding(self) -> datetime.timedelta:
        """Skip-ahead padding implied by the stride: ``padding_strides`` strides."""
        return datetime.timedelta(days=self.padding_strides * self.stride_days)


class KellyGridConfig(_Strict):
    """Fractional-Kelly variants: the cross product of the two lists."""

    bond_fracs: list[float]
    rebalance_days: list[int]


class InsuranceGridConfig(_Strict):
    """Insurance variants (cross product of fracs x deductibles) and shared parameters."""

    fracs: list[float]
    deductibles: list[float]
    period_days: int
    premium_rate: float
    """Annual premium as a fraction of the insured stock value."""
    coverage_ratio: float
    """Fraction of the loss beyond the deductible that the policy pays."""
    loss_window_days: int


class ModelsConfig(_Strict):
    """Model grid for the full backtest run."""

    kelly: KellyGridConfig
    insurance: InsuranceGridConfig


class RecentPeriodConfig(_Strict):
    """One return horizon in the recent-returns report."""

    name: str
    window: int
    """Lookback in trading days."""
    recent: int
    """Number of non-overlapping recent periods to report."""


class RecentReturnsConfig(_Strict):
    """Horizons for bin/generate_recent_returns.py."""

    periods: list[RecentPeriodConfig]


class ReportConfig(_Strict):
    """Report site output."""

    output_dir: Path
    dist_years: list[int]
    """Window lengths whose full return distributions go into the report JSON."""


class MonthlyReturnsConfig(_Strict):
    """bin/get_monthly_returns.py parameters."""

    offset_days: int
    histogram_bins: int
    output_path: Path
    sample_count: int
    """Number of random sample returns logged by the script."""


class YahooConfig(_Strict):
    """Yahoo Finance chart API used by bin/download_qqq.py."""

    chart_url: str
    """URL template with a ``{symbol}`` placeholder."""
    period_end: int
    """``period2`` epoch seconds; far in the future to fetch the full history."""
    timeout_seconds: float
    user_agent: str


class SourcesConfig(_Strict):
    """External data sources."""

    interest_path: Path
    db_namespace: str
    yahoo: YahooConfig


class FairPremiumConfig(_Strict):
    """notebooks/insurance_scan/fair_premium.py scenario: one continuous policy."""

    insurance_frac: float
    premium_rate: float
    coverage_ratio: float
    deductibles: list[float]


class ScreenGridConfig(_Strict):
    """notebooks/insurance_scan/sweep.py ``screen`` grid (cross product)."""

    insurance_frac: float
    premium_rates: list[float]
    deductibles: list[float]
    coverage_ratios: list[float]


class InsuranceScanConfig(_Strict):
    """Insurance parameter scan (notebooks/insurance_scan, docs/insurance_parameter_scan.md)."""

    horizons: list[int]
    """Window lengths (years) compared in the scan."""
    screen: ScreenGridConfig
    fair_premium: FairPremiumConfig


class AppConfig(_Strict):
    """Root of config.yaml."""

    datasets: dict[str, DatasetConfig]
    backtest: BacktestConfig
    models: ModelsConfig
    recent_returns: RecentReturnsConfig
    report: ReportConfig
    monthly_returns: MonthlyReturnsConfig
    sources: SourcesConfig
    insurance_scan: InsuranceScanConfig

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
