"""
mdBook to llms.txt converter package.

This package converts mdBook documentation (or any Markdown docs) into LLM-friendly text files.
"""

__version__ = "1.0.0"

from .models import GitHubRepo, DocEntry, ProcessingConfig
from .exceptions import ValidationError, ProcessingError

__all__ = [
    "GitHubRepo",
    "DocEntry",
    "ProcessingConfig",
    "ValidationError",
    "ProcessingError",
]
