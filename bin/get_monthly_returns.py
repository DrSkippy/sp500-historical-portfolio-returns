"""Sample 30-day rolling returns and write them to out_data/monthly_returns.csv.

Usage:
    poetry run python bin/get_monthly_returns.py [--dataset qqq] [--no-plot]
"""

import argparse
import logging

from returns.config import load_config
from returns.data import get_combined_data, load_dataset
from returns.logging_setup import configure_logging
from returns.monthly_returns import MonthlyReturns

logger = logging.getLogger(__name__)

SAMPLE_COUNT = 20


def main() -> None:
    """Print sample returns and a summary, plot the distribution, write the CSV."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset", default="sp500", help="dataset key from config.yaml (sp500, qqq)"
    )
    parser.add_argument("--no-plot", action="store_true", help="skip the histogram")
    args = parser.parse_args()
    configure_logging("INFO", ["console"])

    config = load_config()
    dataset = load_dataset(args.dataset, config)
    settings = config.monthly_returns
    data, header = get_combined_data(dataset)
    monthly = MonthlyReturns(
        data, header, dataset.config.price_column, settings.offset_days
    )

    for _ in range(SAMPLE_COUNT):
        logger.info(monthly.sample())
    logger.info(monthly.summary())
    if not args.no_plot:
        monthly.plot_returns(settings.histogram_bins)
    monthly.write_to_csv(str(settings.output_path))


if __name__ == "__main__":
    main()
