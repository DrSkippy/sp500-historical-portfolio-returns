"""Command-line helpers shared by the bin/ scripts."""

import argparse

DEFAULT_DATASET = "sp500"


def add_dataset_argument(
    parser: argparse.ArgumentParser, default: str = DEFAULT_DATASET
) -> None:
    """Add the ``--dataset`` option selecting an entry under ``datasets`` in config.yaml."""
    parser.add_argument(
        "--dataset",
        default=default,
        help=f"dataset key from config.yaml (default: {default})",
    )


def add_run_argument(parser: argparse.ArgumentParser) -> None:
    """Add the ``--run`` option selecting a backtest run by timestamp."""
    parser.add_argument(
        "--run",
        help="run timestamp, e.g. 2026-10-07_1550 (default: newest for this model version)",
    )
