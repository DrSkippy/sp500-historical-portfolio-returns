# S&P 500 Historical Portfolio Returns

A backtesting framework for analyzing historical S&P 500 portfolio returns using different investment strategies. This project simulates buying stocks on various historical start dates for different holding periods (1-15 years) to evaluate and compare portfolio management strategies.

## Overview

The project implements and compares three portfolio management strategies:

- **Buy & Hold**: Simple long-only strategy that buys at the start and holds until the end
- **Fractional Kelly**: Dynamic rebalancing strategy that maintains a fixed stock-to-bond allocation with periodic rebalancing
- **Insurance Model**: Enhanced Kelly strategy with downside protection via loss-based insurance payouts

## Features

- **Historical Backtesting**: Tests strategies across 2,500+ different start dates (from May 2005 to September 2023)
- **Multiple Holding Periods**: Analyzes returns for 1-15 year investment horizons
- **Grid Search Optimization**: Tests multiple parameter configurations for each strategy
- **Parallel Processing**: Uses multiprocessing for efficient backtesting
- **Statistical Analysis**: Computes mean, median, standard deviation, and mode of returns
- **Visualization**: Generates comparison plots and histograms
- **Rolling Returns Analysis**: Calculates 30-day rolling returns for market analysis

## Installation

### Prerequisites

- Python 3.10+
- Poetry (for dependency management)

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd sp500-historical-portfolio-returns
```

2. Install dependencies using Poetry:
```bash
poetry install
```

3. Activate the virtual environment:
```bash
poetry shell
```

Alternatively, install dependencies using pip:
```bash
pip install pandas numpy matplotlib seaborn jupyter pytest
```

## Usage

### 1. Run Full Grid Search Backtest

Execute the main backtesting script to run all strategies across all time periods:

```bash
python bin/runner.py
```

This will:
- Test 13-15 different model configurations (Buy & Hold + multiple Kelly/Insurance variants)
- Test 15 different holding periods (1-15 years)
- Run backtests across all available start dates
- Generate CSV files in `./out_data/` for each model and time period
- Log execution details to `app1.log`

**Note**: This process takes 15+ minutes depending on your system.

### 2. Generate Summary Statistics

After running the backtests, create aggregated summary files:

```bash
python bin/summarize.py
```

This will:
- Aggregate all run results into summary statistics
- Generate `./out_data/summary_{suffix}.csv` (stats per year)
- Generate `./out_data/total_returns_{suffix}.json` (full distribution data)
- Create a combined data CSV file

### 3. Analyze 30-Day Rolling Returns (Optional)

Compute and visualize rolling monthly returns:

```bash
python bin/get_monthly_returns.py
```

This will:
- Calculate 30-day rolling returns
- Display summary statistics
- Show a histogram plot
- Export results to `./out_data/monthly_returns.csv`

### 4. Interactive Analysis

Use Jupyter notebooks for exploratory analysis:

```bash
jupyter notebook notebooks/scratch.ipynb
```

## Project Structure

```
sp500-historical-portfolio-returns/
├── returns/                    # Core package
│   ├── models.py              # Trading strategies (Model, KellyModel, InsuranceModel)
│   ├── data.py                # Data loading and aggregation
│   ├── analysis.py            # Statistical analysis and plotting
│   └── monthly_returns.py     # 30-day rolling returns
├── bin/                       # Executable scripts
│   ├── runner.py              # Main grid search backtest
│   ├── summarize.py           # Post-process results
│   └── get_monthly_returns.py # Monthly returns analysis
├── tests/                     # Unit tests
│   ├── test_model_class.py
│   ├── test_kelly_model_class.py
│   └── test_insurance_class.py
├── data/                      # Input data
│   ├── SP500.tab             # S&P 500 historical prices
│   └── interest.tab          # Interest rate data
├── out_data/                  # Output directory (generated)
├── notebooks/                 # Jupyter notebooks
├── pyproject.toml            # Poetry project configuration
└── README.md                 # This file
```

## Data Files

### Input Data

- **SP500.tab**: Tab-separated S&P 500 historical price data (May 2005 - September 2023)
  - Columns: Date, Open, High, Low, Close, Adj Close, Volume

- **interest.tab**: Annual interest rate data used as bond return proxy
  - Columns: Year, Average Yield, Year Open, Year High, Year Low, Year Close, Annual % Change

### Output Data

Results are saved to `./out_data/`:
- `returns_{years}_{model_name}_{timestamp}.csv`: Individual backtest results
- `summary_{suffix}.csv`: Aggregated statistics by time period
- `total_returns_{suffix}.json`: Full distribution data
- `monthly_returns.csv`: 30-day rolling returns

## Strategy Details

### Buy & Hold Model

Simple strategy that:
- Buys stocks at the start date
- Holds until the end date
- Sells and calculates returns

### Kelly Model

Dynamic rebalancing strategy that:
- Maintains a target stock-to-bond allocation (e.g., 60% stocks / 40% bonds)
- Rebalances periodically (every 90 or 180 days)
- Applies daily interest compounding to cash/bond positions
- Tracks rebalance history

**Parameters tested**:
- `bond_frac`: [0.1, 0.15, 0.2, 0.25]
- `rebalance_period`: [90, 180] days

### Insurance Model

Enhanced Kelly strategy with downside protection:
- Extends Kelly model with loss insurance
- Monitors 6-day price history
- Triggers payout when loss exceeds deductible (e.g., 15% drop)
- Insurance payout: `loss_fraction × insurance_payout_factor × capital`
- Rebalances after payout

**Parameters tested**:
- `insurance_frac`: [0.05, 0.1]
- `deductible`: [0.09, 0.12, 0.18]
- Inherits Kelly parameters

## Code Examples

### Single Model Test

```python
from returns.models import KellyModel
from returns.data import get_combined_sp500_interest_data
import datetime

