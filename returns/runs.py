"""Backtest runs: manifests, run selection and each run's output files."""

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from returns.errors import IncompleteRunError, NoMatchingRunError, NoModelOutputsError
from returns.naming import (
    RUN_MANIFEST_GLOB,
    run_manifest_path,
    run_returns_glob,
    run_summary_glob,
    summary_model_name,
    total_returns_path,
)

logger = logging.getLogger(__name__)


class RunManifest(BaseModel):
    """What produced one backtest run; written by runner.py as ``run_{timestamp}.json``.

    runner.py writes it only after every task has succeeded, so a manifest marks a
    complete run.
    """

    timestamp: str
    """Run id, also the suffix of every output file name (``YYYY-MM-DD_HHMM``)."""
    model_version: int
    dataset: str
    years: list[int]
    model_count: int
    model_names: list[str] = Field(default_factory=list)
    """Every model variant in the run (empty in manifests from before 2026-10-09)."""
    parameters: dict[str, Any] = Field(default_factory=dict)
    """The ``backtest`` and ``models`` config the run used, including parameters
    the model names don't encode (premium rate, coverage, loss window)."""


def write_run_manifest(out_dir: Path, manifest: RunManifest) -> Path:
    """Write a run's manifest next to its output files."""
    path = run_manifest_path(out_dir, manifest.timestamp)
    path.write_text(manifest.model_dump_json(indent=1) + "\n")
    return path


def find_runs(out_dir: Path) -> list[RunManifest]:
    """All runs with a manifest in ``out_dir``, oldest first."""
    manifests = [
        RunManifest.model_validate_json(path.read_text())
        for path in out_dir.glob(RUN_MANIFEST_GLOB)
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
    return sorted(out_dir.glob(run_returns_glob(timestamp)))


def run_summary_files(out_dir: Path, run: RunManifest) -> dict[str, tuple[Path, Path]]:
    """The summary CSV and total-returns JSON of every model in one run.

    Only files carrying the run's timestamp are considered, so summaries left over
    from other runs (e.g. a model since removed from the grid, or an older model
    version) can never be mixed in.

    Args:
        out_dir: Dataset output directory.
        run: The run, from ``select_run``.

    Returns:
        ``model_name -> (summary_path, total_returns_path)``.

    Raises:
        NoModelOutputsError: If the run has no summaries (summarize.py not run).
        IncompleteRunError: If a summary lacks its JSON, or the models summarized
            differ from those the manifest lists.
    """
    files: dict[str, tuple[Path, Path]] = {}
    for summary_path in sorted(out_dir.glob(run_summary_glob(run.timestamp))):
        model_name = summary_model_name(summary_path, run.timestamp)
        json_path = total_returns_path(summary_path)
        if not json_path.exists():
            raise IncompleteRunError(f"{summary_path} has no {json_path.name}")
        files[model_name] = (summary_path, json_path)
    if not files:
        raise NoModelOutputsError(
            f"No summaries for run {run.timestamp} in {out_dir}; run bin/summarize.py"
        )
    if run.model_names:
        missing = sorted(set(run.model_names) - set(files))
        unexpected = sorted(set(files) - set(run.model_names))
        if missing or unexpected:
            raise IncompleteRunError(
                f"Run {run.timestamp} summaries don't match its manifest: "
                f"missing {missing}, unexpected {unexpected}; re-run bin/summarize.py"
            )
    elif len(files) != run.model_count:
        raise IncompleteRunError(
            f"Run {run.timestamp} has {len(files)} summaries, expected "
            f"{run.model_count}; re-run bin/summarize.py"
        )
    return files
