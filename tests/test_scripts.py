"""Tests for the bin/ entry points, run against a synthetic project in tmp_path."""

import json
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

import pytest

from returns.config import AppConfig
from returns.data import RunManifest, find_runs, write_run_manifest
from returns.errors import DuplicateModelNameError, EmptyReturnsError
from returns.models import MODEL_VERSION
from tests.conftest import TEST_CAPITAL, TEST_SKIP_PADDING, load_bin_module

runner = load_bin_module("runner")
summarize = load_bin_module("summarize")
generate_report = load_bin_module("generate_report")
generate_recent_returns = load_bin_module("generate_recent_returns")
get_monthly_returns = load_bin_module("get_monthly_returns")


@pytest.fixture
def use_config(
    synthetic_config: AppConfig, monkeypatch: pytest.MonkeyPatch
) -> Callable[..., None]:
    """Point a script module at the synthetic config and set its argv."""

    def apply(module: Any, *args: str) -> None:
        monkeypatch.setattr(module, "load_config", lambda: synthetic_config)
        monkeypatch.setattr(
            sys, "argv", [module.__name__, "--dataset", "synthetic", *args]
        )

    return apply


class SequentialPool:
    """Stand-in for multiprocessing.Pool that runs tasks in-process."""

    def __enter__(self) -> "SequentialPool":
        return self

    def __exit__(self, *exc: object) -> None:
        pass

    def starmap(
        self, func: Callable[..., Any], tasks: Iterable[tuple[Any, ...]]
    ) -> None:
        for task in tasks:
            func(*task)


def shrink_grid(config: AppConfig) -> AppConfig:
    """Same config with a 1-2 year backtest and one variant per model family."""
    models = config.models.model_copy(
        update={
            "kelly": config.models.kelly.model_copy(
                update={"bond_fracs": [0.2], "rebalance_days": [90]}
            ),
            "insurance": config.models.insurance.model_copy(
                update={"fracs": [0.1], "deductibles": [0.09]}
            ),
        }
    )
    backtest = config.backtest.model_copy(update={"max_years": 2})
    return config.model_copy(update={"models": models, "backtest": backtest})


def test_all_model_specs_matches_original_grid(synthetic_config: AppConfig) -> None:
    specs = list(runner.all_model_specs(synthetic_config))
    assert len(specs) == 15
    assert [name for name, _ in specs] == ["Model"] + ["KellyModel"] * 8 + [
        "InsuranceModel"
    ] * 6
    assert specs[1][1]["bond_frac"] == 0.1 and specs[1][1]["rebalance_period"] == 90
    assert specs[-1][1]["insurance_frac"] == 0.1
    assert specs[-1][1]["insurance_deductible"] == 0.18
    for name, kwargs in specs:
        model = runner.MODEL_CLASSES[name](**kwargs)
        assert model.init_capital == 10000


def test_unique_model_names_accepts_the_grid(synthetic_config: AppConfig) -> None:
    names = runner.unique_model_names(list(runner.all_model_specs(synthetic_config)))
    assert len(names) == len(set(names)) == 15
    assert names[0] == "Buy_Hold" and names[-1] == "Insurance_0.1_0.18_90"


def test_unique_model_names_rejects_repeated_grid_values(
    synthetic_config: AppConfig,
) -> None:
    kelly = synthetic_config.models.kelly.model_copy(
        update={"bond_fracs": [0.2, 0.2], "rebalance_days": [90]}
    )
    config = synthetic_config.model_copy(
        update={"models": synthetic_config.models.model_copy(update={"kelly": kelly})}
    )
    with pytest.raises(DuplicateModelNameError, match="Fractional_Kelly_0.2_90"):
        runner.unique_model_names(list(runner.all_model_specs(config)))


def test_worker_raises_when_data_too_short(synthetic_config: AppConfig) -> None:
    with pytest.raises(EmptyReturnsError, match="too short"):
        runner.model_test_worker(
            10,
            "Model",
            {"capital": TEST_CAPITAL, "skip_padding": TEST_SKIP_PADDING},
            "2026-01-01_0000",
            "synthetic",
            synthetic_config,
        )


