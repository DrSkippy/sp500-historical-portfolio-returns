from typing import Any, Mapping, Sequence

import numpy as np
import numpy.typing as npt
import pandas as pd
from matplotlib import pyplot as plt

# One aggregate_returns() summary row; see get_df_aggregate_returns_by_period for columns
ReturnStats = tuple[Any, ...]


def calculate_mode(hist_data: tuple[npt.NDArray[Any], npt.NDArray[Any]]) -> float:
    """
    Calculates the mode of a histogram as the midpoint between the two bins with the highest counts.

    Args:
    hist_data (tuple): A tuple containing the histogram data.

    Returns:
    float: The mode of the histogram.
    """
    return float(
        (
            hist_data[1][np.argmax(hist_data[0])]
            + hist_data[1][np.argmax(hist_data[0]) - 1]
        )
        / 2
    )


def aggregate_returns(
    returns_data: Sequence[Sequence[Any]],
) -> tuple[ReturnStats, list[float]]:
    """
    returns_data = ["date",
                    "frac_return",
                    "yearly_return_rate",
                    "time_span",
                    "model_name"]
    """
    returns_data_vectors = np.array(returns_data).T

    sample_size = len(returns_data_vectors[0])
    time_span = round(returns_data_vectors[3].astype(float)[0], 0)
    model_name = returns_data_vectors[-1][0]

    total_returns = returns_data_vectors[1].astype(float)
    yearly_compounded_returns = returns_data_vectors[2].astype(float)

    mean_total_returns = np.mean(total_returns)
    mean_yearly_compound_returns = np.mean(yearly_compounded_returns)

    median_total_returns = np.median(total_returns)
    median_yearly_returns = np.median(yearly_compounded_returns)

    sdev_total_returns = np.std(total_returns)
    sdev_yearly_returns = np.std(yearly_compounded_returns)

    fraction_losing_starts = np.count_nonzero(total_returns < 0.0) / len(total_returns)

    r_hist = np.histogram(total_returns, bins=45)
    mode_total_returns = calculate_mode(r_hist)
    r_hist = np.histogram(yearly_compounded_returns, bins=45)
    mode_yearly_returns = calculate_mode(r_hist)

    return (
        sample_size,
        time_span,
        model_name,
        mean_total_returns,
        mean_yearly_compound_returns,
        median_total_returns,
        median_yearly_returns,
        sdev_total_returns,
        sdev_yearly_returns,
        fraction_losing_starts,
        mode_total_returns,
        mode_yearly_returns,
    ), total_returns.tolist()


def show_metrics(return_stats: ReturnStats) -> None:
    print(f"### AGGREGATE RETURNS ### {return_stats[2]} ###")
    print(f"Sample Size              = {return_stats[0]}")
    print(f"Time span                = {return_stats[1]:5.1f} years")
    print(f"Mean Returns             = {return_stats[3]:5.2%}")
    print(f"Avg Yearly Return        = {return_stats[4]:5.2%}")
    print(f"Median Returns           = {return_stats[5]:5.2%}")
    print(f"Median Yearly Returns    = {return_stats[6]:5.2%}")
    print(f"StdDev of Returns        = {return_stats[7]:5.2%}")
    print(f"StdDev of Yearly Returns = {return_stats[8]:5.2%}")
    print(f"Losing start days        = {return_stats[9]:5.2%}")
    print(f"Mode of Returns          = {return_stats[10]:5.2%}")
    print(f"Mode of Yearly Returns   = {return_stats[11]:5.2%}")


def get_aggregate_returns_by_period(
    data: Mapping[Any, Sequence[Sequence[Any]]],
) -> tuple[list[ReturnStats], dict[Any, list[float]]]:
    returns_stats_by_period = []
    total_returns_by_period = {}
    for k, v in data.items():
        summary_vector, total_returns = aggregate_returns(v)
        total_returns_by_period[k] = total_returns
        returns_stats_by_period.append(summary_vector)
    return returns_stats_by_period, total_returns_by_period


def get_df_aggregate_returns_by_period(
    returns_stats_by_period: list[ReturnStats],
) -> pd.DataFrame:
    df = pd.DataFrame(
        returns_stats_by_period,
        columns=[
            "sample_size",
            "time_span",
            "model_name",
            "mean_total_returns",
            "mean_yearly_compound_returns",
            "median_total_returns",
            "median_yearly_returns",
            "sdev_total_returns",
            "sdev_yearly_returns",
            "fraction_losing_starts",
            "mode_total_returns",
            "mode_yearly_returns",
        ],
    )
    df = df.sort_values(by=["time_span"])
    return df


def plot_df(
    df: pd.DataFrame,
    columns: list[str] | None = None,
    df2: pd.DataFrame | None = None,
) -> None:
    if columns is None:
        columns = df.columns.to_list()[3:]
    fig, axs = plt.subplots(nrows=len(columns), ncols=1)
    fig.set_size_inches(8, 4 * len(columns))
    for ax, column in zip(axs.reshape(-1), columns):
        df.plot(x="time_span", y=column, ax=ax)
        if df2 is not None:
            df2.plot(x="time_span", y=column, ax=ax)
        ax.set_ylabel(column.replace("_", " ").capitalize())
        ax.set_xlabel("Period (Years)")


def plot_histograms(total_returns_by_period: dict[Any, list[float]]) -> None:
    fig, axs = plt.subplots(nrows=len(total_returns_by_period), ncols=1)
    fig.set_size_inches(8, 4 * len(total_returns_by_period))
    for ax, (k, v) in zip(axs.reshape(-1), total_returns_by_period.items()):
        _ = ax.hist(v, bins=45)
        ax.set_title(f"Sample Returns {k}")


def plot_period_comparison_data(drf: pd.DataFrame) -> None:
    drf.plot.scatter("mean_total_returns", "model_name")
    drf.plot.scatter("mean_yearly_compound_returns", "model_name")
    drf.plot.scatter("median_total_returns", "model_name")
    drf.plot.scatter("median_yearly_returns", "model_name")
    drf.plot.scatter("fraction_losing_starts", "model_name")
