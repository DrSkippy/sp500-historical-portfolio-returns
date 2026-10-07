"""Insurance parameter sweep vs Kelly / Buy & Hold (see docs/insurance_parameter_scan.md).

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
_DATA: dict[str, Any] = {}


def data(ds: str) -> Any:
    if ds not in _DATA:
        dataset = load_dataset(ds, load_config())
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
    }[cls](**kwargs)
    rets = runner.model_tester(model, rows, pi, ii, years=years, stride_days=stride)
    stats, _ = aggregate_returns(rets)
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
    horizons = [1, 5, 10, 15]
    tasks = [(ds, "Model", {}, y, stride) for y in horizons]
    tasks += [
        (ds, "KellyModel", {"bond_frac": b, "rebalance_period": r}, y, stride)
        for b in (0.1, 0.15, 0.2, 0.25)
        for r in (90, 180)
        for y in horizons
    ]
    if mode == "screen":
        grid = itertools.product(
            (0.0, 0.0025, 0.005, 0.0075, 0.01, 0.012),
            (0.05, 0.07, 0.09, 0.12),
            (0.5, 1.0, 2.0),
        )
        ins = [
            {
                "insurance_frac": 0.05,
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
