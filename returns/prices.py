"""Price and interest-rate data: datasets, file readers and the combined rows."""

import csv
import datetime
import logging
from dataclasses import dataclass
from pathlib import Path

from returns.config import AppConfig, DatasetConfig, load_config
from returns.errors import MissingInterestDataError, MissingPriceColumnError
from returns.io_utils import log_rows_read, read_tsv
from returns.naming import ISO_DATE_FORMAT, PRICE_DATE_FORMAT
from returns.types import Row

logger = logging.getLogger(__name__)

PERCENT = 100.0
INTEREST_RATE_COLUMN = 0
"""Index of the rate used by the models among the interest file's value columns."""


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

    def __post_init__(self) -> None:
        """Validate the price column eagerly.

        Raises:
            MissingPriceColumnError: If the price column is not in the header.
        """
        _ = self.price_index

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

    Raises:
        DataFileFormatError: If a row cannot be parsed.
    """

    def parse_row(row: list[str]) -> tuple[int, list[float]]:
        year = datetime.datetime.strptime(row[0], ISO_DATE_FORMAT).year
        return year, [float(x) / PERCENT for x in row[1:]]

    full_header, rows = read_tsv(path, parse_row)
    header = full_header[1:]
    interest_data = dict(rows)

    log_rows_read("interest", path, len(interest_data), header)

    return interest_data, header


def get_price_data(path: Path) -> tuple[list[Row], list[str]]:
    """Read daily prices from a TSV file.

    Args:
        path: Price file ("Mon DD, YYYY" dates, any row order).

    Returns:
        Rows of ``[date, value, ...]`` sorted by date, and the header.

    Raises:
        DataFileFormatError: If a row cannot be parsed.
    """

    def parse_row(row: list[str]) -> Row:
        # Parse date and data values
        date = datetime.datetime.strptime(row[0], PRICE_DATE_FORMAT)
        return [date] + [parse_number(x) for x in row[1:]]

    header, parsed_data = read_tsv(path, parse_row)

    # Sort data by date
    parsed_data.sort()

    log_rows_read("price", path, len(parsed_data), header)

    return parsed_data, header


def get_combined_data(dataset: Dataset) -> tuple[list[Row], list[str]]:
    """Join each price row with the interest rates for its year.

    Years after the last interest row use the last available rates.

    Args:
        dataset: Dataset to read.

    Returns:
        Combined rows sorted by date, and the combined header.

    Raises:
        MissingInterestDataError: If the interest file is empty, or has no rate
            for a year of price data up to its last year.
    """
    logger.info("Combining price and interest data")
    prices, price_header = get_price_data(dataset.config.price_path)
    interest, interest_header = get_interest_data(dataset.interest_path)
    if not interest:
        raise MissingInterestDataError(f"No interest rates in {dataset.interest_path}")
    max_interest_year = max(interest.keys())
    missing_years = sorted(
        {min(row[0].year, max_interest_year) for row in prices} - interest.keys()
    )
    if missing_years:
        raise MissingInterestDataError(
            f"{dataset.interest_path} has no rate for years {missing_years} "
            f"needed by {dataset.config.price_path}"
        )
    combined = [row + interest[min(row[0].year, max_interest_year)] for row in prices]
    return combined, price_header + interest_header


def create_combined_data_file(dataset: Dataset) -> None:
    """Write the combined price + interest data to the dataset's combined_path."""
    data, header = get_combined_data(dataset)
    with dataset.config.combined_path.open("w") as outfile:
        writer = csv.writer(outfile)
        writer.writerow(header)
        writer.writerows(data)
