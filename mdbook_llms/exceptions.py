"""Custom exception classes for mdbook_llms."""


class ValidationError(Exception):
    """Raised when input validation fails."""
    pass


class ProcessingError(Exception):
    """Raised when documentation processing fails."""
    pass
