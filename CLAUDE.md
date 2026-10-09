# CLAUDE.md

## Project: sp500-historical-portfolio-returns

Backtests three portfolio strategies (Buy&Hold, KellyModel, InsuranceModel) across the full
S&P 500 daily price history, and the same analysis on QQQ. Datasets are defined under
`datasets:` in `config.yaml` and selected with `--dataset`. The core module is `returns/`.
Scripts live in `bin/`.

### Running tests and checks

```bash
poetry run pytest --cov=returns --cov=bin --cov-report=term-missing tests/   # fails under 90%
poetry run black --check .
poetry run mypy            # strict; covers returns/, bin/, tests/, notebooks/insurance_scan/
```

Coverage below 90% fails the run (`[tool.coverage.report] fail_under` in pyproject.toml).
Log with %-style arguments (`logger.info("x = %s", x)`), never f-strings: the backtest calls
the model loggers millions of times and f-strings format even when the level is off.

Tests live in `tests/` (with an `s`). Use `poetry run python ...` — never bare `python`.
Use explicit imports, not `from x import *` (strict mypy can't follow star imports).

### Report deployment

The report site (`trading_strategies_report/`) is published to GitHub Pages at
https://drskippy.github.io/sp500-historical-portfolio-returns/ from an orphan `gh-pages` branch
holding only the site plus its generated `data/*.json` (gitignored on `main`). See
"Deploy the report site" in README.md for the commands. Generated data files stay off `main`;
only `gh-pages` carries them.

### Testing principles

- **No I/O outside `tmp_path`.** Data functions take explicit paths or a `Dataset`; build a
  config with `load_config(tmp_path / "config.yaml")` (or the `synthetic_config` fixture in
  `tests/conftest.py`) rather than monkeypatching module state. Import `bin/` scripts with
  `tests.conftest.load_bin_module`.
- **Synthetic data only.** Build minimal fixture rows rather than loading real data files.
- **Golden master.** `tests/test_golden_master.py` runs the whole pipeline on synthetic data and
  compares against `tests/golden/pipeline_snapshot.json`. Refactors must not change it; for an
  intentional result change, regenerate with `UPDATE_GOLDEN=1 poetry run pytest
  tests/test_golden_master.py` in the same commit, **bump `MODEL_VERSION`** in
  `returns/models.py`, and say why in the message. `summarize.py` and `generate_report.py`
  only process runs whose `run_{timestamp}.json` manifest carries the current
  `MODEL_VERSION`, and the report reads only the selected run's summaries
  (`returns.runs.run_summary_files`), so old runs can't leak into the report. `runner.py`
  writes the manifest after all tasks succeed, so a crashed run is never selected.
- **Test edge cases explicitly.** Known sharp edges in this codebase:
  - `calculate_mode` (`analysis.py`): `np.histogram` returns bin *edges* (one more than the
    counts); bin `i` spans `edges[i]..edges[i+1]`. The mode is that bin's centre. (Before
    2026-10-07 it used `edges[i-1]`, one bin low and wrapping at `i == 0`.)
  - Model names: `model_name` is a read-only property derived from the constructor
    parameters (it once accumulated across the ~5,800 `model_config()` calls per run when a
    `+=` crept in). Names are written to output files and parsed back by `parse_model_name`
    (which raises `ModelNameError` on anything it can't parse); keep `format_*_name` and it
    in sync. Floats are formatted losslessly (`repr`), and `runner.unique_model_names`
    refuses a grid whose variants would share a name (and overwrite each other's files).
  - `InsuranceModel` insures the **stock, not the cash**: payout = `coverage_ratio ×
    insured_value × (|loss| − deductible)` into cash; premium = `premium_rate` × insured stock
    value per year, charged daily; at most one payout per policy period. Worked example
    ($12 cash, $1,000 stock → $250 pays $570) is pinned in `tests/test_insurance_policy.py`.
- **Prefer `pytest`-style functions and fixtures** over `unittest.TestCase` for new tests.
  Use `TestCase` only when extending an existing suite that already uses it.

### Parallelism & performance

- All work is **CPU-bound math** — `async`/`await` gives no benefit here. Use `multiprocessing`.
- The runner (`bin/runner.py`) dispatches **225 tasks** (15 years × 15 model variants) via
  `mp.Pool().starmap`, saturating all cores. Each worker loads data independently to avoid
  pickling ~17 K rows per task.
- **Bisect for sorted data:** the daily price list is sorted by date. Use `bisect.bisect_left`
  to jump to the start of each test window instead of a linear scan with `continue`. Pre-compute
  `dates = [d[0] for d in data]` once outside the while loop.
- When adding new strategies, add a model class (a `PortfolioModel` subclass) and a frozen
  `*Spec` dataclass with a `build()` method in `returns/backtest.py`, add it to the
  `ModelSpec` union and yield its variants from `all_model_specs()` (grid values come from
  `models:` in `config.yaml`) — the parallelism scales automatically.

### Configuration

All calibration lives in `config.yaml`, validated by Pydantic models in `returns/config.py`
(unknown keys are errors; relative paths resolve against the config file's directory):
`datasets`, `backtest` (stride, capital, year range, histogram bins), `models` (Kelly and
Insurance grids and insurance parameters), `recent_returns`, `report`, `monthly_returns`,
`sources` (incl. the Yahoo endpoint), `insurance_scan` (notebook scan grids). Logging is
configured from `logging.yaml` via `returns.logging_setup`.

**No calibration defaults in code.** Every config field is required, and model
constructors, `model_tester`, `aggregate_returns`, `MonthlyReturns` etc. take their
parameters explicitly — pass them from the loaded `AppConfig`. Tests use the pinned
`SETTINGS_YAML` and the `make_buy_hold` / `make_kelly` / `make_insurance` factories in
`tests/conftest.py`.

### Module layout

```
returns/
  models.py          # PortfolioModel (abstract), BuyHoldModel, RebalancingModel, KellyModel,
                     #   InsuranceModel + InsurancePolicy; model-name format/parse, ModelFamily
  backtest.py        # ModelSpec (BuyHoldSpec/KellySpec/InsuranceSpec), all_model_specs,
                     #   unique_model_names, build_model, model_tester
  types.py           # PriceBar, Trade, WindowReturn, ReturnStats (NamedTuples; CSV headers), Row
  config.py          # Pydantic AppConfig + load_config (config.yaml)
  errors.py          # ReturnsError and subclasses
  prices.py          # load_dataset -> Dataset, get_price_data, get_interest_data, get_combined_data
  runs.py            # RunManifest, write_run_manifest, select_run, run_returns_files, run_summary_files
  summaries.py       # read_run_returns -> WindowReturn rows, create_summary_file(s), read_summary_data
  naming.py          # Date formats and every output file name (returns_/summary_/total_returns_/run_)
  io_utils.py        # read_tsv (file:line errors), write_compact_json, log_rows_read
  cli.py             # add_dataset_argument / add_run_argument for bin/ scripts
  finance.py         # simple_return
  db.py              # PostgreSQL access (get_db_settings, get_quotes); settings from .envrc PG* vars
  analysis.py        # aggregate_returns, calculate_mode, get_aggregate_returns_by_period
  plotting.py        # matplotlib plots (kept out of analysis so pool workers never import pyplot)
  monthly_returns.py # MonthlyReturns (30-day rolling returns, formula: (cur-prior)/cur)
  logging_setup.py   # configure_logging from logging.yaml
bin/
  runner.py                  # Backtest entry point: model_test_worker over all_model_specs x years
  summarize.py               # Aggregate backtest CSVs into summary_*.csv / total_returns_*.json
  generate_report.py         # Build trading_strategies_report/data/report_data*.json
  generate_recent_returns.py # Build recent_returns_data*.json (SPY from PostgreSQL, QQQ from file)
  download_qqq.py            # Fetch QQQ history from Yahoo Finance into data/QQQ.tab
  get_monthly_returns.py     # 30-day rolling returns to out_data/monthly_returns.csv
  transform_new_sp500_records.py  # stdin: pasted Seeking Alpha rows -> SP500.tab format
data/                # SP500.tab, QQQ.tab, interest.tab (tab-separated)
out_data/            # Backtest output (out_data/qqq/ for QQQ); gitignored
trading_strategies_report/   # Static report site, deployed via gh-pages
config.yaml          # Datasets plus all backtest/model/report calibration (see Configuration)
logging.yaml         # Logging formatters/handlers for bin/ scripts
```

---

## Organization Development Standards

### Language & Environment

- **Python 3.11+** is the standard runtime for all projects.
- **Poetry** is used for dependency management and virtual environments. Always use `poetry add` for new dependencies and `poetry install` to set up environments. Respect `pyproject.toml` and `poetry.lock` files.
- Do not use `pip install` directly. All dependencies flow through Poetry.

### Project Structure

Most projects follow this layout:

```
project-root/
├── bin/              # CLI scripts, entrypoints, utilities
├── tests/            # pytest test suite
├── notebooks/        # Jupyter notebooks (exploration, prototyping)
├── <module>/         # One or more Python package directories
├── pyproject.toml    # Poetry project config
├── poetry.lock
├── Dockerfile
├── docker-compose.yml
├── .envrc            # Secrets and environment variables (direnv)
├── config.yaml       # Application configuration
└── CLAUDE.md
```

### Configuration & Secrets

- **YAML** is the preferred format for all configuration and parameter files. Use `config.yaml` (or descriptive variants like `model_config.yaml`) at the project root unless there's a reason to do otherwise.
- **Secrets** (API keys, database credentials, tokens) go in `.envrc` and are loaded via **direnv**. Never hardcode secrets in source files or config YAML.
- `.envrc` must be listed in `.gitignore`. Provide a `.envrc.example` with placeholder values for onboarding.

### Testing

- **pytest** is the test framework. All tests live in the `tests/` directory.
- Always run tests with coverage: `poetry run pytest --cov=<module> --cov-report=term-missing tests/`
- Aim for meaningful coverage of core logic. Don't write tests just to hit a number — focus on business logic, data transformations, and edge cases.
- Use fixtures and `conftest.py` for shared test setup.

### Deployment

- All services are deployed as **Docker containers** running **Flask-based REST APIs**.
- Containers are managed via **Dockge** (block-based Docker Compose management).
- Write a `Dockerfile` and `docker-compose.yml` for every deployable service.
- Use multi-stage builds where appropriate to keep images lean.
- Flask apps should use **Gunicorn** as the WSGI server in production containers.

### Networking & Access

- **NGINX** acts as the reverse proxy for all deployed APIs. Each service gets a virtual host or location block.
- External access is provided through a **Cloudflare Tunnel** (zero trust). No ports are exposed directly to the internet.
- When configuring services, bind to `0.0.0.0` inside the container and let NGINX handle TLS termination and routing.

### Infrastructure Services

| Service       | Host                | Port  | Notes                          |
|---------------|---------------------|-------|--------------------------------|
| PostgreSQL    | `192.168.1.91`      | 5434  | Primary database (`stock_quotes`, etc.) |
| MySQL         | `192.168.1.91`      | 3306  | Legacy (e.g. weewx)            |

- **PostgreSQL** is the default database. Use `psycopg` (v3) as the driver. SQLAlchemy is fine as an ORM when appropriate.
  In this repo, `returns/db.py` reads `PGHOST`/`PGPORT`/`PGUSER`/`PGPASSWORD`/`PGDATABASE` from `.envrc` — never hardcode connection defaults.

### Code Style & Conventions

- Follow PEP 8. Use type hints for function signatures.
- **Black** is the code formatter. Do not override its defaults. All code must pass `black --check` before merge.
- **mypy** is used for static type checking. All code must pass `mypy --strict` (or project-configured strictness) before merge.
- Both `black` and `mypy` run as part of the CI/CD pipeline — treat their failures as blocking.
- **Pydantic** is the standard for data validation and settings management. Use Pydantic `BaseModel` subclasses for API request/response schemas, config objects, and any structured data coming from external sources.
- Prefer `pathlib.Path` over `os.path` for file operations.
- Use `logging` (not print statements) for application output. Configure logging in YAML.
- Docstrings on all public functions and classes (Google style preferred).
- Keep notebooks in `notebooks/` for exploration only — production logic belongs in modules.

### Common Patterns

- **Flask API template**: Use Blueprints for route organization. Load config from `config.yaml` at startup. Health check endpoint at `/health`.
- **Database connections**: Load credentials from environment variables (via `.envrc`). Use connection pooling.
- **CLI tools in `bin/`**: Use `argparse` or `click`. Make them executable and ensure they work within the Poetry virtualenv (`poetry run`).

### Git Practices

- `.gitignore` must exclude: `.envrc`, `__pycache__/`, `.pytest_cache/`, `*.egg-info/`, `dist/`, `.venv/`, `*.pyc`, `.ipynb_checkpoints/`
- Write clear commit messages. Reference issue numbers when applicable.
