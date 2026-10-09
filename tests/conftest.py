import dataclasses
import datetime
import importlib.util
import math
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from returns.config import AppConfig, load_config
from returns.models import BuyHoldModel, InsuranceModel, InsurancePolicy, KellyModel

BIN_DIR = Path(__file__).parent.parent / "bin"

# Every config section except ``datasets``, with values pinned for the tests (equal to
# the repo's config.yaml as of 2026-10-09, so the golden snapshot is unaffected by
# later calibration changes there). Relative paths resolve against tmp_path.
SETTINGS_YAML = """backtest:
  stride_days: 3
  padding_strides: 2
  initial_capital: 10000
  min_years: 1
  max_years: 15
  histogram_bins: 45
models:
  kelly:
    bond_fracs: [0.1, 0.2, 0.25, 0.15]
    rebalance_days: [90, 180]
  insurance:
    fracs: [0.05, 0.1]
    deductibles: [0.09, 0.12, 0.18]
    period_days: 90
    premium_rate: 0.012
    coverage_ratio: 1.0
    loss_window_days: 6
recent_returns:
  periods:
    - {name: daily, window: 1, recent: 30}
    - {name: weekly, window: 5, recent: 10}
    - {name: monthly, window: 21, recent: 4}
report:
  output_dir: ./trading_strategies_report/data
  dist_years: [1, 5, 10, 15]
monthly_returns:
  offset_days: 30
  histogram_bins: 60
  output_path: ./out_data/monthly_returns.csv
  sample_count: 20
sources:
  interest_path: ./data/interest.tab
  db_namespace: NASDAQ
  yahoo:
    chart_url: "https://example.invalid/chart/{symbol}"
    period_end: 9999999999
    timeout_seconds: 30
    user_agent: "test-agent"
insurance_scan:
  horizons: [1, 5, 10, 15]
  screen:
    insurance_frac: 0.05
    premium_rates: [0.0, 0.012]
    deductibles: [0.05, 0.12]
    coverage_ratios: [1.0]
  fair_premium:
    insurance_frac: 0.05
    premium_rate: 0.0
    coverage_ratio: 1.0
    deductibles: [0.05, 0.18]
"""

# Model parameters for unit tests (the constructor defaults before 2026-10-09, which
# the existing assertions were written against).
TEST_CAPITAL = 10000.0
TEST_SKIP_PADDING = datetime.timedelta(days=6)
KELLY_PARAMS: dict[str, Any] = {"bond_frac": 0.4, "rebalance_days": 90}
TEST_POLICY = InsurancePolicy(
    period_days=90, premium_rate=0.012, coverage_ratio=1.0, loss_window_days=6
)
INSURANCE_PARAMS: dict[str, Any] = {
    "insurance_frac": 0.10,
    "insurance_deductible": 0.15,
}
POLICY_FIELDS = set(InsurancePolicy.__dataclass_fields__)


def _with_common(params: dict[str, Any]) -> dict[str, Any]:
    return {"capital": TEST_CAPITAL, "skip_padding": TEST_SKIP_PADDING} | params


def make_buy_hold(**overrides: Any) -> BuyHoldModel:
    """A Buy & Hold model with the test parameters, overridden by ``overrides``."""
    return BuyHoldModel(**_with_common(overrides))


def make_kelly(**overrides: Any) -> KellyModel:
    """A KellyModel with the test parameters, overridden by ``overrides``."""
    return KellyModel(**_with_common(KELLY_PARAMS | overrides))


def make_insurance(**overrides: Any) -> InsuranceModel:
    """An InsuranceModel with the test parameters, overridden by ``overrides``.

    Overrides named like ``InsurancePolicy`` fields (e.g. ``loss_window_days``)
    change the policy; the rest go to the constructor.
    """
    policy_overrides = {k: v for k, v in overrides.items() if k in POLICY_FIELDS}
    model_overrides = {k: v for k, v in overrides.items() if k not in POLICY_FIELDS}
    policy = dataclasses.replace(TEST_POLICY, **policy_overrides)
    return InsuranceModel(
        **_with_common(INSURANCE_PARAMS | {"policy": policy} | model_overrides)
    )


def load_bin_module(name: str) -> ModuleType:
    """Import a script from bin/ (not a package) as a module.

    Args:
        name: Script file name without the ``.py`` extension.

    Returns:
        The executed module.
    """
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthetic_prices() -> list[tuple[datetime.datetime, float]]:
    """Five years of weekday prices: trend, swings, and two crashes to trigger payouts."""
    start = datetime.datetime(2000, 1, 3)
    rows = []
    for i in range(5 * 365):
        day = start + datetime.timedelta(days=i)
        if day.weekday() >= 5:
            continue
        price = 1500 * (1.0003**i) * (1 + 0.08 * math.sin(i / 9))
        if 400 <= i < 460:
            price *= 0.75
        if 1100 <= i < 1130:
            price *= 0.8
        rows.append((day, price))
    return rows


def write_synthetic_project(root: Path) -> Path:
    """Write price/interest files and a config.yaml in the repo's on-disk formats."""
    (root / "data").mkdir()
    lines = ["Date\tOpen\tHigh\tLow\tClose*\tAdj Close**\tVolume"]
    for day, price in reversed(synthetic_prices()):  # newest first, like SP500.tab
        p = f"{price:,.2f}"
        lines.append(f"{day:%b %d, %Y}\t{p}\t{p}\t{p}\t{p}\t{p}\t1,000,000")
    (root / "data" / "prices.tab").write_text("\n".join(lines) + "\n")
    interest = ["observation_date\tGS1"] + [
        f"{year}-01-01\t{rate}"
        for year, rate in zip(range(2000, 2005), [6.1, 3.5, 2.0, 1.2, 1.9])
    ]
    (root / "data" / "interest.tab").write_text("\n".join(interest) + "\n")
    (root / "config.yaml").write_text("""datasets:
  synthetic:
    price_path: ./data/prices.tab
    combined_path: ./data/combined.csv
    out_dir: ./out_data/
    report_data: report_data.json
    price_column: "Adj Close**"
    label: "Synthetic"
    recent_source: file
    recent_symbol: SYN
    recent_data: recent_returns_data.json
""" + SETTINGS_YAML)
    return root / "config.yaml"


@pytest.fixture
def synthetic_config(tmp_path: Path) -> AppConfig:
    """A synthetic project (prices, interest, config.yaml) in tmp_path, loaded."""
    config = load_config(write_synthetic_project(tmp_path))
    config.datasets["synthetic"].out_dir.mkdir()
    return config
