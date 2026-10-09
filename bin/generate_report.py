"""Generate report_data.json for the trading strategies static report site.

Reads all <out_dir>/summary_*.csv and <out_dir>/total_returns_*.json files,
merges them, and writes trading_strategies_report/data/report_data.json.

Usage:
    poetry run python bin/generate_report.py [--dataset qqq]

With --dataset, reads that dataset's out_dir and writes its report_data file
(e.g. report_data_qqq.json, viewed at index.html?dataset=qqq).
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

from returns.config import load_config
from returns.errors import EmptyReturnsError, NoModelOutputsError
from returns.logging_setup import configure_logging
from returns.models import parse_model_name

logger = logging.getLogger(__name__)

BYTES_PER_MB = 1_048_576

# Pattern: {kind}_{model_name}_{date}_{time}.{ext}
SUMMARY_PATTERN = re.compile(r"^summary_(.+)_\d{4}-\d{2}-\d{2}_\d{4}\.csv$")
TOTAL_RETURNS_PATTERN = re.compile(
    r"^total_returns_(.+)_\d{4}-\d{2}-\d{2}_\d{4}\.json$"
)

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


def latest_by_model(paths: Iterable[Path], pattern: re.Pattern[str]) -> dict[str, Path]:
    """Map each model name to its most recent file matching ``pattern``.

    The lexicographically greatest name wins, which is the latest timestamp suffix.
    """
    latest: dict[str, Path] = {}
    for path in paths:
        match = pattern.match(path.name)
        if match:
            model = match.group(1)
            if model not in latest or path.name > latest[model].name:
                latest[model] = path
    return latest


def find_latest_files(out_data: Path) -> dict[str, tuple[Path, Path]]:
    """Find the most recent summary + total_returns file pair per model.

    Args:
        out_data: Directory holding backtest summaries.

    Returns:
        Mapping of model_name -> (summary_path, total_returns_path).

    Raises:
        NoModelOutputsError: If no model has both files.
    """
    paths = list(out_data.iterdir())
    summaries = latest_by_model(paths, SUMMARY_PATTERN)
    totals = latest_by_model(paths, TOTAL_RETURNS_PATTERN)
    models_found = set(summaries) & set(totals)
    if not models_found:
        raise NoModelOutputsError(
            f"No matching summary/total_returns file pairs found in {out_data}"
        )
    return {m: (summaries[m], totals[m]) for m in models_found}


def build_report_data(
    file_map: dict[str, tuple[Path, Path]], dist_years: Iterable[int]
) -> dict[str, Any]:
    """Build the full report data structure.

    Args:
        file_map: Output of ``find_latest_files``.
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
    parser.add_argument(
        "--dataset", default="sp500", help="dataset key from config.yaml (sp500, qqq)"
    )
    args = parser.parse_args()
    configure_logging("INFO", ["console"])
    config = load_config()
    dataset = config.dataset(args.dataset)
    out_data = dataset.out_dir
    report_dir = config.report.output_dir
    output_path = report_dir / dataset.report_data

    report_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Scanning {out_data} for model files...")
    try:
        file_map = find_latest_files(out_data)
    except NoModelOutputsError as e:
        logger.error(e)
        sys.exit(1)
    logger.info(f"Found {len(file_map)} model(s): {', '.join(sorted(file_map))}")

    logger.info("Building report data...")
    report = build_report_data(file_map, config.report.dist_years)

    logger.info(f"Writing {output_path}...")
    with output_path.open("w") as f:
        json.dump(report, f, separators=(",", ":"))

    size_mb = output_path.stat().st_size / BYTES_PER_MB
    logger.info(
        f"Done. {output_path} ({size_mb:.1f} MB, {len(report['models'])} models)"
    )


if __name__ == "__main__":
    main()
