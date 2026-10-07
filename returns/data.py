"""File I/O for price, interest, backtest-output and summary data."""

import csv
import datetime
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from pydantic import BaseModel

from returns.analysis import (
    HISTOGRAM_BINS,
    get_aggregate_returns_by_period,
    get_df_aggregate_returns_by_period,
)
from returns.config import AppConfig, DatasetConfig, load_config
from returns.errors import MissingPriceColumnError, NoMatchingRunError
from returns.types import SUMMARY_COLUMNS

logger = logging.getLogger(__name__)

PRICE_DATE_FORMAT = "%b %d, %Y"
OUTPUT_DATE_FORMAT = "%Y-%m-%d"
INTEREST_DATE_FORMAT = "%Y-%m-%d"
PERCENT = 100.0
INTEREST_RATE_COLUMN = 0
"""Index of the rate used by the models among the interest file's value columns."""

Row = list[Any]


@dataclass(frozen=True)
class Dataset:
    """A dataset from config.yaml plus the column layout of its files.

    Combined rows are ``price_row + interest_values``: the date, the price file's
    value columns, then the interest file's value columns.
    """

    name: str
    config: DatasetConfig
    interest_path: Path
    price_header: tuple[str, ...]

    @property
    def price_index(self) -> int:
        """Column of the traded price in price-file (and combined) rows."""
        try:
            return self.price_header.index(self.config.price_column)
        except ValueError:
            raise MissingPriceColumnError(
                f"Price column {self.config.price_column!r} not in "
                f"{self.config.price_path} header {list(self.price_header)}"
            ) from None

    @property
    def interest_index(self) -> int:
        """Column of the interest rate in combined rows."""
        return len(self.price_header) + INTEREST_RATE_COLUMN


def read_header(path: Path) -> list[str]:
    """Return the first row of a tab-separated file."""
    with path.open() as infile:
        return next(csv.reader(infile, delimiter="\t"))


def load_dataset(name: str, config: AppConfig | None = None) -> Dataset:
    """Resolve a dataset from config.yaml and read its price-file header.

    Args:
        name: Key under ``datasets`` in config.yaml (e.g. "sp500", "qqq").
        config: Loaded configuration; read from the default config.yaml if None.

    Returns:
        The dataset.

    Raises:
        DatasetConfigError: If the dataset is unknown or config is invalid.
        MissingPriceColumnError: If the price column is not in the file header.
    """
    config = config or load_config()
    dataset_config = config.dataset(name)
    dataset = Dataset(
        name=name,
        config=dataset_config,
        interest_path=config.sources.interest_path,
        price_header=tuple(read_header(dataset_config.price_path)),
    )
    dataset.price_index  # validate the price column eagerly
    logger.info(f"Using dataset {name}: {dataset_config}")
    return dataset


def parse_number(text: str) -> float:
    """Parse a number that may contain comma thousands separators ("6,790.09")."""
    return float(text.replace(",", ""))


def get_interest_data(path: Path) -> tuple[dict[int, list[float]], list[str]]:
    """Read yearly interest rates from a TSV file of percentages.

    Args:
        path: Interest file (first column a date, then one column per series).

    Returns:
        Rates as fractions keyed by year, and the header without the date column.
    """
    interest_data = {}

    with path.open() as infile:
        reader = csv.reader(infile, delimiter="\t")
        header = next(reader)[1:]  # Reading the header

        for row in reader:
            if not row:
                continue
            year = datetime.datetime.strptime(row[0], INTEREST_DATE_FORMAT).year
            interest_data[year] = [float(x) / PERCENT for x in row[1:]]

    logger.info("Reading interest data")
    logger.info(f"Path = {path}")
    logger.info(f"Read {len(interest_data)} rows")
    logger.info(f"Fields = {header}")

    return interest_data, header


def get_price_data(path: Path) -> tuple[list[Row], list[str]]:
    """Read daily prices from a TSV file.

    Args:
        path: Price file ("Mon DD, YYYY" dates, any row order).

    Returns:
        Rows of ``[date, value, ...]`` sorted by date, and the header.
    """
    parsed_data: list[Row] = []

    with path.open() as infile:
        reader = csv.reader(infile, delimiter="\t")
        header = next(reader)  # Reading the header

        for row in reader:
            # Parse date and data values
            date = datetime.datetime.strptime(row[0], PRICE_DATE_FORMAT)
            parsed_data.append([date] + [parse_number(x) for x in row[1:]])

    # Sort data by date
    parsed_data.sort()

    logger.info("Reading price data")
    logger.info(f"Path = {path}")
    logger.info(f"Read {len(parsed_data)} rows")
    logger.info(f"Fields = {header}")

    return parsed_data, header


def get_combined_data(dataset: Dataset) -> tuple[list[Row], list[str]]:
    """Join each price row with the interest rates for its year.

    Years after the last interest row use the last available rates.

    Args:
        dataset: Dataset to read.

    Returns:
        Combined rows sorted by date, and the combined header.
    """
    logger.info("Combining price and interest data")
    prices, price_header = get_price_data(dataset.config.price_path)
    interest, interest_header = get_interest_data(dataset.interest_path)
    max_interest_year = max(interest.keys())
    combined = [row + interest[min(row[0].year, max_interest_year)] for row in prices]
    return combined, price_header + interest_header


