"""Aggregate one backtest run's returns CSVs into summary_*.csv / total_returns_*.json.

Only runs produced by the current model version (``returns.models.MODEL_VERSION``,
recorded in each run's ``run_{timestamp}.json`` manifest) are processed: by default
the newest such run, or the one named with --run.

Usage:
    poetry run python bin/summarize.py [--dataset qqq] [--run 2026-10-07_1550]
"""

import argparse
import logging
import sys

from returns.cli import add_dataset_argument, add_run_argument
from returns.config import load_config
from returns.errors import NoMatchingRunError
from returns.logging_setup import configure_logging
from returns.models import MODEL_VERSION
from returns.prices import create_combined_data_file, load_dataset
from returns.runs import run_returns_files, select_run
from returns.summaries import create_summary_files

logger = logging.getLogger(__name__)


def main() -> None:
    """Write the combined data file and one summary per model in the selected run."""
    parser = argparse.ArgumentParser(description="Summarize backtest output CSVs.")
    add_dataset_argument(parser)
    add_run_argument(parser)
    args = parser.parse_args()
    configure_logging("INFO", ["console"])

    config = load_config()
    dataset = load_dataset(args.dataset, config)
    out_dir = dataset.config.out_dir
    try:
        run = select_run(out_dir, MODEL_VERSION, args.run)
    except NoMatchingRunError as e:
        logger.error(e)
        sys.exit(1)
    logger.info(
        "Summarizing run %s (model version %s)", run.timestamp, run.model_version
    )

    create_combined_data_file(dataset)
    files_created = create_summary_files(
        out_dir,
        run_returns_files(out_dir, run.timestamp),
        run.years,
        bins=config.backtest.histogram_bins,
    )
    logger.info("Wrote %s summaries to %s", len(files_created), out_dir)


if __name__ == "__main__":
    main()
