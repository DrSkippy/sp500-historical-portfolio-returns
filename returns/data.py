import csv
import datetime
import json
import locale
import logging

import pandas as pd

from returns.analysis import get_aggregate_returns_by_period, get_df_aggregate_returns_by_period

logger = logging.getLogger(__name__)

locale.setlocale(locale.LC_ALL, '')

sp500_input_path = "./data/SP500.tab"
interest_input_path = "./data/interest.tab"

FMT_IN = "%b %d, %Y"
FMT_out = "%Y-%m-%d"

sp500_index = 5
interest_index = 0
combined_sp500_index = sp500_index
combined_interest_index = 7 + interest_index


def get_interest_data():
    """
    Reads interest data from a TSV file.

    Returns:
    tuple: A tuple containing the interest data (as a dictionary with years as keys) and the header.
    """
    interest_data = {}

    with open(interest_input_path, "r") as infile:
        reader = csv.reader(infile, delimiter="\t")
        header = next(reader)[1:]  # Reading the header

        for row in reader:
            year = datetime.datetime.strptime(row[0], "%Y-%m-%d").year
            interest_data[year] = [float(x) / 100. for x in row[1:]]

    # Debugging information
    logger.info(f"Reading interest data")
    logger.info(f"Path = {interest_input_path}")
    logger.info(f"Read {len(interest_data)} rows")
    logger.info(f"Fields = {header}")

    return interest_data, header


def get_sp500_data():
    """
    Reads S&P 500 data from a TSV file.

    Returns:
    tuple: A tuple containing the sorted data (with dates and values) and the header.
    """
    parsed_data = []

    with open(sp500_input_path, "r") as infile:
        reader = csv.reader(infile, delimiter="\t")
        header = next(reader)  # Reading the header

        for row in reader:
            # Parse date and data values
            date = datetime.datetime.strptime(row[0], FMT_IN)
            row_data = [locale.atof(x) for x in row[1:]]
            parsed_data.append([date] + row_data)

    # Sort data by date
    parsed_data.sort()

    # Debugging information
    logger.info(f"Reading S&P 500 data")
    logger.info(f"Path = {sp500_input_path}")
    logger.info(f"Read {len(parsed_data)} rows")
    logger.info(f"Fields = {header}")

    return parsed_data, header


def get_combined_sp500_interest_data():
    """
    Reads S&P 500 and interest data from TSV files.

    Returns:
    tuple: A tuple containing the combined data (with dates and values) and
    the header.
    """
    result = []
    logger.info(f"Combining S&P 500 and Interest data")
    sp500, sp500_header = get_sp500_data()
    interest, interest_header = get_interest_data()
    # Append rows from interest data to S&P 500 data
    for i, row in enumerate(sp500):
        result.append(row + interest[row[0].year])
    return result, sp500_header + interest_header


def create_combined_data_file():
    """
    Creates a combined CSV file with data from all model runs.
    """
    data, header = get_combined_sp500_interest_data()
    with open("./data/combined_data.csv", "w") as outfile:
        writer = csv.writer(outfile)
        writer.writerow(header)
        for row in data:
            writer.writerow(row)


def get_model_run_outputs(suffix, years=[1, 2, 3]):
    """
    Reads data from CSV files for specified years and returns the data along with headers.

    Parameters:
    suffix (str): Suffix for the filename.
    years (list): List of years for which to read the data.

    Returns:
    tuple: A dictionary containing data for each year and the header of the CSV files.
    """
    results = {}
    header = None

    logger.info(f"Reading model run data")
    for year in years:
        filename = f"./out_data/returns_{year}_{suffix}"
        logger.info(f"Reading {filename}")

        with open(filename, "r") as infile:
            reader = csv.reader(infile)
            header = next(reader)  # Reading the header

            # Process each row
            data = []
            for row in reader:
                date = datetime.datetime.strptime(row[0][:10], FMT_out)
                data.append([date] + row[1:])

        results[year] = sorted(data)
        logger.info(f"Read {len(data)} rows")
        logger.info(f"Fields = {header}")

    return results, header, f"./out_data/summary_{suffix}"


def create_summary_file(results, header, filename):
    """
    Creates a summary of the results and writes it to a CSV file.

    Parameters:
    results (dict): A dictionary containing the results for each year.
    header (list): A list of headers for the CSV file.
    filename (str): The name of the CSV file to write.
    """
    returns_stats_by_period, total_returns_by_period = get_aggregate_returns_by_period(results)
    df = get_df_aggregate_returns_by_period(returns_stats_by_period)

    df.to_csv(filename, index=False)
    logger.info(f"Summary data written to {filename}")

    json_filename = filename.replace("summary", "total_returns").replace(".csv", ".json")
    with open(json_filename, "w") as outfile:
        json.dump(total_returns_by_period, outfile)
    logger.info(f"Total returns data written to {json_filename}")
    return filename, json_filename


def create_summary_files(files):
    """
    Prompts the user to select a file suffix from a list of file names.

    Parameters:
    files (list of str): A list of file names.

    Returns:
    str: The selected file suffix.
    """
    # Extract unique suffixes from file names
    # there is an _ in the directory name so 3 not 2...!!
    suffixes = list(set("_".join(filename.split("_")[3:]) for filename in files))
    logger.info("Suffixes extracted from file names")
    unique_suffixes = {'_'.join(x.split("_")[1:]) for x in suffixes}
    for s in unique_suffixes:
        logger.info(f"  - {s}")
    files_created = []
    years = range(1, 16)
    for i, suffix in enumerate(suffixes):
        logger.info(f"*** {i} of {len(suffixes)} *** {suffix}")
        result = get_model_run_outputs(suffix, years=years)
        fn, jfn = create_summary_file(*result)
        files_created.append((fn, jfn))
    return files_created


def read_summary_data(filename):
    """
    Reads summary data from a CSV file. Returns a dataframe.
    :param filename:
    :return:
    """
    df = pd.read_csv(filename)
    json_filename = filename.replace("summary", "total_returns").replace(".csv", ".json")
    with open(json_filename, "r") as infile:
        total_returns_by_period = json.load(infile)
    return df, total_returns_by_period


def get_model_comparison_data(files, year=10):
    rdata = []
    for p in files:
        d, h = read_summary_data(p)
        rdata.append(d.iloc[year-1].to_list())
    drf = pd.DataFrame(rdata, columns=[
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
        "mode_yearly_returns"])
    drf = drf.sort_values("mean_total_returns")
    return drf