import datetime
import importlib.util
import math
from pathlib import Path
from types import ModuleType

import pytest

from returns.config import AppConfig, load_config

BIN_DIR = Path(__file__).parent.parent / "bin"


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
""")
    return root / "config.yaml"


@pytest.fixture
def synthetic_config(tmp_path: Path) -> AppConfig:
    """A synthetic project (prices, interest, config.yaml) in tmp_path, loaded."""
    config = load_config(write_synthetic_project(tmp_path))
    config.datasets["synthetic"].out_dir.mkdir()
    return config
