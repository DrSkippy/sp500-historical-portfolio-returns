"""Summaries of a backtest run: per-model statistics and return distributions."""

import csv
import datetime
import json
import logging
from pathlib import Path
from typing import Iterable

import pandas as pd

from returns.analysis import (
    get_aggregate_returns_by_period,
    get_df_aggregate_returns_by_period,
)
from returns.errors import DataFileFormatError
from returns.io_utils import log_rows_read
from returns.naming import (
    ISO_DATE_FORMAT,
    returns_file_path,
    returns_file_suffix,
    summary_file_path,
    total_returns_path,
)
from returns.types import RETURNS_CSV_HEADER, SUMMARY_COLUMNS, WindowReturn

logger = logging.getLogger(__name__)


def parse_window_return(row: list[str]) -> WindowReturn:
    """Parse one row of a returns CSV (written by runner.py from ``WindowReturn``)."""
    date, frac_return, yearly_return_rate, time_span, model_name = row
    return WindowReturn(
        date=datetime.datetime.strptime(date[:10], ISO_DATE_FORMAT),
        frac_return=float(frac_return),
        yearly_return_rate=float(yearly_return_rate),
        time_span=float(time_span),
        model_name=model_name,
    )


def read_run_returns(
    out_dir: Path, suffix: str, years: Iterable[int]
) -> dict[int, list[WindowReturn]]:
    """Read one model run's returns files for each window length.

    Args:
        out_dir: Directory holding the returns files.
        suffix: ``{model}_{timestamp}.csv`` identifying the run.
        years: Window lengths to read.

    Returns:
        Window results keyed by window length, each sorted by start date.

    Raises:
        DataFileFormatError: If a file's header is not the returns CSV header or a
            row cannot be parsed.
    """
    results: dict[int, list[WindowReturn]] = {}

    logger.info("Reading model run data")
    for year in years:
        filename = returns_file_path(out_dir, year, suffix)
        logger.info("Reading %s", filename)

        with filename.open() as infile:
            reader = csv.reader(infile)
            header = next(reader)  # Reading the header
            if header != RETURNS_CSV_HEADER:
                raise DataFileFormatError(
                    f"{filename}: header {header} is not {RETURNS_CSV_HEADER}"
                )
            try:
                data = [parse_window_return(row) for row in reader]
            except ValueError as e:
                raise DataFileFormatError(
                    f"{filename}:{reader.line_num}: cannot parse row ({e})"
                ) from e

        results[year] = sorted(data)
        log_rows_read("returns", filename, len(data), header)

    return results


def create_summary_file(
    results: dict[int, list[WindowReturn]],
    filename: Path,
    *,
    bins: int,
) -> tuple[Path, Path]:
    """Write a model run's summary CSV and total-returns JSON.

    Args:
        results: Window results keyed by window length (``read_run_returns``).
        filename: Summary CSV to write; the JSON goes alongside it.
        bins: Histogram bins for the mode estimates.

    Returns:
        The summary CSV and total-returns JSON paths.
    """
    returns_stats_by_period, total_returns_by_period = get_aggregate_returns_by_period(
        results, bins
    )
    df = get_df_aggregate_returns_by_period(returns_stats_by_period)

    df.to_csv(filename, index=False)
    logger.info("Summary data written to %s", filename)

    json_filename = total_returns_path(filename)
    with json_filename.open("w") as outfile:
        json.dump(total_returns_by_period, outfile)
    logger.info("Total returns data written to %s", json_filename)
    return filename, json_filename


def create_summary_files(
    out_dir: Path,
    files: Iterable[Path],
    years: Iterable[int],
    *,
    bins: int,
) -> list[tuple[Path, Path]]:
    """Summarize every model run found among the given returns files.

    Args:
        out_dir: Directory holding the returns files.
        files: Returns files (``returns_{years}_{model}_{timestamp}.csv``).
        years: Window lengths every run must have.
        bins: Histogram bins for the mode estimates.

    Returns:
        The (summary CSV, total-returns JSON) paths written, one pair per run.
    """
    # Extract unique suffixes from file names
    # returns_{years}_{suffix}
    suffixes = sorted({returns_file_suffix(Path(f)) for f in files})
    logger.info("Suffixes extracted from file names")
    for s in sorted({"_".join(x.split("_")[1:]) for x in suffixes}):
        logger.info("  - %s", s)
    years = list(years)
    files_created = []
    for i, suffix in enumerate(suffixes):
        logger.info("*** %s of %s *** %s", i, len(suffixes), suffix)
        results = read_run_returns(out_dir, suffix, years)
        files_created.append(
            create_summary_file(results, summary_file_path(out_dir, suffix), bins=bins)
        )
    return files_created


def read_summary_data(filename: Path) -> tuple[pd.DataFrame, dict[str, list[float]]]:
    """Read a summary CSV and its total-returns JSON.

    Args:
        filename: Summary CSV path.

    Returns:
        The summary table and the total returns keyed by window length (as str).
    """
    df = pd.read_csv(filename)
    with total_returns_path(filename).open() as infile:
        total_returns_by_period: dict[str, list[float]] = json.load(infile)
    return df, total_returns_by_period


def get_model_comparison_data(files: Iterable[Path], year: int = 10) -> pd.DataFrame:
    """Collect one window length's summary row from each model's summary file.

    Args:
        files: Summary CSV paths, one per model.
        year: Window length in years to compare.

    Returns:
        One row per model, sorted by mean total return.
    """
    rows = []
    for path in files:
        summary, _ = read_summary_data(path)
        rows.append(summary.loc[summary["time_span"] == year].iloc[0].to_list())
    comparison = pd.DataFrame(rows, columns=SUMMARY_COLUMNS)
    return comparison.sort_values("mean_total_returns")
