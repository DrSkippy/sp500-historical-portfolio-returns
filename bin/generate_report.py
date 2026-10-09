"""Generate report_data.json for the trading strategies static report site.

Reads one run's <out_dir>/summary_*.csv and <out_dir>/total_returns_*.json files,
merges them, and writes trading_strategies_report/data/report_data.json. The run is
the newest one produced by the current model version (``returns.models.MODEL_VERSION``,
from its ``run_{timestamp}.json`` manifest), or the one named with --run; summaries
from any other run are ignored.

Usage:
    poetry run python bin/generate_report.py [--dataset qqq] [--run 2026-10-07_1550]

With --dataset, reads that dataset's out_dir and writes its report_data file
(e.g. report_data_qqq.json, viewed at index.html?dataset=qqq).
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

from returns.cli import add_dataset_argument, add_run_argument
from returns.config import load_config
from returns.errors import (
    EmptyReturnsError,
    IncompleteRunError,
    NoMatchingRunError,
    NoModelOutputsError,
)
from returns.io_utils import write_compact_json
from returns.logging_setup import configure_logging
from returns.models import MODEL_VERSION, parse_model_name
from returns.runs import run_summary_files, select_run

logger = logging.getLogger(__name__)

BYTES_PER_MB = 1_048_576

# summary CSV column -> (report JSON key, parser), in report JSON key order
SUMMARY_FIELDS: dict[str, tuple[str, Callable[[str], Any]]] = {
    "time_span": ("year", lambda v: int(float(v))),
    "mean_total_returns": ("mean_total", float),
    "mean_yearly_compound_returns": ("mean_yearly", float),
    "median_total_returns": ("median_total", float),
    "median_yearly_returns": ("median_yearly", float),
    "sdev_total_returns": ("sdev_total", float),
    "sdev_yearly_returns": ("sdev_yearly", float),
    "fraction_losing_starts": ("fraction_losing", float),
    "mode_total_returns": ("mode_total", float),
    "mode_yearly_returns": ("mode_yearly", float),
    "sample_size": ("sample_size", int),
}


def load_summary(csv_path: Path) -> tuple[str, list[dict[str, Any]]]:
    """Load a summary CSV.

    Args:
        csv_path: Summary CSV written by bin/summarize.py.

    Returns:
        The model name and one dict per window length, sorted by year.

    Raises:
        EmptyReturnsError: If the CSV has no data rows.
    """
    with csv_path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise EmptyReturnsError(f"Summary file has no rows: {csv_path}")
    summary = [
        {key: parse(row[column]) for column, (key, parse) in SUMMARY_FIELDS.items()}
        for row in rows
    ]
    summary.sort(key=lambda r: r["year"])
    return rows[-1]["model_name"], summary


def load_distributions(
    json_path: Path, dist_years: Iterable[int]
) -> dict[str, list[float]]:
    """Load a total_returns JSON, keeping only the requested window lengths.

    Args:
        json_path: total_returns JSON written by bin/summarize.py.
        dist_years: Window lengths (years) to keep.

    Returns:
        Total returns keyed by window length (as str).
    """
    keep = {str(year) for year in dist_years}
    with json_path.open() as f:
        data: dict[str, list[float]] = json.load(f)
    return {k: v for k, v in data.items() if k in keep}


def build_report_data(
    file_map: dict[str, tuple[Path, Path]], dist_years: Iterable[int]
) -> dict[str, Any]:
    """Build the full report data structure.

    Args:
        file_map: Output of ``returns.data.run_summary_files``.
        dist_years: Window lengths whose full distributions are included
            (``report.dist_years``).

    Returns:
        ``{"models": [...]}`` sorted by model name.
    """
    dist_years = list(dist_years)
    models = []
    for model_name in sorted(file_map):
        summary_path, total_path = file_map[model_name]
        family, params = parse_model_name(model_name)
        _, summary_rows = load_summary(summary_path)
        models.append(
            {
                "name": model_name,
                "family": family,
                "params": params,
                "summary": summary_rows,
                "distributions": load_distributions(total_path, dist_years),
            }
        )
    return {"models": models}


def main() -> None:
    """Build and write the report JSON for one dataset."""
    parser = argparse.ArgumentParser(
        description="Build report_data.json for the report site."
    )
    add_dataset_argument(parser)
    add_run_argument(parser)
    args = parser.parse_args()
    configure_logging("INFO", ["console"])
    config = load_config()
    dataset = config.dataset(args.dataset)
    out_data = dataset.out_dir
    report_dir = config.report.output_dir
    output_path = report_dir / dataset.report_data

    report_dir.mkdir(parents=True, exist_ok=True)

    try:
        run = select_run(out_data, MODEL_VERSION, args.run)
        logger.info(
            f"Reporting run {run.timestamp} (model version {run.model_version})"
        )
        file_map = run_summary_files(out_data, run)
    except (NoMatchingRunError, NoModelOutputsError, IncompleteRunError) as e:
        logger.error(e)
        sys.exit(1)
    logger.info(f"Found {len(file_map)} model(s): {', '.join(sorted(file_map))}")

    logger.info("Building report data...")
    report = build_report_data(file_map, config.report.dist_years)

    logger.info(f"Writing {output_path}...")
    write_compact_json(output_path, report)

    size_mb = output_path.stat().st_size / BYTES_PER_MB
    logger.info(
        f"Done. {output_path} ({size_mb:.1f} MB, {len(report['models'])} models)"
    )


if __name__ == "__main__":
    main()
