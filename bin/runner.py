"""Run the full backtest grid: every model variant x every window length.

Usage:
    poetry run python bin/runner.py [--dataset qqq] [--log-level INFO]
"""

import argparse
import csv
import logging
import multiprocessing as mp
from pathlib import Path

from returns.backtest import (
    ModelSpec,
    all_model_specs,
    build_model,
    model_tester,
    unique_model_names,
)
from returns.cli import add_dataset_argument
from returns.config import AppConfig, load_config
from returns.errors import EmptyReturnsError
from returns.logging_setup import configure_logging
from returns.models import MODEL_VERSION
from returns.naming import new_run_timestamp, returns_file_path, run_suffix
from returns.prices import get_combined_data, load_dataset
from returns.runs import RunManifest, write_run_manifest
from returns.types import RETURNS_CSV_HEADER, WindowReturn

logger = logging.getLogger(__name__)


def write_returns_csv(path: Path, rows: list[WindowReturn]) -> None:
    """Write window results with the standard returns header."""
    with path.open("w") as outfile:
        writer = csv.writer(outfile)
        writer.writerow(RETURNS_CSV_HEADER)
        writer.writerows(rows)


def model_test_worker(
    years: int,
    spec: ModelSpec,
    date_str: str,
    dataset_name: str,
    config: AppConfig,
) -> None:
    """Run one (years, model) combination and write its results to CSV.

    Loads the data itself so the pool doesn't pickle ~17K rows per task.

    Args:
        years: Window length in years.
        spec: Model variant to test.
        date_str: Run timestamp, the suffix of the output file name.
        dataset_name: Key under ``datasets`` in config.yaml.
        config: Loaded configuration.

    Raises:
        EmptyReturnsError: If the data is too short for a single window.
    """
    dataset = load_dataset(dataset_name, config)
    data, _ = get_combined_data(dataset)
    model = build_model(spec, config.backtest)
    results = model_tester(
        model,
        data,
        dataset.price_index,
        dataset.interest_index,
        years=years,
        stride_days=config.backtest.stride_days,
    )
    if not results:
        raise EmptyReturnsError(
            f"{dataset_name} data is too short for a {years}-year window"
        )

    path = returns_file_path(
        dataset.config.out_dir, years, run_suffix(model.model_name, date_str)
    )
    logger.info(f"Writing results to {path}")
    write_returns_csv(path, results)


def main() -> None:
    """Parse arguments and run every task on a process pool."""
    parser = argparse.ArgumentParser(description="Run the full backtest grid.")
    add_dataset_argument(parser)
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="log level for app1.log (DEBUG/INFO log every trade and can reach 100s of GB)",
    )
    args = parser.parse_args()
    configure_logging(args.log_level, ["file"])
    config = load_config()
    dataset = load_dataset(args.dataset, config)
    dataset.config.out_dir.mkdir(parents=True, exist_ok=True)
    date_str = new_run_timestamp()
    specs = all_model_specs(config)
    model_names = unique_model_names(specs, config.backtest)
    tasks = [
        (years, spec, date_str, args.dataset, config)
        for years in config.backtest.years
        for spec in specs
    ]
    with mp.Pool() as pool:
        pool.starmap(model_test_worker, tasks)
    # Written only once every task has succeeded: summarize.py selects runs by
    # manifest, so a crashed or interrupted run is never picked up.
    write_run_manifest(
        dataset.config.out_dir,
        RunManifest(
            timestamp=date_str,
            model_version=MODEL_VERSION,
            dataset=args.dataset,
            years=list(config.backtest.years),
            model_count=len(specs),
            model_names=model_names,
            parameters={
                "backtest": config.backtest.model_dump(mode="json"),
                "models": config.models.model_dump(mode="json"),
            },
        ),
    )
    logger.info("All model testing completed")


if __name__ == "__main__":
    main()
