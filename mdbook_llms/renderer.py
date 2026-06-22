"""Rendering utilities for llms.txt output files."""

import logging
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from .markdown_utils import md_escape_link_text, strip_yaml_frontmatter, expand_mdbook_includes
from .models import DocEntry

logger = logging.getLogger(__name__)


def link_for(
    rel: str,
    fragment: str,
    link_base: Optional[str],
    html_links: bool,
    url: Optional[str] = None,
) -> str:
    """
    Generate appropriate link for a documentation page.

    Args:
        rel: Relative path to the page
        fragment: URL fragment (e.g., #section)
        link_base: Optional base URL to prepend
        html_links: Whether to convert .md to .html

    Returns:
        Complete URL string
    """
    if url and not link_base:
        return url + fragment

    href = rel

    if html_links:
        p = Path(href)
        lower_name = p.name.lower()

        if lower_name in {"readme.md", "index.md"}:
            parent = p.parent.as_posix()
            href = "./" if parent == "." else parent + "/"
        else:
            href = p.with_suffix(".html").as_posix()

    href += fragment

    if link_base:
        base = link_base.rstrip("/")
        return base + "/" + quote(href, safe="/#%.-_~")

    return quote(href, safe="/#%.-_~")


def group_entries(entries: list[DocEntry]) -> list[tuple[str, list[DocEntry]]]:
    """
    Group entries by section, preserving order.

    Args:
        entries: List of documentation entries

    Returns:
        List of (section_name, entries) tuples
    """
    grouped = []
    index = {}

    for e in entries:
        section = e.section or "Docs"
        if section not in index:
            index[section] = []
            grouped.append((section, index[section]))
        index[section].append(e)

    return grouped


def render_llms_txt(
    title: str,
    description: Optional[str],
    entries: list[DocEntry],
    link_base: Optional[str],
    html_links: bool
) -> str:
    """
    Render llms.txt table of contents file.

    Args:
        title: Documentation title
        description: Optional description
        entries: List of documentation entries
        link_base: Optional base URL for links
        html_links: Whether to use .html links

    Returns:
        Complete llms.txt content
    """
    lines = [f"# {title}", ""]

    if description:
        lines.append(f"> {description}")
        lines.append("")

    lines.append("This file lists the most useful documentation pages for language models.")
    lines.append("")

    for section, section_entries in group_entries(entries):
        lines.append(f"## {section}")
        lines.append("")

        for e in section_entries:
            href = link_for(e.rel, e.fragment, link_base, html_links, url=e.url)
            lines.append(f"- [{md_escape_link_text(e.title)}]({href})")

        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_llms_full_txt(
    title: str,
    description: Optional[str],
    entries: list[DocEntry],
    source_label: str
) -> str:
    """
    Render llms-full.txt with complete documentation content.

    Args:
        title: Documentation title
        description: Optional description
        entries: List of documentation entries
        source_label: Human-readable source identifier

    Returns:
        Complete llms-full.txt content
    """
    lines = [f"# {title}", ""]

    if description:
        lines.append(f"> {description}")
        lines.append("")

    lines.append(f"Generated from: `{source_label}`")
    lines.append("")

    lines.append("## Contents")
    lines.append("")

    for e in entries:
        source = e.url or e.rel
        lines.append(f"- {e.title} — `{source}`")

    lines.append("")

    for e in entries:
        path = e.path

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as ex:
            logger.warning(f"Failed to read {e.rel}: {ex}")
            lines.append("---")
            lines.append("")
            lines.append(f"## {e.title}")
            lines.append("")
            lines.append(f"Source: `{e.rel}`")
            lines.append("")
            lines.append(f"<!-- failed to read file: {ex} -->")
            lines.append("")
            continue

        text = strip_yaml_frontmatter(text)
        text = expand_mdbook_includes(text, path)
        text = text.strip()

        lines.append("---")
        lines.append("")
        lines.append(f"## {e.title}")
        lines.append("")
        lines.append(f"Source: `{e.url or e.rel}`")
        lines.append("")

        if text:
            lines.append(text)
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"
