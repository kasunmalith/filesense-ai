class FileSenseError(Exception):
    """Base for errors that can be shown safely to the user."""


class OptionalDependencyError(FileSenseError):
    """An optional feature needs an extra dependency."""


class ModelUnavailableError(FileSenseError):
    """An explicitly requested model is not installed or cached."""


class IndexingError(FileSenseError):
    """An indexing operation could not be completed safely."""
