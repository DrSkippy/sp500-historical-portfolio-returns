# S&P 500 Historical Portfolio Returns

A backtesting framework that tests three portfolio strategies across the full S&P 500 daily
price history (August 1956 – March 2026, ~17,500 trading days). Strategies are run across
every 3-day-strided start date for holding periods of 1–15 years, producing statistical
distributions of returns rather than point estimates. The same analysis also runs on QQQ
(Nasdaq-100, March 1999 – present).

**Live report:** https://drskippy.github.io/sp500-historical-portfolio-returns/ (S&P 500 / QQQ
switch in the header). See [Deploy the report site](#deploy-the-report-site).

## Strategies

| Strategy | Description |
|---|---|
| **Buy & Hold** | Buy at open, hold to end date, sell |
| **Fractional Kelly** | Periodic stock/bond rebalancing at a fixed allocation |
| **Insurance** | Near-full equity plus crash insurance on the stock: pays a premium, receives the loss beyond a deductible |

### Grid search parameters

Set under `models:` in `config.yaml` (with the stride, capital and year range under `backtest:`):

- **Kelly**: `bond_frac` ∈ {0.10, 0.15, 0.20, 0.25} × `rebalance_period` ∈ {90, 180} days → 8 variants
- **Insurance**: `insurance_frac` ∈ {0.05, 0.10} × `deductible` ∈ {0.09, 0.12, 0.18} → 6 variants
- **Total**: 15 model variants × 15 holding periods = **225 parallel backtest tasks**

## Installation

**Requirements**: Python 3.12+, [Poetry](https://python-poetry.org/)

```bash
git clone <repository-url>
cd sp500-historical-portfolio-returns
poetry install
cp .envrc.example .envrc   # fill in PGPASSWORD etc., then:
direnv allow
```

Database settings (used only by `bin/generate_recent_returns.py` for recent SPY quotes) are read
from the standard PostgreSQL variables `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD` and `PGDATABASE`,
set in `.envrc` (gitignored) and loaded by direnv. There are no defaults in code; a missing
variable raises a clear error. The quotes live in the `stock_quotes` database on the home-lab
PostgreSQL cluster (`192.168.1.91:5434`, table `quotes`).

## Configuration

Everything the backtest is calibrated with lives in `config.yaml`, validated at load time by
Pydantic models in `returns/config.py`: unknown keys and bad values are errors, and relative
paths resolve against the directory holding `config.yaml`. Every section and field is
required: there are no calibration defaults in code to drift from the file. Secrets never go
there — database credentials come from `.envrc`. Logging is configured in `logging.yaml`.

| Section | Contents |
|---|---|
| `datasets` | One entry per price series (see below) |
| `backtest` | Start-date stride (3 days), skip-ahead padding, starting capital, holding periods (1–15 years), histogram bins |
| `models` | The Kelly and Insurance grids, plus the Insurance premium, coverage and loss window |
| `recent_returns` | Daily / weekly / monthly horizons for the recent-returns page |
| `report` | Report output directory and the holding periods whose full distributions are published |
| `monthly_returns` | Settings for `get_monthly_returns.py` |
| `sources` | Interest-rate file, the PostgreSQL quotes namespace, and the Yahoo Finance endpoint for `download_qqq.py` |
| `insurance_scan` | Horizons and grids for the scripts in `notebooks/insurance_scan/` |

### Datasets

`runner.py`, `summarize.py`, `generate_report.py` and `generate_recent_returns.py` take
`--dataset <name>`, selecting an entry under `datasets:` in `config.yaml` (default `sp500`;
also `qqq`). Each entry defines:

| Key | Used by | Meaning |
|---|---|---|
| `price_path` | all | Tab-separated daily price file |
| `price_column` | all | Column traded by the models (`"Adj Close**"` for S&P 500, `"Close*"` for QQQ) |
| `combined_path` | `summarize.py` | Price + interest-rate CSV written as a by-product |
| `out_dir` | `runner.py`, `summarize.py`, `generate_report.py` | Backtest output directory |
| `report_data` | `generate_report.py` | Report JSON written to `trading_strategies_report/data/` |
| `label` | `generate_recent_returns.py` | Display name on the recent-returns page |
| `recent_source` | `generate_recent_returns.py` | `db` (PostgreSQL `quotes` table) or `file` (tail of `price_path`) |
| `recent_symbol` | `generate_recent_returns.py` | Ticker for recent quotes (`SPY`, `QQQ`) |
| `recent_data` | `generate_recent_returns.py` | Recent-returns JSON written to `trading_strategies_report/data/` |


## Usage

All commands use `poetry run` — never invoke `python` directly.

### Run the full backtest

```bash
poetry run python bin/runner.py
```

Dispatches 225 tasks via `multiprocessing.Pool`, one per (years, model) combination.
Each worker loads data independently and writes a CSV to `./out_data/`. Once every task has
succeeded, the run writes a `run_{timestamp}.json` manifest recording the model version
(`MODEL_VERSION` in `returns/models.py`) that produced it, every model variant, and the
`backtest`/`models` config used; a crashed run has no manifest and is never summarized. The
runner refuses to start if two grid variants would share a model name. Warnings go to
`app1.log`; pass `--log-level INFO` (or `DEBUG`) for a per-trade trace, but expect a very large
log (tens to hundreds of GB for a full run). Insurance variants check for losses every trading
day and dominate the runtime: a full S&P 500 run takes about 18 minutes on 24 cores, QQQ about 5.

### Generate summary statistics

Run after the backtest to aggregate results:

```bash
poetry run python bin/summarize.py [--run 2026-10-07_1550]
```

Summarizes the newest run produced by the current model version — runs from older model
versions, or without a manifest, are ignored — or the run named with `--run`. Produces
per-model summary CSVs and JSON files in `./out_data/`, and rewrites the dataset's
`combined_path` CSV.

### Generate the report data

Run after summarize.py to build the static report data file:

```bash
poetry run python bin/generate_report.py [--run 2026-10-07_1550]
```

Reads one run's `out_dir/summary_*.csv` and `out_dir/total_returns_*.json` files and writes
`trading_strategies_report/data/report_data.json` (~8 MB). The run is chosen as for
`summarize.py` (newest of the current model version, or `--run`); summaries from every other
run are ignored, so old runs can stay in `out_data/` without leaking into the report. It
stops with an error if the run's summaries don't cover exactly the models its manifest lists.

### Generate the recent-returns data

```bash
poetry run python bin/generate_recent_returns.py
```

Computes the historical daily/weekly/monthly return distributions and ranks the most recent
returns against them, writing `trading_strategies_report/data/recent_returns_data.json`. For
`sp500`, recent SPY quotes come from PostgreSQL (`recent_source: db`), so the `PG*` variables
must be set in `.envrc`.

### View the report locally

```bash
cd trading_strategies_report && python3 -m http.server 8080
```

Open `http://localhost:8080`. The site has six interactive sections (overview table, return
curves, risk over time, distribution explorer, risk/return scatter, investment advice), a
recent-returns page (`recent_returns.html`), and static strategy description pages for each
of the three strategy families. Add `?dataset=qqq` to either page for QQQ.

### Refresh everything

```bash
for ds in sp500 qqq; do
  poetry run python bin/runner.py --dataset $ds
  poetry run python bin/summarize.py --dataset $ds
  poetry run python bin/generate_report.py --dataset $ds
  poetry run python bin/generate_recent_returns.py --dataset $ds
done
```

Then [deploy](#deploy-the-report-site).

### Deploy the report site

The site is published on GitHub Pages from an orphan **`gh-pages`** branch that holds only the
contents of `trading_strategies_report/`, including the generated `data/*.json` files (which
are gitignored on `main`). All site paths are relative, so it works unchanged under the
`/sp500-historical-portfolio-returns/` project path. Pushing to `gh-pages` triggers a Pages
rebuild (about a minute).

After regenerating the report and recent-returns data for every dataset:

```bash
git worktree add /tmp/gh-pages gh-pages
cp -r trading_strategies_report/. /tmp/gh-pages/
cd /tmp/gh-pages
git add -A && git commit -m "Update report data" && git push origin gh-pages
cd - && git worktree remove /tmp/gh-pages
```

The branch keeps a `.nojekyll` file so GitHub serves the files as-is. Check the build with
`gh api repos/DrSkippy/sp500-historical-portfolio-returns/pages/builds/latest`.

### Run tests and code-quality checks

```bash
poetry run pytest --cov=returns --cov-report=term-missing tests/
poetry run black --check .
poetry run mypy                 # strict mode; covers returns/, bin/ and tests/ (see pyproject.toml)
```

124 tests, ~96% coverage over `returns/` and `bin/`. `black` and `mypy --strict` must both pass
before merge.

`tests/test_golden_master.py` runs the whole pipeline on synthetic data and compares it with
`tests/golden/pipeline_snapshot.json`, so a refactor that changes any result fails. When a
change is *meant* to change results, regenerate the snapshot in the same commit:

```bash
UPDATE_GOLDEN=1 poetry run pytest tests/test_golden_master.py
```

### Compute 30-day rolling returns

```bash
poetry run python bin/get_monthly_returns.py [--dataset qqq] [--no-plot]
```

Calculates `(current - prior) / current` over a 30-day offset across the full price history,
logs a sample and summary, shows a histogram (skip it with `--no-plot`) and writes
`out_data/monthly_returns.csv`.

### Update SP500 data

`data/SP500.tab` is updated by hand; until it is, rerunning the S&P 500 backtest reproduces the
previous results. Copy the new rows from the
[Seeking Alpha historical quotes page](https://seekingalpha.com/symbol/SP500/historical-price-quotes)
into a text file, then:

```bash
poetry run python bin/transform_new_sp500_records.py < new_rows.txt
```

The script reads the pasted rows on stdin and prints them in `.tab` format; prepend the output
to `data/SP500.tab` (newest rows go first).

### Run the analysis on QQQ (Nasdaq-100)

The pipeline can run against any dataset defined under `datasets:` in `config.yaml`
(`sp500` is the default). To repeat the full analysis on QQQ:

```bash
poetry run python bin/download_qqq.py               # data/QQQ.tab from Yahoo Finance (Mar 1999 – today)
poetry run python bin/runner.py --dataset qqq       # writes ./out_data/qqq/
poetry run python bin/summarize.py --dataset qqq    # also writes data/combined_qqq_interest_data.csv
poetry run python bin/generate_report.py --dataset qqq  # writes report_data_qqq.json
poetry run python bin/generate_recent_returns.py --dataset qqq  # writes recent_returns_data_qqq.json
```

View it at `http://localhost:8080/?dataset=qqq` and `recent_returns.html?dataset=qqq` (both
headers have an S&P 500 / QQQ switch), then [deploy](#deploy-the-report-site). For QQQ, the
recent-returns page uses the tail of `data/QQQ.tab` (`recent_source: file`) instead of
PostgreSQL, so re-run `download_qqq.py` to refresh it.
QQQ uses the split-adjusted `Close*` column (price return, no dividends), matching the
S&P 500 price-index methodology; set `price_column: "Adj Close**"` to include dividends.

## Project structure

```
sp500-historical-portfolio-returns/
├── returns/
│   ├── models.py              # BuyHoldModel, KellyModel, InsuranceModel (+ InsurancePolicy)
│   ├── backtest.py            # Typed model specs, the configured grid, model_tester
│   ├── types.py               # PriceBar, Trade, WindowReturn, ReturnStats records
│   ├── config.py              # Pydantic schema + loader for config.yaml
│   ├── errors.py              # Package exceptions
│   ├── logging_setup.py       # Logging from logging.yaml
│   ├── prices.py              # Price + interest loading and combination
│   ├── runs.py                # Run manifests and each run's files
│   ├── summaries.py           # Per-model summary CSV / total-returns JSON
│   ├── naming.py              # Date formats and output file names
│   ├── io_utils.py            # TSV reading, compact JSON writing
│   ├── cli.py                 # Shared --dataset / --run options
│   ├── finance.py             # Return arithmetic
│   ├── analysis.py            # Aggregation and statistics
│   ├── plotting.py            # Matplotlib plots (notebooks)
│   ├── db.py                  # PostgreSQL access for recent quotes (PG* env vars)
│   └── monthly_returns.py     # 30-day rolling return series
├── bin/
│   ├── runner.py              # Main backtest entry point
│   ├── summarize.py           # Post-process backtest output
│   ├── generate_report.py     # Build report_data*.json for the report site
│   ├── generate_recent_returns.py  # Build recent_returns_data*.json
│   ├── get_monthly_returns.py # Rolling returns analysis
│   ├── transform_new_sp500_records.py  # Data ingestion helper
│   └── download_qqq.py        # Download QQQ history to data/QQQ.tab
├── tests/
│   ├── conftest.py            # load_bin_module, synthetic project fixture
│   ├── golden/                # pipeline_snapshot.json for the golden-master test
│   ├── test_golden_master.py  # end-to-end pipeline vs snapshot (refactors must not change it)
│   ├── test_scripts.py        # bin/ entry points on a synthetic project
│   ├── test_generate_report.py
│   ├── test_generate_recent_returns.py
│   ├── test_config.py
│   ├── test_model_names.py
│   ├── test_model_class.py
│   ├── test_kelly_model_class.py
│   ├── test_insurance_class.py
│   ├── test_insurance_policy.py   # insurance payout/premium semantics ($12 cash / $1000 asset)
│   ├── test_analysis.py
│   ├── test_data.py
│   ├── test_db.py
│   ├── test_download_qqq.py
│   ├── test_monthly_returns.py
│   └── test_backtest.py       # model_tester early exit vs full scan; model specs
├── data/
│   ├── SP500.tab              # Daily OHLCV + Adj Close (Aug 1956 – Mar 2026)
│   ├── QQQ.tab                # QQQ daily OHLCV, same layout (Mar 1999 – )
│   └── interest.tab           # Annual interest rates (bond return proxy)
├── out_data/                  # Backtest output, S&P 500 (generated, not committed)
│   └── qqq/                   # Backtest output, QQQ
├── trading_strategies_report/ # Static HTML/JS report site (deployed via gh-pages)
│   ├── index.html             # Single-page interactive report (Chart.js)
│   ├── recent_returns.html    # Recent returns vs historical distribution
│   ├── css/style.css
│   ├── js/                    # app.js, charts.js, recent_returns_app.js
│   ├── strategies/            # buy-hold.html, kelly.html, insurance.html
│   └── data/                  # report_data*.json, recent_returns_data*.json (generated, not committed)
├── docs/
│   └── insurance_parameter_scan.md  # Insurance premium/deductible/coverage scan vs Kelly
├── notebooks/                 # Exploratory notebooks; insurance_scan/ holds the scan scripts + results
├── .claude/agents/
│   └── test-runner.md         # Claude Code subagent that runs the test suite
├── config.yaml                # Datasets and all backtest/model/report calibration
├── logging.yaml               # Logging configuration for bin/ scripts
├── .envrc.example             # PG* database variables template (copy to .envrc)
└── pyproject.toml             # Dependencies plus black and mypy (strict) settings
```

## Data

**`data/SP500.tab`** — tab-separated daily prices, ~17,500 rows
- Source: https://seekingalpha.com/symbol/SP500/historical-price-quotes
- Columns: `Date`, `Open`, `High`, `Low`, `Close*`, `Adj Close**`, `Volume`
- Dates in `"%b %d, %Y"` format; numbers may contain comma thousands separators

**`data/QQQ.tab`** — QQQ daily prices in the same layout, ~6,900 rows
- Source: Yahoo Finance chart API (`bin/download_qqq.py`)
- `Close*` is split-adjusted; `Adj Close**` is split- and dividend-adjusted

**`data/interest.tab`** — annual interest rates (FRED GS1 series), one row per year
- Source: FRED GS1 — Market Yield on U.S. Treasury Securities at 1-Year Constant Maturity, Quoted on an Investment Basis
- Columns: `observation_date`, `GS1`
- Date format: `YYYY-01-01`; values are plain percentages (e.g. `1.05` = 1.05% annual yield)
- Used as the bond/cash return proxy in Kelly and Insurance models

**Output files** (written to the dataset's `out_dir`: `./out_data/` or `./out_data/qqq/`):
- `run_{timestamp}.json` — run manifest: model version, dataset, holding periods, model names and the `backtest`/`models` config, written when the run completes (`runner.py`)
- `returns_{years}_{model_name}_{timestamp}.csv` — per-start-date results (`runner.py`)
- `summary_{model_name}_{timestamp}.csv` — aggregated stats (mean, median, stdev, mode, fraction losing) (`summarize.py`)
- `total_returns_{model_name}_{timestamp}.json` — full return distribution for histogram plots (`summarize.py`)

## Strategy details

### Buy & Hold

Buys the index with all capital at the first data point inside the window, holds, then sells
at the end. Baseline for comparison.

### Fractional Kelly (`KellyModel`)

Maintains a target `stock_frac = 1 - bond_frac` allocation. Every `rebalance_period` days
it rebalances back to target, applying daily compounding interest to the cash/bond position.

### Insurance (`InsuranceModel`)

**The policy insures the stock, not the cash.** The portfolio holds `1 − ins_frac` in stock
and keeps `ins_frac` as a cash reserve that earns the market interest rate and pays the
premium. Both are rebalanced back to target every `insurance_period` days.

- **Premium**: `premium_rate` per year of the insured stock value, charged daily from cash
  (configured at 1.2%/yr, i.e. $1/month per $1,000 insured).
- **Trigger**: the price falls by at least `insurance_deductible` (tested values: 9%, 12%, 18%)
  over a rolling 6-day window (`loss_window_days`).
- **Payout**: the loss beyond the deductible on the insured stock, paid into cash:

  ```
  insured_value = shares × price at the start of the loss window
  payout        = coverage_ratio × insured_value × (|loss_fraction| − deductible)
  ```

  Example: $1,000 of stock falls to $250 (75%) with an 18% deductible →
  payout = 1000 × (0.75 − 0.18) = **$570**, whatever the size of the cash reserve.
- A rebalance follows the payout the same day and the price history resets. A policy pays
  out at most once; it is renewed at the next scheduled rebalance.

Parameters live under `models.insurance` in `config.yaml`.

A scan of premium, deductible and coverage against the best Kelly variant, with an assessment
of which settings are realistic, is in [docs/insurance_parameter_scan.md](docs/insurance_parameter_scan.md).

## Statistical output

For each (model, holding period) combination the framework computes:

| Metric | Description |
|---|---|
| Mean / Median returns | Central tendency of fractional and annualised returns |
| Standard deviation | Volatility across start dates |
| Mode | Centre of the most populated histogram bin (45 bins) |
| Fraction losing | Share of start dates that ended with a loss |
| Yearly compound rate | Geometric annualised return |

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `numpy` | ^2.5 | Numerical arrays and statistics |
| `pandas` | ^3.0 | DataFrames and time-series handling |
| `matplotlib` | ^3.11 | Plotting |
| `seaborn` | ^0.13 | Statistical visualisation in notebooks (`notebook` group) |
| `requests` | ^2.34 | Yahoo Finance HTTP calls |
| `pyyaml` | ^6.0 | Config file loading |
| `pydantic` | ^2.13 | Config validation |
| `psycopg[binary]` | ^3.3 | PostgreSQL access for recent quotes |
| `pytest` | ^9.1 | Test framework (`dev` group) |
| `pytest-cov` | ^7.1 | Coverage reporting (`dev` group) |
| `black` | ^26.5 | Code formatter (`dev` group) |
| `mypy` | ^2.4 | Static type checking, strict mode (`dev` group) |
| `pandas-stubs`, `types-requests`, `types-pyyaml` | — | Type stubs for mypy (`dev` group) |
| `notebook` | ^7.6 | Exploratory notebooks (`notebook` group) |
