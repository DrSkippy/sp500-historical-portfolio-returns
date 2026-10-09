"""Insurance parameter sweep vs Kelly / Buy & Hold (see docs/insurance_parameter_scan.md).

Grids come from config.yaml: Kelly variants from ``models.kelly``, horizons and the
screen grid from ``insurance_scan``, and every parameter a variant doesn't set from
``backtest`` / ``models.insurance``. Result ``kwargs`` record only the variant's own
parameters (in the original constructor-keyword spelling read by analyze.py).

Usage:
    poetry run python notebooks/insurance_scan/sweep.py screen <dataset> <stride_days> <out.json>
    poetry run python notebooks/insurance_scan/sweep.py <variants.json> <dataset> <stride_days> <out.json>
"""

import argparse
import dataclasses
import itertools
import json
import multiprocessing as mp
from pathlib import Path
from typing import Any, NamedTuple

from returns.analysis import aggregate_returns
from returns.backtest import (
    BuyHoldSpec,
    InsuranceSpec,
    KellySpec,
    ModelSpec,
    build_model,
    insurance_policy,
    model_tester,
)
from returns.config import AppConfig, load_config
from returns.prices import get_combined_data, load_dataset
from returns.types import Row

# Model family labels recorded as ``cls`` in the result JSON (read by analyze.py)
BUY_HOLD = "Model"
KELLY = "KellyModel"
INSURANCE = "InsuranceModel"
POLICY_KEYS = ("premium_rate", "coverage_ratio", "loss_window_days")

CONFIG = load_config()
_DATA_CACHE: dict[str, tuple[list[Row], int, int]] = {}


class SweepTask(NamedTuple):
    """One (dataset, variant, horizon) backtest."""

    dataset: str
    family: str
    variant: dict[str, Any]
    years: int
    stride_days: int


def dataset_rows(name: str) -> tuple[list[Row], int, int]:
    """Combined rows plus price and interest columns, loaded once per process."""
    if name not in _DATA_CACHE:
        dataset = load_dataset(name, CONFIG)
        rows, _ = get_combined_data(dataset)
        _DATA_CACHE[name] = (rows, dataset.price_index, dataset.interest_index)
    return _DATA_CACHE[name]


def variant_spec(family: str, variant: dict[str, Any], config: AppConfig) -> ModelSpec:
    """The spec for a variant; parameters it doesn't set come from config.yaml.

    Raises:
        ValueError: If ``family`` is not one of the recorded family labels.
    """
    if family == BUY_HOLD:
        return BuyHoldSpec()
    if family == KELLY:
        return KellySpec(
            bond_frac=variant["bond_frac"], rebalance_days=variant["rebalance_period"]
        )
    if family == INSURANCE:
        policy = dataclasses.replace(
            insurance_policy(config.models.insurance),
            **{key: variant[key] for key in POLICY_KEYS if key in variant},
        )
        return InsuranceSpec(
            insurance_frac=variant["insurance_frac"],
            deductible=variant["insurance_deductible"],
            policy=policy,
        )
    raise ValueError(f"unknown model family {family!r}")


def run_task(task: SweepTask) -> dict[str, Any]:
    """Backtest one task and summarize it as a result record."""
    rows, price_index, interest_index = dataset_rows(task.dataset)
    spec = variant_spec(task.family, task.variant, CONFIG)
    window_returns = model_tester(
        build_model(spec, CONFIG.backtest),
        rows,
        price_index,
        interest_index,
        years=task.years,
        stride_days=task.stride_days,
    )
    stats, _ = aggregate_returns(window_returns, CONFIG.backtest.histogram_bins)
    return {
        "ds": task.dataset,
        "cls": task.family,
        "kwargs": task.variant,
        "years": task.years,
        "mean_yearly": stats.mean_yearly_compound_returns,
        "median_yearly": stats.median_yearly_returns,
        "losing": stats.fraction_losing_starts,
        "n": stats.sample_size,
    }


def screen_variants(config: AppConfig) -> list[dict[str, Any]]:
    """The ``insurance_scan.screen`` grid as insurance variants."""
    screen = config.insurance_scan.screen
    return [
        {
            "insurance_frac": screen.insurance_frac,
            "premium_rate": premium_rate,
            "insurance_deductible": deductible,
            "coverage_ratio": coverage_ratio,
        }
        for premium_rate, deductible, coverage_ratio in itertools.product(
            screen.premium_rates, screen.deductibles, screen.coverage_ratios
        )
    ]


def sweep_tasks(
    dataset: str,
    stride_days: int,
    insurance_variants: list[dict[str, Any]],
    config: AppConfig,
) -> list[SweepTask]:
    """Buy & Hold, every Kelly variant and every insurance variant at every horizon."""
    kelly = config.models.kelly
    variants: list[tuple[str, dict[str, Any]]] = [(BUY_HOLD, {})]
    variants += [
        (KELLY, {"bond_frac": bond_frac, "rebalance_period": rebalance_days})
        for bond_frac in sorted(kelly.bond_fracs)
        for rebalance_days in kelly.rebalance_days
    ]
    variants += [(INSURANCE, variant) for variant in insurance_variants]
    tasks = [
        SweepTask(dataset, family, variant, years, stride_days)
        for family, variant in variants
        for years in config.insurance_scan.horizons
    ]
    # longest tasks first for better packing
    tasks.sort(key=lambda task: (task.family != INSURANCE, -task.years))
    return tasks


def main() -> None:
    """Run the sweep on a process pool and write the result records as JSON."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "variants", help='"screen", or a JSON file of insurance variants'
    )
    parser.add_argument("dataset", help="dataset key from config.yaml")
    parser.add_argument("stride_days", type=int)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()

    insurance_variants = (
        screen_variants(CONFIG)
        if args.variants == "screen"
        else json.loads(Path(args.variants).read_text())
    )
    tasks = sweep_tasks(args.dataset, args.stride_days, insurance_variants, CONFIG)
    with mp.Pool() as pool:
        results = pool.map(run_task, tasks, chunksize=1)
    args.out.write_text(json.dumps(results))
    print(f"wrote {len(results)} results to {args.out}")


if __name__ == "__main__":
    main()
