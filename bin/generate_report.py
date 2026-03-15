"""Generate report_data.json for the trading strategies static report site.

Reads all out_data/summary_*.csv and out_data/total_returns_*.json files,
merges them, and writes trading_strategies_report/data/report_data.json.

Usage:
    poetry run python bin/generate_report.py
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT_DATA = ROOT / "out_data"
REPORT_DATA_DIR = ROOT / "trading_strategies_report" / "data"
OUTPUT_PATH = REPORT_DATA_DIR / "report_data.json"

# Only include these years in distribution data to keep JSON manageable
DIST_YEARS = {"1", "5", "10", "15"}


def parse_model_name(name: str) -> tuple[str, dict]:
    """Return (family, params) from a model name string."""
    if name == "Buy_Hold":
        return "buy_hold", {}
    if name.startswith("Fractional_Kelly_"):
        # Fractional_Kelly_{bond_frac}_{rebalance}
        parts = name.split("_")
        return "kelly", {
            "bond_frac": float(parts[2]),
            "rebalance": int(parts[3]),
        }
    if name.startswith("Insurance_"):
        # Insurance_{ins_frac}_{deductible}_{rebalance}
        parts = name.split("_")
        return "insurance", {
            "ins_frac": float(parts[1]),
            "deductible": float(parts[2]),
            "rebalance": int(parts[3]),
        }
    return "unknown", {}


def load_summary(csv_path: Path) -> tuple[str, list[dict]]:
    """Load a summary CSV and return (model_name, list-of-year-dicts)."""
    rows = []
    model_name = None
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            model_name = row["model_name"]
            rows.append(
                {
                    "year": int(float(row["time_span"])),
                    "mean_total": float(row["mean_total_returns"]),
                    "mean_yearly": float(row["mean_yearly_compound_returns"]),
                    "median_total": float(row["median_total_returns"]),
                    "median_yearly": float(row["median_yearly_returns"]),
                    "sdev_total": float(row["sdev_total_returns"]),
                    "sdev_yearly": float(row["sdev_yearly_returns"]),
                    "fraction_losing": float(row["fraction_losing_starts"]),
                    "mode_total": float(row["mode_total_returns"]),
                    "mode_yearly": float(row["mode_yearly_returns"]),
                    "sample_size": int(row["sample_size"]),
                }
            )
    rows.sort(key=lambda r: r["year"])
    return model_name, rows  # type: ignore[return-value]


def load_distributions(json_path: Path) -> dict[str, list[float]]:
    """Load total_returns JSON and return only DIST_YEARS keys."""
    with json_path.open() as f:
        data: dict[str, list[float]] = json.load(f)
    return {k: v for k, v in data.items() if k in DIST_YEARS}


def find_latest_files() -> dict[str, tuple[Path, Path]]:
    """Find the most recent summary + total_returns file pair per model.

    Returns mapping: model_name -> (summary_path, total_returns_path)
    Multiple runs may exist; pick the file with the latest timestamp suffix.
    """
    # Pattern: summary_{model_name}_{date}_{time}.csv
    summary_pattern = re.compile(r"^summary_(.+)_\d{4}-\d{2}-\d{2}_\d{4}\.csv$")
    total_pattern = re.compile(
        r"^total_returns_(.+)_\d{4}-\d{2}-\d{2}_\d{4}\.json$"
    )

    summaries: dict[str, Path] = {}
    totals: dict[str, Path] = {}

    for p in OUT_DATA.iterdir():
        m = summary_pattern.match(p.name)
        if m:
            model = m.group(1)
            # Keep latest (lexicographic on timestamp suffix is correct)
            if model not in summaries or p.name > summaries[model].name:
                summaries[model] = p

        m = total_pattern.match(p.name)
        if m:
            model = m.group(1)
            if model not in totals or p.name > totals[model].name:
                totals[model] = p

    models_found = set(summaries) & set(totals)
    if len(models_found) == 0:
        print("ERROR: No matching summary/total_returns file pairs found.", file=sys.stderr)
        sys.exit(1)

    return {m: (summaries[m], totals[m]) for m in models_found}


def build_report_data(file_map: dict[str, tuple[Path, Path]]) -> dict:
    """Build the full report data structure."""
    models = []

    for model_name in sorted(file_map):
        summary_path, total_path = file_map[model_name]
        family, params = parse_model_name(model_name)
        _, summary_rows = load_summary(summary_path)
        distributions = load_distributions(total_path)

        models.append(
            {
                "name": model_name,
                "family": family,
                "params": params,
                "summary": summary_rows,
                "distributions": distributions,
            }
        )

    return {"models": models}


def main() -> None:
    REPORT_DATA_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Scanning {OUT_DATA} for model files...")
    file_map = find_latest_files()
    print(f"Found {len(file_map)} model(s): {', '.join(sorted(file_map))}")

    print("Building report data...")
    report = build_report_data(file_map)

    print(f"Writing {OUTPUT_PATH}...")
    with OUTPUT_PATH.open("w") as f:
        json.dump(report, f, separators=(",", ":"))

    size_mb = OUTPUT_PATH.stat().st_size / 1_048_576
    print(f"Done. {OUTPUT_PATH} ({size_mb:.1f} MB, {len(report['models'])} models)")


if __name__ == "__main__":
    main()
