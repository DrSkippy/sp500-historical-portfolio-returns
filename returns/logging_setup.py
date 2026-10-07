"""Logging configuration for the bin/ scripts, read from logging.yaml."""

import logging.config
from pathlib import Path
from typing import Any

import yaml

DEFAULT_LOGGING_PATH = Path(__file__).resolve().parent.parent / "logging.yaml"


def configure_logging(
    level: str | None = None,
    handlers: list[str] | None = None,
    path: Path = DEFAULT_LOGGING_PATH,
) -> None:
    """Configure the root logger from logging.yaml.

    Args:
        level: Root log level (e.g. "INFO"); the file's level if None.
        handlers: Handler names from the file to attach to the root logger
            (e.g. ["file"]); the file's root handlers if None.
        path: Logging YAML file.
    """
    config: dict[str, Any] = yaml.safe_load(path.read_text())
    if level is not None:
        config["root"]["level"] = level
    if handlers is not None:
        config["root"]["handlers"] = handlers
    logging.config.dictConfig(config)