def create_combined_data_file(dataset: Dataset) -> None:
    """Write the combined price + interest data to the dataset's combined_path."""
    data, header = get_combined_data(dataset)
    with dataset.config.combined_path.open("w") as outfile:
        writer = csv.writer(outfile)
        writer.writerow(header)
        writer.writerows(data)


def returns_file_path(out_dir: Path, years: int, suffix: str) -> Path:
    """Path of a backtest output file: ``returns_{years}_{model}_{timestamp}.csv``."""
    return out_dir / f"returns_{years}_{suffix}"


def returns_file_suffix(path: Path) -> str:
    """The ``{model}_{timestamp}.csv`` part of a returns file name."""
    return "_".join(path.name.split("_")[2:])


def total_returns_path(summary_path: Path) -> Path:
    """Path of the total-returns JSON that accompanies a summary CSV."""
    return summary_path.with_name(
        summary_path.name.replace("summary", "total_returns").replace(".csv", ".json")
    )


class RunManifest(BaseModel):
    """What produced one backtest run; written by runner.py as ``run_{timestamp}.json``."""

    timestamp: str
    """Run id, also the suffix of every output file name (``YYYY-MM-DD_HHMM``)."""
    model_version: int
    dataset: str
    years: list[int]
    model_count: int


def run_manifest_path(out_dir: Path, timestamp: str) -> Path:
    """Path of a run's manifest file."""
    return out_dir / f"run_{timestamp}.json"


def write_run_manifest(out_dir: Path, manifest: RunManifest) -> Path:
    """Write a run's manifest next to its output files."""
    path = run_manifest_path(out_dir, manifest.timestamp)
    path.write_text(manifest.model_dump_json(indent=1) + "\n")
    return path


def find_runs(out_dir: Path) -> list[RunManifest]:
    """All runs with a manifest in ``out_dir``, oldest first."""
    manifests = [
        RunManifest.model_validate_json(path.read_text())
        for path in out_dir.glob("run_*.json")
    ]
    return sorted(manifests, key=lambda m: m.timestamp)


def select_run(
    out_dir: Path, model_version: int, timestamp: str | None = None
) -> RunManifest:
    """Choose the run to summarize.

    Args:
        out_dir: Dataset output directory.
        model_version: Only runs produced by this model version qualify.
        timestamp: A specific run id; the newest qualifying run if None.

    Returns:
        The selected run's manifest.

    Raises:
        NoMatchingRunError: If no run qualifies. Runs without a manifest (from
            before manifests existed) never qualify.
    """
    runs = [m for m in find_runs(out_dir) if m.model_version == model_version]
    if timestamp is not None:
        runs = [m for m in runs if m.timestamp == timestamp]
    if not runs:
        wanted = f"run {timestamp} " if timestamp else ""
        raise NoMatchingRunError(
            f"No {wanted}for model version {model_version} in {out_dir}; "
            "run bin/runner.py first"
        )
    return runs[-1]


def run_returns_files(out_dir: Path, timestamp: str) -> list[Path]:
    """The returns files belonging to one run."""
    return sorted(out_dir.glob(f"returns_*_{timestamp}.csv"))


def get_model_run_outputs(
    out_dir: Path, suffix: str, years: Iterable[int] = (1, 2, 3)
) -> tuple[dict[int, list[Row]], list[str] | None, Path]:
    """Read one model run's returns files for each window length.

    Args:
        out_dir: Directory holding the returns files.
        suffix: ``{model}_{timestamp}.csv`` identifying the run.
        years: Window lengths to read.

    Returns:
        Rows keyed by window length (sorted by date), the CSV header, and the
        summary file path to write.
    """
    results: dict[int, list[Row]] = {}
    header: list[str] | None = None

    logger.info("Reading model run data")
    for year in years:
        filename = returns_file_path(out_dir, year, suffix)
        logger.info(f"Reading {filename}")

        with filename.open() as infile:
            reader = csv.reader(infile)
            header = next(reader)  # Reading the header
            data = [
                [datetime.datetime.strptime(row[0][:10], OUTPUT_DATE_FORMAT)] + row[1:]
                for row in reader
            ]

        results[year] = sorted(data)
        logger.info(f"Read {len(data)} rows")
        logger.info(f"Fields = {header}")

    return results, header, out_dir / f"summary_{suffix}"


def create_summary_file(
    results: dict[int, list[Row]],
    header: list[str] | None,
    filename: Path,
    bins: int = HISTOGRAM_BINS,
) -> tuple[Path, Path]:
    """Write a model run's summary CSV and total-returns JSON.

    Args:
        results: Returns rows keyed by window length.
        header: Header of the returns files (unused; kept for the call signature
            produced by ``get_model_run_outputs``).
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
    logger.info(f"Summary data written to {filename}")

    json_filename = total_returns_path(filename)
    with json_filename.open("w") as outfile:
        json.dump(total_returns_by_period, outfile)
    logger.info(f"Total returns data written to {json_filename}")
    return filename, json_filename


def create_summary_files(
    out_dir: Path,
    files: Iterable[Path],
    years: Iterable[int],
    bins: int = HISTOGRAM_BINS,
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
        logger.info(f"  - {s}")
    years = list(years)
    files_created = []
    for i, suffix in enumerate(suffixes):
        logger.info(f"*** {i} of {len(suffixes)} *** {suffix}")
        result = get_model_run_outputs(out_dir, suffix, years=years)
        files_created.append(create_summary_file(*result, bins=bins))
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