def test_backtest_summarize_report_end_to_end(
    synthetic_config: AppConfig,
    use_config: Callable[..., None],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)  # runner logs to ./app1.log
    small = shrink_grid(synthetic_config)
    monkeypatch.setattr(runner.mp, "Pool", SequentialPool)
    for module in (runner, summarize, generate_report):
        use_config(module)
        monkeypatch.setattr(module, "load_config", lambda: small)

    out_dir = small.datasets["synthetic"].out_dir
    # leftovers that summarize must ignore: an unversioned run and an old-version run
    for stamp in ("2025-01-01_0000", "2025-02-01_0000"):
        (out_dir / f"returns_1_Buy_Hold_{stamp}.csv").write_text("garbage\n")
    # ... and a summary of a model since dropped from the grid, which the report
    # must not pick up (it used to take the newest summary per model name)
    (out_dir / "summary_Insurance_0.1_0.15_90_2025-02-01_0000.csv").write_text("x\n")
    (out_dir / "total_returns_Insurance_0.1_0.15_90_2025-02-01_0000.json").write_text(
        "{}"
    )
    write_run_manifest(
        out_dir,
        RunManifest(
            timestamp="2025-02-01_0000",
            model_version=MODEL_VERSION - 1,
            dataset="synthetic",
            years=[1],
            model_count=1,
        ),
    )

    runner.main()
    manifests = [m for m in find_runs(out_dir) if m.model_version == MODEL_VERSION]
    assert len(manifests) == 1
    assert manifests[0].years == [1, 2] and manifests[0].model_count == 3
    assert manifests[0].model_names == [
        "Buy_Hold",
        "Fractional_Kelly_0.2_90",
        "Insurance_0.1_0.09_90",
    ]
    insurance = manifests[0].parameters["models"]["insurance"]
    assert insurance["premium_rate"] == 0.012
    assert insurance["loss_window_days"] == 6
    assert manifests[0].parameters["backtest"]["stride_days"] == 3
    assert len(list(out_dir.glob(f"returns_*_{manifests[0].timestamp}.csv"))) == 3 * 2

    summarize.main()
    assert len(list(out_dir.glob(f"summary_*_{manifests[0].timestamp}.csv"))) == 3
    assert not list(out_dir.glob("summary_Buy_Hold_2025-*"))
    assert (tmp_path / "data" / "combined.csv").exists()

    generate_report.main()
    report = json.loads((small.report.output_dir / "report_data.json").read_text())
    assert [m["family"] for m in report["models"]] == ["buy_hold", "kelly", "insurance"]
    assert [m["name"] for m in report["models"]] == manifests[0].model_names
    assert [row["year"] for row in report["models"][0]["summary"]] == [1, 2]
    assert set(report["models"][0]["distributions"]) == {"1"}


