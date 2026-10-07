"""Run the full backtest grid: every model variant x every window length.

Usage:
    poetry run python bin/runner.py [--dataset qqq] [--log-level INFO]
"""

import argparse
import bisect
import csv
import datetime
import logging
import multiprocessing as mp
from pathlib import Path
from typing import Any, Iterator

from returns.config import AppConfig, BacktestConfig, load_config
from returns.data import Row, get_combined_data, load_dataset, returns_file_path
from returns.errors import EmptyReturnsError
from returns.logging_setup import configure_logging
from returns.models import (
    STRIDE_DAYS,
    InsuranceModel,
    KellyModel,
    Model,
    years_to_timedelta,
)
from returns.types import RETURNS_CSV_HEADER, PriceBar, WindowReturn

logger = logging.getLogger(__name__)

MODEL_CLASSES: dict[str, type[Model]] = {
    "Model": Model,
    "KellyModel": KellyModel,
    "InsuranceModel": InsuranceModel,
}


def model_tester(
    model: Model,
    data: list[Row],
    price_index: int,
    interest_index: int,
    years: int = 10,
    stride_days: int = STRIDE_DAYS,
) -> list[WindowReturn]:
    """Backtest a model over every window of ``years`` length in the data.

    Window start dates step forward by ``stride_days`` from the first date.

    Args:
        model: Strategy to test; reconfigured for each window.
        data: Combined rows sorted by date.
        price_index: Column of the traded price in each row.
        interest_index: Column of the annual interest rate in each row.
        years: Window length in years.
        stride_days: Days between successive window start dates.

    Returns:
        One result per window.
    """
    test_interval = datetime.timedelta(days=stride_days)
    test_start_date = data[0][0]  # first (oldest) date in data
    model_returns: list[WindowReturn] = []

    logger.info("Starting model testing")

    # Pre-compute date list once for bisect lookups
    dates = [row[0] for row in data]

    while test_start_date + years_to_timedelta(years) < data[-1][0]:
        model.model_config(test_start_date, years=years)

        start_idx = bisect.bisect_left(dates, test_start_date - model.skip_padding)
        skip_to_date = None
        for row in data[start_idx:]:
            if skip_to_date is not None and row[0] < skip_to_date:
                continue
            # data is (stock price, interest rate by years)
            bar = PriceBar(row[price_index], row[interest_index])
            skip_to_date = model.trade(row[0], bar)
            if not model.last_trigger:
                # last trade of this window is done; the rest of the data can't affect it
                break

        for log_line in model.status():
            logger.debug(log_line)

        result = model.total_returns()
        model_returns.append(result)
        logger.debug(
            f"frac_returns={result.frac_return:5.2%} yearly_return_rate={result.yearly_return_rate}"
            f" model={model.model_name} start_date={test_start_date}"
        )
        test_start_date += test_interval

    logger.info("End model testing")
    return model_returns


def skip_padding(backtest: BacktestConfig) -> datetime.timedelta:
    """Skip-ahead padding implied by the backtest stride."""
    return datetime.timedelta(days=backtest.padding_strides * backtest.stride_days)


def all_model_specs(config: AppConfig) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield (class_name, kwargs) for every model variant in the configured grid."""
    common: dict[str, Any] = {
        "capital": config.backtest.initial_capital,
        "skip_padding": skip_padding(config.backtest),
    }
    yield ("Model", common)
    kelly = config.models.kelly
    for bond_frac in kelly.bond_fracs:
        for rebalance_days in kelly.rebalance_days:
            yield (
                "KellyModel",
                common | {"bond_frac": bond_frac, "rebalance_period": rebalance_days},
            )
    insurance = config.models.insurance
    for frac in insurance.fracs:
        for deductible in insurance.deductibles:
            yield (
                "InsuranceModel",
                common
                | {
                    "insurance_frac": frac,
                    "insurance_deductible": deductible,
                    "insurance_period": insurance.period_days,
                    "premium_rate": insurance.premium_rate,
                    "coverage_ratio": insurance.coverage_ratio,
                    "loss_window_days": insurance.loss_window_days,
                },
            )


def write_returns_csv(path: Path, rows: list[WindowReturn]) -> None:
    """Write window results with the standard returns header."""
    with path.open("w") as outfile:
        writer = csv.writer(outfile)
        writer.writerow(RETURNS_CSV_HEADER)
        writer.writerows(rows)


def model_test_worker(
    years: int,
    class_name: str,
    model_kwargs: dict[str, Any],
    date_str: str,
    dataset_name: str,
    config: AppConfig,
) -> None:
    """Run one (years, model) combination and write its results to CSV.

    Loads the data itself so the pool doesn't pickle ~17K rows per task.

    Raises:
        EmptyReturnsError: If the data is too short for a single window.
    """
    dataset = load_dataset(dataset_name, config)
    data, _ = get_combined_data(dataset)
    model = MODEL_CLASSES[class_name](**model_kwargs)
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
        dataset.config.out_dir, years, f"{model.model_name}_{date_str}.csv"
    )
    logger.info(f"Writing results to {path}")
    write_returns_csv(path, results)


def main() -> None:
    """Parse arguments and run every task on a process pool."""
    parser = argparse.ArgumentParser(description="Run the full backtest grid.")
    parser.add_argument(
        "--dataset", default="sp500", help="dataset key from config.yaml (sp500, qqq)"
    )
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
    date_str = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
    tasks = [
        (years, class_name, kwargs, date_str, args.dataset, config)
        for years in config.backtest.years
        for class_name, kwargs in all_model_specs(config)
    ]
    with mp.Pool() as pool:
        pool.starmap(model_test_worker, tasks)
    logger.info("All model testing completed")


if __name__ == "__main__":
    main()
