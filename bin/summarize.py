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

from returns.config import load_config
from returns.data import (
    create_combined_data_file,
    create_summary_files,
    load_dataset,
    run_returns_files,
    select_run,
)
from returns.errors import NoMatchingRunError
from returns.logging_setup import configure_logging
from returns.models import MODEL_VERSION

logger = logging.getLogger(__name__)


def main() -> None:
    """Write the combined data file and one summary per model in the selected run."""
    parser = argparse.ArgumentParser(description="Summarize backtest output CSVs.")
    parser.add_argument(
        "--dataset", default="sp500", help="dataset key from config.yaml (sp500, qqq)"
    )
    parser.add_argument(
        "--run",
        help="run timestamp to summarize (default: newest for this model version)",
    )
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
    logger.info(f"Summarizing run {run.timestamp} (model version {run.model_version})")

    create_combined_data_file(dataset)
    files_created = create_summary_files(
        out_dir,
        run_returns_files(out_dir, run.timestamp),
        run.years,
        bins=config.backtest.histogram_bins,
    )
    logger.info(f"Wrote {len(files_created)} summaries to {out_dir}")


if __name__ == "__main__":
    main()
