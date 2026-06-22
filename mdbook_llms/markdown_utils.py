"""Markdown parsing and processing utilities."""

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def first_h1(markdown: str) -> Optional[str]:
    """
    Extract the first H1 heading from markdown text.

    Args:
        markdown: Markdown content as string

    Returns:
        Cleaned title text, or None if no H1 found
    """
    for line in markdown.splitlines():
        m = re.match(r"^\s*#\s+(.+?)\s*$", line)
        if m:
            return clean_title(m.group(1))
    return None


def first_paragraph(markdown: str) -> Optional[str]:
    """
    Extract the first paragraph from markdown text.

    Skips frontmatter, headings, and links.

    Args:
        markdown: Markdown content as string

    Returns:
        First paragraph text, or None if not found
    """
    lines = markdown.splitlines()
    out = []
    in_frontmatter = False

    if lines and lines[0].strip() == "---":
        in_frontmatter = True
        lines = lines[1:]

    if in_frontmatter:
        while lines:
            line = lines.pop(0)
            if line.strip() == "---":
                break

    for line in lines:
        s = line.strip()
        if not s:
            if out:
                break
            continue
        if s.startswith("#"):
            continue
        if s.startswith("[") and "](" in s:
            continue
        if s.startswith("<!--"):
            continue
        out.append(s)

    return " ".join(out).strip() if out else None


def clean_title(s: str) -> str:
    """
    Clean markdown formatting from title text.

    Removes code backticks, HTML tags, and backslashes.

    Args:
        s: Raw title string

    Returns:
        Cleaned title string
    """
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("\\", "")
    return s.strip()


def md_escape_link_text(s: str) -> str:
    """
    Escape square brackets in markdown link text.

    Args:
        s: Link text to escape

    Returns:
        Escaped text safe for markdown links
    """
    return s.replace("[", r"\[").replace("]", r"\]")


def strip_yaml_frontmatter(text: str) -> str:
    """
    Remove YAML frontmatter from markdown text.

    Args:
        text: Markdown content

    Returns:
        Text with frontmatter removed
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text

    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[i + 1:]).lstrip()

    return text


def split_include_spec(spec: str) -> tuple[str, Optional[int], Optional[int]]:
    """
    Parse mdBook include directive with line ranges.

    Handles formats:
      {{#include file.rs}}       -> (file.rs, None, None)
      {{#include file.rs:10}}    -> (file.rs, 10, None)
      {{#include file.rs:10:20}} -> (file.rs, 10, 20)
      {{#include file.rs::20}}   -> (file.rs, None, 20)

    Args:
        spec: Include specification string

    Returns:
        Tuple of (file_path, start_line, end_line)
    """
    parts = spec.split(":")

    if len(parts) >= 3 and (parts[-1].isdigit() or parts[-1] == "") and (parts[-2].isdigit() or parts[-2] == ""):
        path = ":".join(parts[:-2])
        start = int(parts[-2]) if parts[-2] else None
        end = int(parts[-1]) if parts[-1] else None
        return path, start, end

    if len(parts) >= 2 and parts[-1].isdigit():
        path = ":".join(parts[:-1])
        start = int(parts[-1])
        return path, start, None

    return spec, None, None


def expand_mdbook_includes(text: str, current_file: Path, depth: int = 0) -> str:
    """
    Recursively expand mdBook {{#include}} directives.

    Args:
        text: Markdown content with potential includes
        current_file: Path to current file (for resolving relative includes)
        depth: Recursion depth (prevents infinite loops)

    Returns:
        Text with all includes expanded
    """
    if depth > 5:
        return text

    pattern = re.compile(r"\{\{#(?:rustdoc_)?include\s+([^}\s]+)\s*\}\}")

    def repl(m):
        spec = m.group(1).strip()
        inc_path, start, end = split_include_spec(spec)
        target = (current_file.parent / inc_path).resolve()

        if not target.exists() or not target.is_file():
            return f"\n<!-- unresolved mdBook include: {spec} -->\n"

        try:
            included = target.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"\n<!-- failed to read mdBook include: {spec}: {e} -->\n"

        lines = included.splitlines()

        if start is not None or end is not None:
            # mdBook line ranges are 1-based.
            s = max((start or 1) - 1, 0)
            e = end if end is not None else len(lines)
            lines = lines[s:e]
            included = "\n".join(lines)

        included = expand_mdbook_includes(included, target, depth + 1)

        lang = target.suffix.lstrip(".")
        if lang in {"md", "markdown", ""}:
            return "\n" + included.strip() + "\n"

        return f"\n```{lang}\n{included.rstrip()}\n```\n"

    return pattern.sub(repl, text)


def title_from_file(path: Path) -> str:
    """
    Extract or infer a title from a markdown file.

    Tries to extract the first H1, falls back to filename.

    Args:
        path: Path to markdown file

    Returns:
        Title string
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        h1 = first_h1(text)
        if h1:
            return h1
    except Exception:
        pass

    if path.name.lower() == "readme.md":
        return path.parent.name.replace("-", " ").replace("_", " ").title() or "README"

    return path.stem.replace("-", " ").replace("_", " ").title()
