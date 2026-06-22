"""Documentation to llms.txt converter package."""

__version__ = "1.1.0"

from .models import GitHubRepo, DocEntry, ProcessingConfig
from .exceptions import ValidationError, ProcessingError

__all__ = [
    "GitHubRepo",
    "DocEntry",
    "ProcessingConfig",
    "ValidationError",
    "ProcessingError",
]
