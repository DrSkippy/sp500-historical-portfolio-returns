"""The insurance-scan scripts' mapping between result-JSON kwargs and model specs."""

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from returns.backtest import BuyHoldSpec, InsuranceSpec, KellySpec
from returns.config import AppConfig

SCAN_DIR = Path(__file__).parent.parent / "notebooks" / "insurance_scan"


def load_scan_module(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCAN_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sweep = load_scan_module("sweep")
analyze = load_scan_module("analyze")


def test_variant_spec_maps_recorded_kwargs(synthetic_config: AppConfig) -> None:
    assert sweep.variant_spec("Model", {}, synthetic_config) == BuyHoldSpec()
    assert sweep.variant_spec(
        "KellyModel", {"bond_frac": 0.2, "rebalance_period": 180}, synthetic_config
    ) == KellySpec(bond_frac=0.2, rebalance_days=180)
    spec = sweep.variant_spec(
        "InsuranceModel",
        {
            "insurance_frac": 0.05,
            "premium_rate": 0.004,
            "insurance_deductible": 0.12,
            "coverage_ratio": 2.0,
        },
        synthetic_config,
    )
    assert isinstance(spec, InsuranceSpec)
    assert (spec.insurance_frac, spec.deductible) == (0.05, 0.12)
    assert (spec.policy.premium_rate, spec.policy.coverage_ratio) == (0.004, 2.0)
    # not in the variant: from models.insurance
    assert spec.policy.loss_window_days == 6 and spec.policy.period_days == 90


def test_variant_spec_unknown_family_raises(synthetic_config: AppConfig) -> None:
    with pytest.raises(ValueError, match="Mystery"):
        sweep.variant_spec("Mystery", {}, synthetic_config)


def test_sweep_tasks_cover_every_variant_and_horizon(
    synthetic_config: AppConfig,
) -> None:
    variants = sweep.screen_variants(synthetic_config)
    assert len(variants) == 2 * 2 * 1  # premium_rates x deductibles x coverage
    tasks = sweep.sweep_tasks("synthetic", 9, variants, synthetic_config)
    horizons = synthetic_config.insurance_scan.horizons
    assert len(tasks) == (1 + 8 + len(variants)) * len(horizons)
    assert tasks[0].family == "InsuranceModel" and tasks[0].years == max(horizons)


def test_analyze_ranks_insurance_against_best_kelly(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def result(
        cls: str, kwargs: dict[str, float], years: int, mean: float
    ) -> dict[str, Any]:
        return {
            "cls": cls,
            "kwargs": kwargs,
            "years": years,
            "mean_yearly": mean,
            "losing": 0.1,
        }

    ins = {"premium_rate": 0.004, "insurance_deductible": 0.12, "coverage_ratio": 1.0}
    results = [
        result(cls, kwargs, y, mean)
        for y in (1, 5)
        for cls, kwargs, mean in [
            ("Model", {}, 0.10),
            ("KellyModel", {"bond_frac": 0.2, "rebalance_period": 90}, 0.08),
            ("InsuranceModel", ins, 0.09),
        ]
    ]
    analyze.print_ranking(analyze.results_by_variant(results), [1, 5], top_n=5)
    out = capsys.readouterr().out
    assert "Ins prem=0.0040 ded=0.12 cov=1.0" in out
    assert "+1.00pt" in out and "BEATS" in out
    assert "1 of 1 variants beat the best Kelly at every horizon" in out
