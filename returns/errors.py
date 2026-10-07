"""Exceptions raised by the returns package."""


class ReturnsError(Exception):
    """Base class for all errors raised by this package."""


class DatasetConfigError(ReturnsError):
    """config.yaml is missing, invalid, or names an unknown dataset."""


class MissingPriceColumnError(ReturnsError):
    """The configured price column is not in the price file's header."""


class EmptyReturnsError(ReturnsError):
    """A returns or summary input contained no data rows."""


class NoModelOutputsError(ReturnsError):
    """No matching summary/total_returns file pairs were found."""


class NoMatchingRunError(ReturnsError):
    """No backtest run in the output directory matches the requested model version."""
