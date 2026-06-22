"""mdBook parsing utilities."""

import logging
import os
import re
from pathlib import Path
from typing import Optional

from .markdown_utils import clean_title, title_from_file
from .models import DocEntry

logger = logging.getLogger(__name__)

EXCLUDE_DIRS = {
    ".git",
    ".github",
    ".idea",
    ".vscode",
    "node_modules",
    "target",
    "book",
    "dist",
    "build",
    "__pycache__",
}


def parse_basic_toml(path: Path) -> dict[str, dict[str, str]]:
    """
    Parse basic TOML configuration for mdBook.

    Handles simple key-value pairs in sections, sufficient for:
      [book]
      title = "..."
      description = "..."

      [build]
      src = "src"

    Args:
        path: Path to book.toml file

    Returns:
        Nested dict of {section: {key: value}}
    """
    data = {}
    if not path.exists():
        return data

    section = None

    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        m = re.match(r"^\[([A-Za-z0-9_.-]+)\]$", line)
        if m:
            section = m.group(1)
            data.setdefault(section, {})
            continue

        m = re.match(r'^([A-Za-z0-9_.-]+)\s*=\s*"(.*)"\s*$', line)
        if m and section:
            key = m.group(1)
            val = m.group(2)
            data.setdefault(section, {})[key] = val
            continue

        m = re.match(r"^([A-Za-z0-9_.-]+)\s*=\s*'(.*)'\s*$", line)
        if m and section:
            key = m.group(1)
            val = m.group(2)
            data.setdefault(section, {})[key] = val

    return data


def find_mdbook_content_root(source_root: Path) -> tuple[Path, dict[str, dict[str, str]]]:
    """
    Locate the mdBook content directory containing SUMMARY.md.

    Standard mdBook structure:
      book.toml
      src/SUMMARY.md

    But some repos place SUMMARY.md directly in docs/ or other locations.

    Args:
        source_root: Root directory to search from

    Returns:
        Tuple of (content_root_path, parsed_config)
    """
    book_toml = source_root / "book.toml"
    config = parse_basic_toml(book_toml)

    candidates = []

    build_src = config.get("build", {}).get("src")
    if build_src:
        candidates.append(source_root / build_src)

    candidates.extend([
        source_root,
        source_root / "src",
        source_root / "docs",
    ])

    for c in candidates:
        if (c / "SUMMARY.md").exists():
            return c.resolve(), config

    found = []
    for root, dirs, files in os.walk(source_root):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
        if "SUMMARY.md" in files:
            found.append(Path(root))

    if found:
        found.sort(key=lambda x: len(x.relative_to(source_root).parts))
        return found[0].resolve(), config

    return source_root.resolve(), config


def split_link(link: str) -> tuple[str, str]:
    """
    Split a link into path and fragment parts.

    Args:
        link: Link URL possibly containing # fragment

    Returns:
        Tuple of (path, fragment) where fragment includes the #
    """
    if "#" in link:
        path, frag = link.split("#", 1)
        return path, "#" + frag
    return link, ""


def is_external_link(link: str) -> bool:
    """
    Check if a link is external (http/https/mailto/tel).

    Args:
        link: URL to check

    Returns:
        True if external, False otherwise
    """
    lowered = link.lower()
    return (
        lowered.startswith("http://")
        or lowered.startswith("https://")
        or lowered.startswith("mailto:")
        or lowered.startswith("tel:")
    )


def rel_to_content(path: Path, content_root: Path) -> str:
    """
    Get path relative to content root as POSIX string.

    Args:
        path: Absolute path to file
        content_root: Content root directory

    Returns:
        Relative POSIX path string
    """
    return path.resolve().relative_to(content_root.resolve()).as_posix()


