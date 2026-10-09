"""Insurance parameter sweep vs Kelly / Buy & Hold (see docs/insurance_parameter_scan.md).

Grids come from config.yaml: Kelly variants from ``models.kelly``, horizons and the
screen grid from ``insurance_scan``, and every parameter a variant doesn't set from
``backtest`` / ``models.insurance``. Result ``kwargs`` record only the variant's own
parameters.

Usage:
    poetry run python notebooks/insurance_scan/sweep.py screen <dataset> <stride_days> <out.json>
    poetry run python notebooks/insurance_scan/sweep.py <variants.json> <dataset> <stride_days> <out.json>
"""

import itertools
import json
import multiprocessing as mp
import sys
from pathlib import Path
from typing import Any

from returns.analysis import aggregate_returns
from returns.config import load_config
from returns.data import get_combined_data, load_dataset
from returns.models import InsuranceModel, KellyModel, Model
from tests.conftest import load_bin_module

runner = load_bin_module("runner")
CONFIG = load_config()
_DATA: dict[str, Any] = {}


def model_kwargs(cls: str, variant: dict[str, Any]) -> dict[str, Any]:
    """Full constructor kwargs: config.yaml calibration overridden by the variant."""
    common = {
        "capital": CONFIG.backtest.initial_capital,
        "skip_padding": CONFIG.backtest.skip_padding,
    }
    if cls != "InsuranceModel":
        return common | variant
    insurance = CONFIG.models.insurance
    return (
        common
        | {
            "insurance_period": insurance.period_days,
            "premium_rate": insurance.premium_rate,
            "coverage_ratio": insurance.coverage_ratio,
            "loss_window_days": insurance.loss_window_days,
        }
        | variant
    )


def data(ds: str) -> Any:
    if ds not in _DATA:
        dataset = load_dataset(ds, CONFIG)
        rows, _ = get_combined_data(dataset)
        _DATA[ds] = (rows, dataset.price_index, dataset.interest_index)
    return _DATA[ds]


def run(task: tuple[str, str, dict[str, Any], int, int]) -> dict[str, Any]:
    ds, cls, kwargs, years, stride = task
    rows, pi, ii = data(ds)
    model = {
        "Model": Model,
        "KellyModel": KellyModel,
        "InsuranceModel": InsuranceModel,
    }[cls](**model_kwargs(cls, kwargs))
    rets = runner.model_tester(model, rows, pi, ii, years=years, stride_days=stride)
    stats, _ = aggregate_returns(rets, CONFIG.backtest.histogram_bins)
    return {
        "ds": ds,
        "cls": cls,
        "kwargs": kwargs,
        "years": years,
        "mean_yearly": stats.mean_yearly_compound_returns,
        "median_yearly": stats.median_yearly_returns,
        "losing": stats.fraction_losing_starts,
        "n": stats.sample_size,
    }


if __name__ == "__main__":
    mode, ds, stride, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
    horizons = CONFIG.insurance_scan.horizons
    kelly = CONFIG.models.kelly
    tasks = [(ds, "Model", {}, y, stride) for y in horizons]
    tasks += [
        (ds, "KellyModel", {"bond_frac": b, "rebalance_period": r}, y, stride)
        for b in sorted(kelly.bond_fracs)
        for r in kelly.rebalance_days
        for y in horizons
    ]
    if mode == "screen":
        screen = CONFIG.insurance_scan.screen
        grid = itertools.product(
            screen.premium_rates, screen.deductibles, screen.coverage_ratios
        )
        ins = [
            {
                "insurance_frac": screen.insurance_frac,
                "premium_rate": p,
                "insurance_deductible": d,
                "coverage_ratio": c,
            }
            for p, d, c in grid
        ]
    else:
        ins = json.loads(Path(mode).read_text())
    tasks += [(ds, "InsuranceModel", k, y, stride) for k in ins for y in horizons]
    # longest tasks first for better packing
    tasks.sort(key=lambda t: (t[1] != "InsuranceModel", -t[3]))
    with mp.Pool() as pool:
        results = pool.map(run, tasks, chunksize=1)
    Path(out).write_text(json.dumps(results))
    print(f"wrote {len(results)} results to {out}")
