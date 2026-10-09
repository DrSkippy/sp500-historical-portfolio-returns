"""Small file helpers shared by the data modules and scripts."""

import csv
import json
import logging
from pathlib import Path
from typing import Any, Callable, Sequence, TypeVar

from returns.errors import DataFileFormatError

logger = logging.getLogger(__name__)

T = TypeVar("T")

COMPACT_JSON_SEPARATORS = (",", ":")


def read_tsv(
    path: Path, parse_row: Callable[[list[str]], T]
) -> tuple[list[str], list[T]]:
    """Read a tab-separated file with a header row, parsing each data row.

    Blank lines are skipped.

    Args:
        path: File to read.
        parse_row: Converts one row of fields.

    Returns:
        The header and the parsed rows, in file order.

    Raises:
        DataFileFormatError: If a row cannot be parsed (with its file and line).
    """
    with path.open() as infile:
        reader = csv.reader(infile, delimiter="\t")
        header = next(reader)  # Reading the header
        parsed = []
        for row in reader:
            if not row:
                continue
            try:
                parsed.append(parse_row(row))
            except (ValueError, IndexError) as e:
                raise DataFileFormatError(
                    f"{path}:{reader.line_num}: cannot parse {row!r} ({e})"
                ) from e
    return header, parsed


def log_rows_read(kind: str, path: Path, row_count: int, header: Sequence[str]) -> None:
    """Log what a reader loaded (the same lines for every input file)."""
    logger.info(f"Reading {kind} data")
    logger.info(f"Path = {path}")
    logger.info(f"Read {row_count} rows")
    logger.info(f"Fields = {header}")


def write_compact_json(path: Path, data: Any) -> None:
    """Write JSON without whitespace (the report site's data files)."""
    with path.open("w") as f:
        json.dump(data, f, separators=COMPACT_JSON_SEPARATORS)
