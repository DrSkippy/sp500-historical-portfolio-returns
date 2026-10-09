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


class ModelNameError(ReturnsError):
    """A model name is not one ``format_*_name`` produces, so it cannot be parsed."""


class DuplicateModelNameError(ReturnsError):
    """Two model variants in one run would share a name (and so overwrite each
    other's output files)."""


class IncompleteRunError(ReturnsError):
    """A run's summary outputs don't cover every model the run's manifest lists."""
