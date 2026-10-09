"""Turn S&P 500 rows pasted from Seeking Alpha into SP500.tab lines.

Each pasted record spans three lines: the date ("Mar. 11, 2026"), the
tab-separated Open/High/Low/Close prices, and the volume. Each becomes one
SP500.tab line: date (periods removed), the four prices, Close repeated as
"Adj Close**" (the index has no dividend adjustment), and the volume.

Usage:
    cat pasted.txt | poetry run python bin/transform_new_sp500_records.py
"""

import logging
import sys
from typing import Iterable, Iterator

from returns.logging_setup import configure_logging

##########################################################################################################
# https://seekingalpha.com/symbol/SP500/historical-price-quotes
# cut and paste new records to text file
# run transform_new_sp500_records.py:
#     cat deleteme.csv | python bin/transform_new_sp500_records.py | xclip -sel clip
# prepend to the sp500.tab file
##########################################################################################################

logger = logging.getLogger(__name__)

LINES_PER_RECORD = 3
DATE_LINE = 0
PRICES_LINE = 1
CLOSE_FIELD = 3
"""Index of Close among the pasted Open/High/Low/Close fields."""
FIELD_SEPARATOR = "\t"


def transform_record(record: list[str]) -> str:
    """Convert one three-line pasted record into an SP500.tab line.

    Args:
        record: The record's lines, stripped.

    Returns:
        The tab-separated line.
    """
    fields = list(record)
    fields[DATE_LINE] = fields[DATE_LINE].replace(".", "")
    close = fields[PRICES_LINE].split(FIELD_SEPARATOR)[CLOSE_FIELD]
    fields[PRICES_LINE] += FIELD_SEPARATOR + close
    return FIELD_SEPARATOR.join(fields)


def transform_records(lines: Iterable[str]) -> Iterator[str]:
    """Convert pasted lines, three per record, into SP500.tab lines.

    A trailing incomplete record is dropped with a warning (it was dropped
    silently before).

    Args:
        lines: Pasted text, one line per item.

    Yields:
        One SP500.tab line per complete record.
    """
    record: list[str] = []
    for line in lines:
        record.append(line.strip())
        if len(record) == LINES_PER_RECORD:
            yield transform_record(record)
            record = []
    if record:
        logger.warning("Ignoring %d trailing line(s): %s", len(record), record)


def main() -> None:
    """Read pasted records from stdin and write SP500.tab lines to stdout.

    Warnings go to stderr so they never end up in the piped output.
    """
    configure_logging("WARNING", ["stderr"])
    for line in transform_records(sys.stdin):
        sys.stdout.write(line + "\n")


if __name__ == "__main__":
    main()
