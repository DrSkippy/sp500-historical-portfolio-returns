"""Aggregate backtest returns CSVs into summary_*.csv / total_returns_*.json.

Usage:
    poetry run python bin/summarize.py [--dataset qqq]
"""

import argparse
import logging

from returns.config import load_config
from returns.data import create_combined_data_file, create_summary_files, load_dataset
from returns.logging_setup import configure_logging

logger = logging.getLogger(__name__)


def main() -> None:
    """Write the combined data file and one summary per model run."""
    parser = argparse.ArgumentParser(description="Summarize backtest output CSVs.")
    parser.add_argument(
        "--dataset", default="sp500", help="dataset key from config.yaml (sp500, qqq)"
    )
    args = parser.parse_args()
    configure_logging("INFO", ["console"])

    config = load_config()
    dataset = load_dataset(args.dataset, config)
    create_combined_data_file(dataset)
    out_dir = dataset.config.out_dir
    files_created = create_summary_files(
        out_dir,
        sorted(out_dir.glob("returns_*.csv")),
        config.backtest.years,
        bins=config.backtest.histogram_bins,
    )
    logger.info(f"Summary files created: {files_created}")
    logger.info("Done")


if __name__ == "__main__":
    main()
