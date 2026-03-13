import bisect
import multiprocessing as mp

from returns.data import *
from returns.models import *

# Configure logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(process)d|%(asctime)s|%(levelname)s|%(funcName)20s()|%(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S',
                    filename='app1.log',
                    filemode='w')

path = "./out_data/"


def model_tester(model, data, years=10):
    """
    Tests the given model on the provided data for the specified number of years.
    """
    test_interval = datetime.timedelta(days=STRIDE_DAYS)
    test_start_date = data[0][0]  # first (oldest) date in data
    model_returns = []

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
                _data = (d[combined_sp500_index], d[combined_interest_index])
                skip_to_date = model.trade(d[0], _data)

        for log_line in model.status():
            logging.debug(log_line)

        model_returns.append(model.total_returns())
        logging.debug((f"frac_returns={model_returns[-1][1]:5.2%} yearly_return_rate={model_returns[-1][2]}"
                       "model={model.name} start_date={test_start_date}"))
        test_start_date += test_interval

    logging.info("End model testing")
    return model_returns


def all_model_specs():
    """Yields (class_name, kwargs) for every model variant."""
    yield ("Model", {})
    for i in [0.1, 0.2, 0.25, 0.15]:
        for j in [90, 180]:
            yield ("KellyModel", {"bond_fract": i, "rebalance_period": j})
    for i in [0.05, 0.1]:
        for j in [0.09, 0.12, 0.18]:
            yield ("InsuranceModel", {"insurance_frac": i, "insurance_deductible": j})


def model_test_worker(years: int, class_name: str, model_kwargs: dict, date_str: str) -> None:
    """Worker that runs one (years, model) combination and writes results to CSV."""
    d, h = get_combined_sp500_interest_data()
    model_classes = {"Model": Model, "KellyModel": KellyModel, "InsuranceModel": InsuranceModel}
    m = model_classes[class_name](**model_kwargs)
    rets = model_tester(m, d, years=years)

    fn = f"{path}returns_{years}_{rets[0][-1]}_{date_str}.csv"
    logging.info(f"Writing results to {fn}")

    with open(fn, "w") as outfile:
        writer = csv.writer(outfile)
        writer.writerow(["date", "frac_return", "yearly_return_rate", "time_span", "model_name"])
        for r in rets:
            writer.writerow(r)


if __name__ == '__main__':
    date_str = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
    tasks = [
        (years, class_name, kwargs, date_str)
        for years in range(1, 16)
        for class_name, kwargs in all_model_specs()
    ]
    with mp.Pool() as p:
        p.starmap(model_test_worker, tasks)
    logging.info("All model testing completed")
