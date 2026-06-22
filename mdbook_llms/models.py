"""Data models for mdbook_llms."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class GitHubRepo:
    """Represents a parsed GitHub repository URL."""
    owner: str
    repo: str
    repo_url: str
    tree_parts: list[str]


@dataclass
class DocEntry:
    """Represents a documentation page entry."""
    title: str
    path: Path
    rel: str
    fragment: str
    section: str


@dataclass
class ProcessingConfig:
    """Configuration for documentation processing."""
    source_root: Path
    content_root: Path
    source_label: str
    title: str
    description: Optional[str]
    link_base: Optional[str]
    html_links: bool
    include_orphans: bool
