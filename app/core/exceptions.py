class AppError(Exception):
    """Base application error."""


class ExternalApiError(AppError):
    """External API failed; log and continue where possible."""


class RepositoryError(AppError):
    """Database repository operation failed."""

