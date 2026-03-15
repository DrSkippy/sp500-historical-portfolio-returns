# S&P 500 Historical Portfolio Returns

A backtesting framework that tests three portfolio strategies across the full S&P 500 daily
price history (August 1956 – March 2026, ~17,500 trading days). Strategies are run across
every 3-day-strided start date for holding periods of 1–15 years, producing statistical
distributions of returns rather than point estimates.

## Strategies

| Strategy | Description |
|---|---|
| **Buy & Hold** | Buy at open, hold to end date, sell |
| **Fractional Kelly** | Periodic stock/bond rebalancing at a fixed allocation |
| **Insurance** | Kelly variant with loss-triggered insurance payouts |

### Grid search parameters

- **Kelly**: `bond_frac` ∈ {0.10, 0.15, 0.20, 0.25} × `rebalance_period` ∈ {90, 180} days → 8 variants
- **Insurance**: `insurance_frac` ∈ {0.05, 0.10} × `deductible` ∈ {0.09, 0.12, 0.18} → 6 variants
- **Total**: 15 model variants × 15 holding periods = **225 parallel backtest tasks**

## Installation

**Requirements**: Python 3.12+, [Poetry](https://python-poetry.org/)

```bash
git clone <repository-url>
cd sp500-historical-portfolio-returns
poetry install
```

## Usage

All commands use `poetry run` — never invoke `python` directly.

### Run the full backtest

```bash
poetry run python bin/runner.py
```

Dispatches 225 tasks via `multiprocessing.Pool`, one per (years, model) combination.
Each worker loads data independently and writes a CSV to `./out_data/`. Logs go to `app1.log`.
Runtime is typically 15–30 minutes depending on core count.

### Generate summary statistics

Run after the backtest to aggregate results:

```bash
poetry run python bin/summarize.py
```

Produces per-model summary CSVs and JSON files in `./out_data/`.

### Generate the report site

Run after summarize.py to build the static report data file:

```bash
poetry run python bin/generate_report.py
```

Reads all `out_data/summary_*.csv` and `out_data/total_returns_*.json` files and writes
`trading_strategies_report/data/report_data.json` (~8 MB). To view the report locally:

```bash
cd trading_strategies_report && python3 -m http.server 8080
```

Open `http://localhost:8080`. The site has six interactive sections (overview table, return
curves, risk over time, distribution explorer, risk/return scatter, investment advice) plus
static strategy description pages for each of the three strategy families.

### Run tests

```bash
poetry run pytest --cov=returns --cov-report=term-missing tests/
```

43 tests, ~72% coverage. Or use the Ollama-powered test agent (see below).

### Compute 30-day rolling returns

```bash
poetry run python bin/get_monthly_returns.py
```

Calculates `(current - prior) / current` over a 30-day offset across the full price history.

### Update SP500 data

```bash
poetry run python bin/transform_new_sp500_records.py
```

Transforms newly downloaded SP500 records into the `.tab` format used by the data loader.

## Test agent (Ollama-powered)

`bin/test_agent.py` runs pytest and, on any failure, queries a local Ollama LLM for a
structured analysis of root causes and suggested fixes.

```bash
# Run tests + Ollama analysis on failure
poetry run python bin/test_agent.py

# Use a lighter model
poetry run python bin/test_agent.py --model gemma3:latest

# Target specific tests
poetry run python bin/test_agent.py --pytest-args "-k test_data"

# Just pytest, skip LLM
poetry run python bin/test_agent.py --no-analysis
```

The agent is also available as a Claude Code subagent (`.claude/agents/test-runner.md`) and
can be invoked by Claude automatically when asked to run or investigate tests.

Configuration is in `config.yaml`:

```yaml
test_agent:
  ollama_base_url: "http://192.168.1.90:11434"
  model: "phi4:latest"
  max_context_chars: 8000
```

## Project structure

```
sp500-historical-portfolio-returns/
├── returns/
│   ├── models.py              # Model, KellyModel, InsuranceModel
│   ├── data.py                # Data loading and combination
│   ├── analysis.py            # Aggregation and statistics
│   └── monthly_returns.py     # 30-day rolling return series
├── bin/
│   ├── runner.py              # Main backtest entry point
│   ├── summarize.py           # Post-process backtest output
│   ├── generate_report.py     # Build report_data.json for the report site
│   ├── get_monthly_returns.py # Rolling returns analysis
│   ├── transform_new_sp500_records.py  # Data ingestion helper
│   └── test_agent.py          # Ollama-powered test runner
├── tests/
│   ├── test_model_class.py
│   ├── test_kelly_model_class.py
│   ├── test_insurance_class.py
│   ├── test_analysis.py
│   ├── test_data.py
│   └── test_monthly_returns.py
├── data/
│   ├── SP500.tab              # Daily OHLCV + Adj Close (Aug 1956 – Mar 2026)
│   └── interest.tab           # Annual interest rates (bond return proxy)
├── out_data/                  # Backtest output (generated, not committed)
├── trading_strategies_report/ # Static HTML/JS report site
│   ├── index.html             # Single-page interactive report (Chart.js)
│   ├── css/style.css
│   ├── js/                    # app.js, charts.js
│   ├── strategies/            # buy-hold.html, kelly.html, insurance.html
│   └── data/                  # report_data.json (generated, not committed)
├── notebooks/                 # Exploratory Jupyter notebooks
├── .claude/agents/
│   └── test-runner.md         # Claude Code subagent definition
├── config.yaml                # Test agent and Ollama settings
└── pyproject.toml
```

## Data

**`data/SP500.tab`** — tab-separated daily prices, ~17,500 rows
- Source: https://seekingalpha.com/symbol/SP500/historical-price-quotes
- Columns: `Date`, `Open`, `High`, `Low`, `Close*`, `Adj Close**`, `Volume`
- Dates in `"%b %d, %Y"` format; numbers may contain locale-formatted commas

**`data/interest.tab`** — annual interest rates (FRED GS1 series), one row per year
- Source: FRED GS1 — Market Yield on U.S. Treasury Securities at 1-Year Constant Maturity, Quoted on an Investment Basis
- Columns: `observation_date`, `GS1`
- Date format: `YYYY-01-01`; values are plain percentages (e.g. `1.05` = 1.05% annual yield)
- Used as the bond/cash return proxy in Kelly and Insurance models

**Output files** (written to `./out_data/` by the backtest runner):
- `returns_{years}_{model_name}_{timestamp}.csv` — per-start-date results
- `summary_{suffix}.csv` — aggregated stats (mean, median, stdev, mode, fraction losing)
- `total_returns_{suffix}.json` — full return distribution for histogram plots

## Strategy details

### Buy & Hold

Buys all available capital in S&P 500 shares at the first data point inside the window,
holds, then sells at the end. Baseline for comparison.

### Fractional Kelly (`KellyModel`)

Maintains a target `stock_frac = 1 - bond_frac` allocation. Every `rebalance_period` days
it rebalances back to target, applying daily compounding interest to the cash/bond position.

### Insurance (`InsuranceModel`)

Extends Kelly with a rolling 6-day price window. If the price drops more than
`insurance_deductible` (tested values: 9%, 12%, 18%) over that window, an insurance payout fires:

```
reserve = reserve × |loss_fraction| × payout_factor   # payout_factor = 10
```

The reserve (the `ins_frac` portion of the portfolio) replaces its value with a leveraged
multiple of the loss. A rebalance follows every payout, and the price history resets.

## Statistical output

For each (model, holding period) combination the framework computes:

| Metric | Description |
|---|---|
| Mean / Median returns | Central tendency of fractional and annualised returns |
| Standard deviation | Volatility across start dates |
| Mode | Histogram-estimated peak of the return distribution |
| Fraction losing | Share of start dates that ended with a loss |
| Yearly compound rate | Geometric annualised return |

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `numpy` | ^1.26 | Numerical arrays and statistics |
| `pandas` | ^2.1 | DataFrames and time-series handling |
| `matplotlib` | ^3.8 | Plotting |
| `seaborn` | ^0.13 | Statistical visualisation |
| `pydantic` | ^2.12 | LLM response validation, data schemas |
| `requests` | ^2.32 | Ollama HTTP API calls |
| `pyyaml` | ^6.0 | Config file loading |
| `pytest` | ^7.4 | Test framework |
| `pytest-cov` | ^7.0 | Coverage reporting |
| `jupyter` / `notebook` | ^7.0 | Exploratory notebooks |