def test_runner_writes_no_manifest_when_a_task_fails(
    synthetic_config: AppConfig,
    use_config: Callable[..., None],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    use_config(runner)
    monkeypatch.setattr(runner, "load_config", lambda: shrink_grid(synthetic_config))
    monkeypatch.setattr(runner.mp, "Pool", SequentialPool)

    def failing_worker(*args: Any) -> None:
        raise EmptyReturnsError("boom")

    monkeypatch.setattr(runner, "model_test_worker", failing_worker)
    with pytest.raises(EmptyReturnsError):
        runner.main()
    assert find_runs(synthetic_config.datasets["synthetic"].out_dir) == []


def test_generate_report_reports_the_requested_run(
    synthetic_config: AppConfig,
    use_config: Callable[..., None],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    small = shrink_grid(synthetic_config)
    monkeypatch.setattr(runner.mp, "Pool", SequentialPool)
    out_dir = small.datasets["synthetic"].out_dir
    stamps = iter(["2026-01-01_0000", "2026-02-01_0000"])
    monkeypatch.setattr(runner, "new_run_timestamp", lambda: next(stamps))
    for module in (runner, summarize, generate_report):
        use_config(module)
        monkeypatch.setattr(module, "load_config", lambda: small)
    for _ in range(2):
        runner.main()
    for stamp in ("2026-01-01_0000", "2026-02-01_0000"):
        use_config(summarize, "--run", stamp)
        summarize.main()

    report_path = small.report.output_dir / "report_data.json"
    use_config(generate_report, "--run", "2026-01-01_0000")
    monkeypatch.setattr(generate_report, "load_config", lambda: small)
    generate_report.main()
    assert len(json.loads(report_path.read_text())["models"]) == 3
    # remove one model's summary from the newest run: the default (newest) run is
    # now incomplete, so the report refuses rather than mixing in older files
    (out_dir / "summary_Buy_Hold_2026-02-01_0000.csv").unlink()
    use_config(generate_report)
    monkeypatch.setattr(generate_report, "load_config", lambda: small)
    with pytest.raises(SystemExit) as exc:
        generate_report.main()
    assert exc.value.code == 1


def test_summarize_exits_when_no_current_version_run(
    use_config: Callable[..., None],
) -> None:
    use_config(summarize)
    with pytest.raises(SystemExit) as exc:
        summarize.main()
    assert exc.value.code == 1


def test_generate_report_main_exits_when_no_outputs(
    use_config: Callable[..., None],
) -> None:
    use_config(generate_report)
    with pytest.raises(SystemExit) as exc:
        generate_report.main()
    assert exc.value.code == 1


def test_generate_recent_returns_main_writes_json(
    synthetic_config: AppConfig, use_config: Callable[..., None]
) -> None:
    use_config(generate_recent_returns)
    generate_recent_returns.main()
    path = synthetic_config.report.output_dir / "recent_returns_data.json"
    output = json.loads(path.read_text())
    assert output["symbol"] == "SYN"
    assert output["history_start"] == 2000
    assert [len(output[p]["recent"]) for p in ("daily", "weekly", "monthly")] == [
        30,
        10,
        4,
    ]


def test_generate_recent_returns_reads_db_quotes(
    synthetic_config: AppConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset_config = synthetic_config.datasets["synthetic"].model_copy(
        update={"recent_source": "db"}
    )
    config = synthetic_config.model_copy(
        update={"datasets": {"synthetic": dataset_config}}
    )
    calls: list[tuple[str, str]] = []

    def fake_get_quotes(symbol: str, namespace: str) -> list[tuple[str, float]]:
        calls.append((symbol, namespace))
        return [("2026-01-01", 100.0), ("2026-01-02", 110.0)]

    monkeypatch.setattr(
        generate_recent_returns,
        "get_db_settings",
        lambda: {"host": "h", "port": 1, "dbname": "d"},
    )
    monkeypatch.setattr(generate_recent_returns, "get_quotes", fake_get_quotes)
    dataset = generate_recent_returns.load_dataset("synthetic", config)
    output = generate_recent_returns.build_output(dataset, config)
    assert calls == [("SYN", "NASDAQ")]
    assert output["latest_spy_date"] == "2026-01-02"
    assert output["latest_spy_close"] == 110.0
    assert output["daily"]["recent"][0]["value"] == pytest.approx(0.1)


def test_get_monthly_returns_main_writes_csv(
    synthetic_config: AppConfig,
    use_config: Callable[..., None],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = synthetic_config.monthly_returns.model_copy(
        update={"output_path": tmp_path / "monthly.csv"}
    )
    config = synthetic_config.model_copy(update={"monthly_returns": settings})
    use_config(get_monthly_returns, "--no-plot")
    monkeypatch.setattr(get_monthly_returns, "load_config", lambda: config)
    get_monthly_returns.main()
    lines = (tmp_path / "monthly.csv").read_text().splitlines()
    assert (
        len(lines)
        == 1
        + len(
            get_monthly_returns.get_combined_data(
                get_monthly_returns.load_dataset("synthetic", config)
            )[0]
        )
        - 30
    )
