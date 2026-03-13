# CLAUDE.md

## Project: sp500-historical-portfolio-returns

Backtests three portfolio strategies (Buy&Hold, KellyModel, InsuranceModel) across the full
S&P 500 daily price history. The core module is `returns/`. Scripts live in `bin/`.

### Running tests

```bash
poetry run pytest --cov=returns --cov-report=term-missing tests/
```

Tests live in `tests/` (with an `s`). Use `poetry run python ...` — never bare `python`.

### Testing principles

- **No I/O in unit tests.** Use `tmp_path` + `monkeypatch` to redirect module-level file paths
  (e.g. `monkeypatch.setattr(returns.data, "sp500_input_path", str(tmp_file))`).
- **Synthetic data only.** Build minimal fixture rows rather than loading real data files.
- **Test edge cases explicitly.** Known sharp edges in this codebase:
  - `calculate_mode` (`analysis.py`): when `argmax == 0`, `bins[argmax - 1]` wraps to the
    last bin — test data must place the histogram peak away from bin 0.
  - `model_name` mutation: `model_config()` must assign (`=`), never append (`+=`), or the
    name accumulates across the ~5,800 calls made per full backtest run.
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
- When adding new strategies, add them to `all_model_specs()` in `runner.py` — the parallelism
  scales automatically.

### Module layout

```
returns/
  models.py          # Model, KellyModel, InsuranceModel
  data.py            # I/O: get_sp500_data, get_interest_data, get_combined_sp500_interest_data
  analysis.py        # aggregate_returns, calculate_mode, get_aggregate_returns_by_period
  monthly_returns.py # MonthlyReturns (30-day rolling returns, formula: (cur-prior)/cur)
bin/
  runner.py          # Backtest entry point; model_tester, model_test_worker, all_model_specs
  transform_new_sp500_records.py
data/                # Raw SP500.tab and interest.tab (tab-separated)
out_data/            # CSV output from backtest runs
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
| MySQL         | `192.168.1.91`      | 3306  | Primary database               |
| Ollama (LLM)  | `192.168.1.90`      | 11434 | Local LLM inference server     |

- **MySQL** is the default database. Use `PyMySQL` or `mysqlclient` as the driver. SQLAlchemy is fine as an ORM when appropriate.
- **Ollama** provides local LLM access. Base URL: `http://192.168.1.90:11434/`
  - Use the Ollama REST API or the `ollama` Python client library.
  - Prefer local models over external API calls when feasible.
  - **Always validate LLM responses with Pydantic models.** Define expected response schemas as Pydantic classes and parse LLM output through them before use.
  - Available models:

    | Model                  | Size   | Use Case                                      |
    |------------------------|--------|-----------------------------------------------|
    | `llama4:latest`        | 67 GB  | Large general-purpose reasoning                |
    | `gpt-oss:latest`       | 13 GB  | General-purpose                                |
    | `phi4:latest`          | 9.1 GB | Strong mid-size reasoning                      |
    | `deepseek-ocr:latest`  | 6.7 GB | OCR and document extraction                    |
    | `deepseek-r1:latest`   | 5.2 GB | Reasoning tasks                                |
    | `qwen3:latest`         | 5.2 GB | General-purpose, multilingual                  |
    | `gemma3:latest`        | 3.3 GB | Lightweight general-purpose                    |
    | `deepseek-coder:latest`| 776 MB | Code generation and completion                 |
    | `mxbai-embed-large:latest` | 669 MB | Text embeddings (not generative)          |

  - Specify the model name in `config.yaml` so it's easily swappable. Choose the smallest model that fits the task.

### Code Style & Conventions

- Follow PEP 8. Use type hints for function signatures.
- **Black** is the code formatter. Do not override its defaults. All code must pass `black --check` before merge.
- **mypy** is used for static type checking. All code must pass `mypy --strict` (or project-configured strictness) before merge.
- Both `black` and `mypy` run as part of the CI/CD pipeline — treat their failures as blocking.
- **Pydantic** is the standard for data validation, settings management, and LLM response parsing. Use Pydantic `BaseModel` subclasses for API request/response schemas, config objects, and any structured data coming from external sources (especially LLM output).
- Prefer `pathlib.Path` over `os.path` for file operations.
- Use `logging` (not print statements) for application output. Configure logging in YAML.
- Docstrings on all public functions and classes (Google style preferred).
- Keep notebooks in `notebooks/` for exploration only — production logic belongs in modules.

### Common Patterns

- **Flask API template**: Use Blueprints for route organization. Load config from `config.yaml` at startup. Health check endpoint at `/health`.
- **Database connections**: Load credentials from environment variables (via `.envrc`). Use connection pooling.
- **LLM integration**: Point to Ollama at `http://192.168.1.90:11434/`. Specify model name in `config.yaml` so it's easily swappable. Always define a Pydantic model for expected LLM output and validate responses through it.
- **CLI tools in `bin/`**: Use `argparse` or `click`. Make them executable and ensure they work within the Poetry virtualenv (`poetry run`).

### Git Practices

- `.gitignore` must exclude: `.envrc`, `__pycache__/`, `.pytest_cache/`, `*.egg-info/`, `dist/`, `.venv/`, `*.pyc`, `.ipynb_checkpoints/`
- Write clear commit messages. Reference issue numbers when applicable.