# Create model
model = KellyModel(bond_fract=0.4, rebalance_period=90)

# Load data
data, header = get_combined_sp500_interest_data()

# Configure test
start_date = datetime.datetime(2015, 1, 1)
model.model_config(start_date, years=5)

# Run backtest and get returns
returns = model.total_returns()
print(returns)  # (start_date, frac_returns, yearly_return_rate, time_span, model_name)
```

### Analyze Results

```python
from returns.data import read_summary_data, get_model_comparison_data
from returns.analysis import plot_df

# Load summary results
df_summary, total_returns_dict = read_summary_data("./out_data/summary_KellyModel.csv")

# Plot mean yearly returns vs time span
plot_df(df_summary, "time_span", ["mean_yearly_compound_returns"],
        title="Kelly Model Returns by Time Span")
```

### Compare Models

```python
from returns.data import get_model_comparison_data

# Compare models for 10-year holding period
files = [
    "./out_data/summary_BuyHold.csv",
    "./out_data/summary_Kelly.csv",
    "./out_data/summary_Insurance.csv"
]

comparison_df = get_model_comparison_data(files, year=10)
print(comparison_df[["model_name", "mean_total_returns", "mean_yearly_compound_returns"]])
```

## Testing

Run the test suite using pytest:

```bash
pytest tests/
```

Or run specific test files:

```bash
pytest tests/test_model_class.py
pytest tests/test_kelly_model_class.py
pytest tests/test_insurance_class.py
```

## Configuration

Key configuration parameters in the code:

- `STRIDE_DAYS = 3`: Sample every 3 days for backtesting (reduces computation time)
- `PADDING_TIME_DELTA = 6 days`: Padding near window boundaries
- Model parameters are configured in generator functions in `bin/runner.py`

## Statistical Metrics

The framework calculates the following metrics for each strategy:

- **Mean Returns**: Average return across all start dates
- **Median Returns**: Middle value of return distribution
- **Standard Deviation**: Volatility of returns
- **Mode**: Most common return value (estimated via histogram)
- **Fraction Losing**: Percentage of start dates with negative returns
- **Yearly Compound Return**: Annualized geometric mean return

## Dependencies

- pandas (^2.1.1): Data manipulation and analysis
- numpy (^1.26.0): Numerical computing
- matplotlib (^3.8.0): Plotting and visualization
- seaborn (^0.13.0): Statistical visualization
- jupyter/notebook (^7.0.4): Interactive notebooks
- pytest (^7.4.3): Testing framework

## License

[Add your license information here]

## Contributing

[Add contributing guidelines here]

## Contact

[Add contact information here]