def parse_summary(summary_path: Path, content_root: Path) -> list[DocEntry]:
    """
    Parse SUMMARY.md file to extract documentation structure.

    Args:
        summary_path: Path to SUMMARY.md file
        content_root: Root directory for resolving relative links

    Returns:
        List of DocEntry objects
    """
    entries = []
    seen = set()
    current_section = "Docs"
    in_code = False

    text = summary_path.read_text(encoding="utf-8", errors="replace")

    for raw in text.splitlines():
        line = raw.rstrip()

        if line.strip().startswith("```"):
            in_code = not in_code
            continue

        if in_code:
            continue

        heading = re.match(r"^\s*#+\s+(.+?)\s*$", line)
        if heading:
            h = clean_title(heading.group(1))
            if h.lower() != "summary":
                current_section = h
            continue

        for m in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", line):
            title = clean_title(m.group(1))
            link = m.group(2).strip()

            if not link or is_external_link(link):
                continue

            link_path, fragment = split_link(link)
            if not link_path:
                continue

            decoded = link_path.replace("%20", " ")
            target = (summary_path.parent / decoded).resolve()

            if not target.exists() or not target.is_file():
                continue

            if target.suffix.lower() not in {".md", ".markdown"}:
                continue

            rel = rel_to_content(target, content_root)
            key = rel + fragment

            if key in seen:
                continue

            seen.add(key)
            entries.append(DocEntry(
                title=title or title_from_file(target),
                path=target,
                rel=rel,
                fragment=fragment,
                section=current_section,
            ))

    return entries


def collect_markdown_files(content_root: Path) -> list[DocEntry]:
    """
    Collect all markdown files from content directory.

    Recursively walks directory tree, excluding common build/config directories.

    Args:
        content_root: Root directory to search

    Returns:
        List of DocEntry objects
    """
    files = []

    for root, dirs, filenames in os.walk(content_root):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
        root_path = Path(root)

        for name in filenames:
            p = root_path / name
            if p.suffix.lower() not in {".md", ".markdown"}:
                continue
            if p.name.lower() == "summary.md":
                continue
            files.append(p.resolve())

    def sort_key(p: Path):
        rel = p.relative_to(content_root).as_posix().lower()
        if p.name.lower() == "readme.md":
            return ("", rel)
        return (rel, rel)

    files.sort(key=sort_key)

    return [DocEntry(
        title=title_from_file(p),
        path=p,
        rel=rel_to_content(p, content_root),
        fragment="",
        section="Docs",
    ) for p in files]


def add_orphan_markdown(entries: list[DocEntry], content_root: Path) -> list[DocEntry]:
    """
    Add markdown files not referenced in SUMMARY.md.

    Args:
        entries: Existing entries from SUMMARY.md
        content_root: Root directory to search

    Returns:
        Combined list with orphaned files added under "Other" section
    """
    existing = {e.path.resolve() for e in entries}
    all_entries = collect_markdown_files(content_root)

    for e in all_entries:
        if e.path.resolve() not in existing:
            orphan = DocEntry(
                title=e.title,
                path=e.path,
                rel=e.rel,
                fragment=e.fragment,
                section="Other",
            )
            entries.append(orphan)

    return entries


def infer_title_and_description(
    source_root: Path,
    content_root: Path,
    config: dict[str, dict[str, str]],
    source_label: str
) -> tuple[str, Optional[str]]:
    """
    Infer documentation title and description from multiple sources.

    Checks in order:
    1. book.toml [book] section
    2. README.md H1 and first paragraph
    3. Falls back to source label

    Args:
        source_root: Root directory of the source
        content_root: Content directory containing docs
        config: Parsed book.toml configuration
        source_label: Human-readable source identifier

    Returns:
        Tuple of (title, description)
    """
    from .markdown_utils import first_h1, first_paragraph

    title = config.get("book", {}).get("title")
    description = config.get("book", {}).get("description")

    readme_candidates = [
        content_root / "README.md",
        content_root / "readme.md",
        source_root / "README.md",
        source_root / "readme.md",
    ]

    for readme in readme_candidates:
        if readme.exists():
            text = readme.read_text(encoding="utf-8", errors="replace")
            if not title:
                title = first_h1(text)
            if not description:
                description = first_paragraph(text)
            break

    if not title:
        title = source_label or content_root.name or "Documentation"

    return title.strip(), description.strip() if description else None
