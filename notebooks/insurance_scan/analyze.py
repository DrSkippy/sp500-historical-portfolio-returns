"""Rank sweep results against the best Kelly variant at every horizon.

Horizons are ``insurance_scan.horizons`` in config.yaml.

Usage:
    python notebooks/insurance_scan/analyze.py <results.json> [top_n]
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from returns.config import load_config

DEFAULT_TOP_N = 30
BUY_HOLD_KEY = "Buy_Hold"
KELLY_KEY_PREFIX = "Kelly"
INSURANCE_KEY_PREFIX = "Ins"
PERCENT = 100

Result = dict[str, Any]
"""One record written by sweep.py."""


def variant_key(result: Result) -> str:
    """Display label for a result's model variant."""
    kwargs = result["kwargs"]
    if result["cls"] == "Model":
        return BUY_HOLD_KEY
    if result["cls"] == "KellyModel":
        return f"{KELLY_KEY_PREFIX} {kwargs['bond_frac']}/{kwargs['rebalance_period']}"
    return (
        f"{INSURANCE_KEY_PREFIX} prem={kwargs['premium_rate']:.4f}"
        f" ded={kwargs['insurance_deductible']:.2f} cov={kwargs['coverage_ratio']}"
    )


def results_by_variant(results: list[Result]) -> dict[str, dict[int, Result]]:
    """Results keyed by variant label, then by horizon (years)."""
    by_variant: dict[str, dict[int, Result]] = defaultdict(dict)
    for result in results:
        by_variant[variant_key(result)][result["years"]] = result
    return by_variant


def print_ranking(
    by_variant: dict[str, dict[int, Result]], horizons: list[int], top_n: int
) -> None:
    """Print the Kelly / Buy & Hold baseline, then insurance variants ranked by
    their worst-horizon margin over the best Kelly mean return."""
    kelly = [key for key in by_variant if key.startswith(KELLY_KEY_PREFIX)]
    best_kelly_mean = {
        y: max(by_variant[key][y]["mean_yearly"] for key in kelly) for y in horizons
    }
    min_kelly_losing = {
        y: min(by_variant[key][y]["losing"] for key in kelly) for y in horizons
    }
    buy_hold = by_variant[BUY_HOLD_KEY]
    print("horizon:            " + "".join(f"{y:>16}y" for y in horizons))
    print(
        "best Kelly mean:    "
        + "".join(f"{best_kelly_mean[y] * PERCENT:16.2f}%" for y in horizons)
    )
    print(
        "Buy&Hold mean:      "
        + "".join(f"{buy_hold[y]['mean_yearly'] * PERCENT:16.2f}%" for y in horizons)
    )
    print(
        "min Kelly losing:   "
        + "".join(f"{min_kelly_losing[y] * PERCENT:16.1f}%" for y in horizons)
    )
    print(
        "Buy&Hold losing:    "
        + "".join(f"{buy_hold[y]['losing'] * PERCENT:16.1f}%" for y in horizons)
    )
    insurance = [key for key in by_variant if key.startswith(INSURANCE_KEY_PREFIX)]

    def margin(key: str) -> float:
        return float(
            min(
                by_variant[key][y]["mean_yearly"] - best_kelly_mean[y] for y in horizons
            )
        )

    ranked = sorted(insurance, key=margin, reverse=True)
    horizon_list = ",".join(str(y) for y in horizons)
    print(
        f"\n{'variant':42}{'min margin vs best Kelly':>26}"
        f"   mean/losing at {horizon_list}y"
    )
    for key in ranked[:top_n]:
        cells = "  ".join(
            f"{by_variant[key][y]['mean_yearly'] * PERCENT:5.2f}"
            f"/{by_variant[key][y]['losing'] * PERCENT:4.1f}"
            for y in horizons
        )
        flag = "BEATS" if margin(key) > 0 else ""
        print(f"{key:42}{margin(key) * PERCENT:+24.2f}pt  {cells} {flag}")
    beats = sum(margin(key) > 0 for key in insurance)
    print(
        f"\n{beats} of {len(insurance)} variants beat the best Kelly at every horizon"
    )


def main() -> None:
    """Load a sweep result file and print the ranking."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path, help="JSON written by sweep.py")
    parser.add_argument("top_n", type=int, nargs="?", default=DEFAULT_TOP_N)
    args = parser.parse_args()
    results: list[Result] = json.loads(args.results.read_text())
    horizons = load_config().insurance_scan.horizons
    print_ranking(results_by_variant(results), horizons, args.top_n)


if __name__ == "__main__":
    main()
