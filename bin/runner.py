import argparse
import bisect
import csv
import datetime
import logging
import multiprocessing as mp
from pathlib import Path
from typing import Any, Iterator

import returns.data
from returns.data import (
    combined_interest_index,
    get_combined_sp500_interest_data,
    use_dataset,
)
from returns.models import (
    PADDING_TIME_DELTA,
    STRIDE_DAYS,
    InsuranceModel,
    KellyModel,
    Model,
    Returns,
)


def model_tester(
    model: Model,
    data: list[list[Any]],
    years: int = 10,
    price_index: int | None = None,
) -> list[Returns]:
    """
    Tests the given model on the provided data for the specified number of years.
    price_index selects the price column in each combined data row (default: the active dataset's).
    """
    if price_index is None:
        price_index = returns.data.combined_sp500_index
    test_interval = datetime.timedelta(days=STRIDE_DAYS)
    test_start_date = data[0][0]  # first (oldest) date in data
    model_returns: list[Returns] = []

    logging.info("Starting model testing")

    # Pre-compute date list once for bisect lookups
    dates = [d[0] for d in data]

    while test_start_date + datetime.timedelta(days=365 * years) < data[-1][0]:
        model.model_config(test_start_date, years=years)

        start_idx = bisect.bisect_left(dates, test_start_date - PADDING_TIME_DELTA)
        skip_to_date = None
        for d in data[start_idx:]:
            if skip_to_date is not None and d[0] < skip_to_date:
                continue
            else:
                # data is (stock price, interest rate by years)
                _data = (d[price_index], d[combined_interest_index])
                skip_to_date = model.trade(d[0], _data)
                if not model.last_trigger:
                    # last trade of this window is done; the rest of the data can't affect it
                    break

        for log_line in model.status():
            logging.debug(log_line)

        model_returns.append(model.total_returns())
        logging.debug(
            (
                f"frac_returns={model_returns[-1][1]:5.2%} yearly_return_rate={model_returns[-1][2]}"
                f" model={model.model_name} start_date={test_start_date}"
            )
        )
        test_start_date += test_interval

    logging.info("End model testing")
    return model_returns


def all_model_specs() -> Iterator[tuple[str, dict[str, float]]]:
    """Yields (class_name, kwargs) for every model variant."""
    yield ("Model", {})
    for i in [0.1, 0.2, 0.25, 0.15]:
        for j in [90, 180]:
            yield ("KellyModel", {"bond_fract": i, "rebalance_period": j})
    for frac in [0.05, 0.1]:
        for deductible in [0.09, 0.12, 0.18]:
            yield (
                "InsuranceModel",
                {"insurance_frac": frac, "insurance_deductible": deductible},
            )


def model_test_worker(
    years: int,
    class_name: str,
    model_kwargs: dict[str, Any],
    date_str: str,
    dataset: str = "sp500",
) -> None:
    """Worker that runs one (years, model) combination and writes results to CSV."""
    use_dataset(dataset)
    d, h = get_combined_sp500_interest_data()
    model_classes: dict[str, type[Model]] = {
        "Model": Model,
        "KellyModel": KellyModel,
        "InsuranceModel": InsuranceModel,
    }
    m = model_classes[class_name](**model_kwargs)
    rets = model_tester(m, d, years=years)

    fn = f"{returns.data.out_data_path}returns_{years}_{rets[0][-1]}_{date_str}.csv"
    logging.info(f"Writing results to {fn}")

    with open(fn, "w") as outfile:
        writer = csv.writer(outfile)
        writer.writerow(
            ["date", "frac_return", "yearly_return_rate", "time_span", "model_name"]
        )
        for r in rets:
            writer.writerow(r)


if __name__ == "__main__":
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
    logging.basicConfig(
        level=args.log_level,
        format="%(process)d|%(asctime)s|%(levelname)s|%(funcName)20s()|%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        filename="app1.log",
        filemode="w",
    )
    use_dataset(args.dataset)
    Path(returns.data.out_data_path).mkdir(parents=True, exist_ok=True)
    date_str = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
    tasks = [
        (years, class_name, kwargs, date_str, args.dataset)
        for years in range(1, 16)
        for class_name, kwargs in all_model_specs()
    ]
    with mp.Pool() as p:
        p.starmap(model_test_worker, tasks)
    logging.info("All model testing completed")
