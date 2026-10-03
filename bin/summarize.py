if __name__ == "__main__":
    import argparse
    import glob
    import sys

    import returns.data
    from returns.data import *

    parser = argparse.ArgumentParser(description="Summarize backtest output CSVs.")
    parser.add_argument(
        "--dataset", default="sp500", help="dataset key from config.yaml (sp500, qqq)"
    )
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        filemode="w",
    )
    use_dataset(args.dataset)
    create_combined_data_file()
    files = glob.glob(f"{returns.data.out_data_path}returns_*.csv")
    files_created = create_summary_files(files)
    logger.info(f"Summary files created: {files_created}")
    logger.info("Done")
