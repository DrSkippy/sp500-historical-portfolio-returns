"""End-to-end golden-master test for the backtest -> summary -> report pipeline.

Runs the real pipeline over a deterministic synthetic dataset written to tmp_path and
compares a fingerprint of every output against tests/golden/pipeline_snapshot.json.
Refactors must leave the snapshot unchanged. Intentional result changes regenerate it:

    UPDATE_GOLDEN=1 poetry run pytest tests/test_golden_master.py
"""

import csv
import json
import math
import os
from pathlib import Path
from typing import Any

import pytest

from returns.config import load_config
from returns.data import (
    create_summary_file,
    get_model_run_outputs,
    load_dataset,
    returns_file_suffix,
)
from tests.conftest import (
    INSURANCE_PARAMS,
    TEST_CAPITAL,
    TEST_SKIP_PADDING,
    load_bin_module,
    write_synthetic_project,
)

runner = load_bin_module("runner")
generate_report = load_bin_module("generate_report")
generate_recent_returns = load_bin_module("generate_recent_returns")

SNAPSHOT_PATH = Path(__file__).parent / "golden" / "pipeline_snapshot.json"
DATE_STR = "2026-01-01_0000"
YEARS = [1, 2, 3]
COMMON: dict[str, Any] = {"capital": TEST_CAPITAL, "skip_padding": TEST_SKIP_PADDING}
MODEL_SPECS: list[tuple[str, dict[str, Any]]] = [
    ("Model", COMMON),
    ("KellyModel", COMMON | {"bond_frac": 0.2, "rebalance_period": 90}),
    (
        "InsuranceModel",
        COMMON
        | INSURANCE_PARAMS
        | {"insurance_frac": 0.1, "insurance_deductible": 0.09},
    ),
    (
        "InsuranceModel",
        COMMON
        | INSURANCE_PARAMS
        | {"insurance_frac": 0.05, "insurance_deductible": 0.18},
    ),
]
REL_TOL = 1e-9


def fingerprint_values(values: list[float]) -> dict[str, Any]:
    """Compact, order-sensitive summary of a long float list."""
    return {
        "n": len(values),
        "sum": math.fsum(values),
        "weighted_sum": math.fsum(i * v for i, v in enumerate(values)),
        "first": values[:3],
        "last": values[-3:],
    }


def fingerprint_returns_csv(path: Path) -> dict[str, Any]:
    """Fingerprint one returns_{years}_{model}_{date}.csv file."""
    with path.open() as f:
        rows = list(csv.reader(f))
    header, body = rows[0], rows[1:]
    return {
        "header": header,
        "first_row": body[0],
        "last_row": body[-1],
        "frac_return": fingerprint_values([float(r[1]) for r in body]),
        "yearly_return_rate": fingerprint_values([float(r[2]) for r in body]),
    }


def run_pipeline(root: Path) -> dict[str, Any]:
    """Run worker -> summary -> report -> recent returns; return output fingerprints."""
    write_synthetic_project(root)
    config = load_config(root / "config.yaml")
    out_dir = root / "out_data"
    out_dir.mkdir()

    for years in YEARS:
        for class_name, kwargs in MODEL_SPECS:
            runner.model_test_worker(
                years, class_name, kwargs, DATE_STR, "synthetic", config
            )

    returns_files = sorted(out_dir.glob("returns_*.csv"))
    for suffix in sorted({returns_file_suffix(p) for p in returns_files}):
        create_summary_file(
            *get_model_run_outputs(out_dir, suffix, years=YEARS),
            bins=config.backtest.histogram_bins,
        )
    report = generate_report.build_report_data(
        generate_report.find_latest_files(out_dir), config.report.dist_years
    )

    recent = json.loads(
        json.dumps(
            generate_recent_returns.build_output(
                load_dataset("synthetic", config), config
            )
        )
    )
    del recent["generated_at"]
    for period in ("daily", "weekly", "monthly"):
        recent[period]["values"] = fingerprint_values(recent[period]["values"])

    return {
        "returns_csv": {p.name: fingerprint_returns_csv(p) for p in returns_files},
        "report": report,
        "recent": recent,
    }


def assert_matches(actual: Any, expected: Any, path: str = "$") -> None:
    """Recursive equality with a relative tolerance on floats."""
    if isinstance(expected, float) or isinstance(actual, float):
        assert isinstance(actual, (int, float)), f"{path}: {actual!r} is not a number"
        assert math.isclose(
            actual, expected, rel_tol=REL_TOL, abs_tol=1e-12
        ), f"{path}: {actual!r} != {expected!r}"
    elif isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path}: expected a dict"
        assert actual.keys() == expected.keys(), f"{path}: keys differ"
        for key in expected:
            assert_matches(actual[key], expected[key], f"{path}.{key}")
    elif isinstance(expected, list):
        assert isinstance(actual, list), f"{path}: expected a list"
        assert len(actual) == len(expected), f"{path}: length differs"
        for i, (a, e) in enumerate(zip(actual, expected)):
            assert_matches(a, e, f"{path}[{i}]")
    else:
        assert actual == expected, f"{path}: {actual!r} != {expected!r}"


def test_pipeline_matches_golden_snapshot(tmp_path: Path) -> None:
    actual = json.loads(json.dumps(run_pipeline(tmp_path)))
    if os.environ.get("UPDATE_GOLDEN"):
        SNAPSHOT_PATH.parent.mkdir(exist_ok=True)
        SNAPSHOT_PATH.write_text(json.dumps(actual, indent=1, sort_keys=True) + "\n")
        pytest.skip("golden snapshot regenerated")
    assert_matches(actual, json.loads(SNAPSHOT_PATH.read_text()))
