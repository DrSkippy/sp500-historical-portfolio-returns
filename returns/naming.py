"""Date formats and the names of every file the pipeline writes.

Output files in a dataset's ``out_dir``, all carrying the run timestamp:

- ``run_{timestamp}.json``: run manifest (runner.py)
- ``returns_{years}_{model}_{timestamp}.csv``: per-window results (runner.py)
- ``summary_{model}_{timestamp}.csv``: aggregate statistics (summarize.py)
- ``total_returns_{model}_{timestamp}.json``: return distributions (summarize.py)

``{model}_{timestamp}.csv`` is a run's *suffix*: it identifies one model in one run.
"""

import datetime
from pathlib import Path

ISO_DATE_FORMAT = "%Y-%m-%d"
"""Dates in the interest file, returns CSVs and report JSON."""
PRICE_DATE_FORMAT = "%b %d, %Y"
"""Dates in the price files (``SP500.tab`` layout, e.g. "Jan 02, 2020")."""
RUN_TIMESTAMP_FORMAT = "%Y-%m-%d_%H%M"
"""Run ids; they sort chronologically."""

RETURNS_PREFIX = "returns_"
SUMMARY_PREFIX = "summary_"
TOTAL_RETURNS_PREFIX = "total_returns_"
RUN_MANIFEST_PREFIX = "run_"
CSV_EXTENSION = ".csv"
JSON_EXTENSION = ".json"


def new_run_timestamp(now: datetime.datetime | None = None) -> str:
    """Run id for a run started at ``now`` (default: the current time)."""
    return (now or datetime.datetime.now()).strftime(RUN_TIMESTAMP_FORMAT)


def run_suffix(model_name: str, timestamp: str) -> str:
    """``{model}_{timestamp}.csv``: identifies one model's output in one run."""
    return f"{model_name}_{timestamp}{CSV_EXTENSION}"


def returns_file_path(out_dir: Path, years: int, suffix: str) -> Path:
    """Path of a backtest output file: ``returns_{years}_{model}_{timestamp}.csv``."""
    return out_dir / f"{RETURNS_PREFIX}{years}_{suffix}"


def returns_file_suffix(path: Path) -> str:
    """The ``{model}_{timestamp}.csv`` part of a returns file name."""
    return "_".join(path.name.split("_")[2:])


def run_returns_glob(timestamp: str) -> str:
    """Glob matching every returns file of one run."""
    return f"{RETURNS_PREFIX}*_{timestamp}{CSV_EXTENSION}"


def summary_file_path(out_dir: Path, suffix: str) -> Path:
    """Path of a model's summary CSV in a run: ``summary_{model}_{timestamp}.csv``."""
    return out_dir / f"{SUMMARY_PREFIX}{suffix}"


def run_summary_glob(timestamp: str) -> str:
    """Glob matching every summary CSV of one run."""
    return f"{SUMMARY_PREFIX}*_{timestamp}{CSV_EXTENSION}"


def summary_model_name(summary_path: Path, timestamp: str) -> str:
    """The model name in a summary CSV's file name."""
    return summary_path.name.removeprefix(SUMMARY_PREFIX).removesuffix(
        run_suffix("", timestamp)
    )


def total_returns_path(summary_path: Path) -> Path:
    """Path of the total-returns JSON that accompanies a summary CSV."""
    return summary_path.with_name(
        summary_path.name.replace(
            SUMMARY_PREFIX.rstrip("_"), TOTAL_RETURNS_PREFIX.rstrip("_")
        ).replace(CSV_EXTENSION, JSON_EXTENSION)
    )


def run_manifest_path(out_dir: Path, timestamp: str) -> Path:
    """Path of a run's manifest file."""
    return out_dir / f"{RUN_MANIFEST_PREFIX}{timestamp}{JSON_EXTENSION}"


RUN_MANIFEST_GLOB = f"{RUN_MANIFEST_PREFIX}*{JSON_EXTENSION}"
"""Glob matching every run manifest."""
