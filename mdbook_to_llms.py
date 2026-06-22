#!/usr/bin/env python3
"""
mdBook to llms.txt converter.

Converts mdBook documentation (or any Markdown docs) into LLM-friendly text files.
Generates llms.txt (table of contents) and llms-full.txt (full documentation).
"""

import argparse
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, quote


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
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


class ValidationError(Exception):
    """Raised when input validation fails."""
    pass


class ProcessingError(Exception):
    """Raised when documentation processing fails."""
    pass


def die(msg: str) -> None:
    """
    Print error message and exit with status code 1.

    Args:
        msg: Error message to display
    """
    logger.error(msg)
    sys.exit(1)


def run(cmd: list[str], cwd: Optional[Path] = None, check: bool = True) -> str:
    """
    Run a shell command and return its output.

    Args:
        cmd: Command and arguments as a list
        cwd: Working directory for the command
        check: Whether to raise an error on non-zero exit

    Returns:
        Command stdout as a string

    Raises:
        SystemExit: If check=True and command fails
    """
    logger.debug(f"Running command: {' '.join(cmd)}")
    p = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and p.returncode != 0:
        die(
            f"Command failed: {' '.join(cmd)}\n"
            f"Exit code: {p.returncode}\n"
            f"stdout: {p.stdout}\n"
            f"stderr: {p.stderr}"
        )
    return p.stdout.strip()


def has_git() -> bool:
    """
    Check if git is available in the system PATH.

    Returns:
        True if git is available, False otherwise
    """
    return shutil.which("git") is not None


def validate_environment() -> None:
    """
    Validate that required tools are available.

    Raises:
        ValidationError: If required tools are missing
    """
    if not has_git():
        raise ValidationError(
            "git is required but not found. Install it with:\n"
            "  macOS: xcode-select --install\n"
            "  Ubuntu/Debian: apt-get install git\n"
            "  Windows: https://git-scm.com/download/win"
        )


def parse_github_url(value: str) -> Optional[GitHubRepo]:
    """
    Parse a GitHub URL into its components.

    Supports formats:
      - https://github.com/owner/repo
      - https://github.com/owner/repo/tree/main/docs
      - https://github.com/owner/repo/tree/feature/branch/docs

    Args:
        value: GitHub URL string

    Returns:
        GitHubRepo object if valid, None otherwise
    """
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        return None

    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < 2:
        return None

    owner = parts[0]
    repo = parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]

    repo_url = f"https://github.com/{owner}/{repo}.git"

    if len(parts) >= 4 and parts[2] == "tree":
        tree_parts = parts[3:]
    else:
        tree_parts = []

    return GitHubRepo(
        owner=owner,
        repo=repo,
        repo_url=repo_url,
        tree_parts=tree_parts,
    )


def remote_refs(repo_url: str) -> list[str]:
    """
    Get all remote refs (branches and tags) for a repository.

    Args:
        repo_url: Git repository URL

    Returns:
        Sorted list of ref names (longest first to handle slash-containing branches)
    """
    logger.debug(f"Fetching remote refs from {repo_url}")
    out = run(["git", "ls-remote", "--heads", "--tags", repo_url], check=False)
    refs = set()

    for line in out.splitlines():
        if "\trefs/heads/" in line:
            refs.add(line.split("\trefs/heads/", 1)[1])
        elif "\trefs/tags/" in line and not line.endswith("^{}"):
            refs.add(line.split("\trefs/tags/", 1)[1])

    return sorted(refs, key=lambda x: len(x.split("/")), reverse=True)


def resolve_ref_and_subpath(repo_url: str, tree_parts: list[str]) -> tuple[Optional[str], Path]:
    """
    Resolve ambiguous GitHub tree URL parts into git ref and subpath.

    GitHub tree URLs like /tree/feature/x/docs are ambiguous:
    - Is it branch "feature" with path "x/docs"?
    - Or branch "feature/x" with path "docs"?

    This function checks remote refs to disambiguate.

    Args:
        repo_url: Git repository URL
        tree_parts: Parts after /tree/ in GitHub URL

    Returns:
        Tuple of (git_ref, subpath)
    """
    if not tree_parts:
        return None, Path(".")

    joined = "/".join(tree_parts)
    refs = remote_refs(repo_url)

    for ref in refs:
        if joined == ref:
            return ref, Path(".")
        if joined.startswith(ref + "/"):
            subpath = joined[len(ref):].lstrip("/")
            return ref, Path(subpath)

    # Fallback for common case: /tree/main/docs
    return tree_parts[0], Path("/".join(tree_parts[1:]) or ".")


def clone_repo(repo_url: str, ref: Optional[str], tmpdir: Path) -> None:
    """
    Clone a git repository to a temporary directory.

    Attempts shallow clone first for speed, falls back to full clone for commits/unusual refs.

    Args:
        repo_url: Git repository URL to clone
        ref: Branch, tag, or commit to checkout (None for default branch)
        tmpdir: Directory to clone into

    Raises:
        SystemExit: If clone fails
    """
    logger.info(f"Cloning {repo_url}...")
    if ref:
        p = subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", ref, repo_url, str(tmpdir)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if p.returncode == 0:
            return

        # Fallback: supports commit hashes or unusual refs.
        run(["git", "clone", "--filter=blob:none", repo_url, str(tmpdir)])
        run(["git", "checkout", ref], cwd=tmpdir)
    else:
        run(["git", "clone", "--depth", "1", repo_url, str(tmpdir)])


def materialize_input(value: str) -> tuple[Path, Optional[Path], str]:
    """
    Convert input (local path or GitHub URL) into a local directory.

    For local paths, returns them directly.
    For GitHub URLs, clones the repository to a temp directory.

    Args:
        value: Local filesystem path or GitHub URL

    Returns:
        Tuple of (source_root, cleanup_dir, source_label) where:
        - source_root: Path to the documentation directory
        - cleanup_dir: Temp directory to delete later (None for local paths)
        - source_label: Human-readable source identifier

    Raises:
        ValidationError: If input is invalid
        SystemExit: If git operations fail
    """
    p = Path(value).expanduser()
    if p.exists():
        logger.info(f"Using local path: {p}")
        return p.resolve(), None, str(p.resolve())

    gh = parse_github_url(value)
    if not gh:
        raise ValidationError(
            f"Input must be a local path or GitHub URL.\n"
            f"Got: {value}\n"
            f"Example: https://github.com/owner/repo/tree/main/docs"
        )

    validate_environment()

    tmp = Path(tempfile.mkdtemp(prefix="mdbook-llms-"))
    ref, subpath = resolve_ref_and_subpath(gh.repo_url, gh.tree_parts)

    clone_repo(gh.repo_url, ref, tmp)

    source_root = (tmp / subpath).resolve()
    if not source_root.exists():
        raise ProcessingError(
            f"Path not found inside repository: {subpath}\n"
            f"Available paths in repo:\n" +
            "\n".join(f"  - {p.relative_to(tmp)}" for p in tmp.rglob("*") if p.is_dir())[:500]
        )

    label = f"{gh.owner}/{gh.repo}"
    if ref:
        label += f"@{ref}"
    if str(subpath) != ".":
        label += f"/{subpath}"

    return source_root, tmp, label


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


def link_for(rel: str, fragment: str, link_base: Optional[str], html_links: bool) -> str:
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
            href = link_for(e.rel, e.fragment, link_base, html_links)
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
        lines.append(f"- {e.title} — `{e.rel}`")

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
        lines.append(f"Source: `{e.rel}`")
        lines.append("")

        if text:
            lines.append(text)
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def extract_project_name(source_label: str, title: str) -> str:
    """
    Extract a clean project name from source_label or title.

    Examples:
      "owner/repo@main" -> "owner"
      "owner/repo@main/docs" -> "owner"
      "owner/repo" -> "owner"
      "/path/to/project" -> "project"
      "My Project Title" -> "My-Project-Title"

    Args:
        source_label: Source identifier string
        title: Documentation title as fallback

    Returns:
        Clean project name suitable for directory name
    """
    # Try to extract from GitHub-style label (owner/repo format)
    if "/" in source_label:
        parts = source_label.split("/")
        if len(parts) >= 2:
            # GitHub format: "owner/repo@ref/path" - use just the owner
            owner = parts[0]
            if owner and owner != ".":
                return owner

    # Try to extract from path
    path = Path(source_label)
    if path.name and path.name != ".":
        return path.name

    # Fall back to title, converted to kebab-case
    return re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "-")


def check_existing_output(out_dir: Path) -> bool:
    """
    Check if output files already exist and prompt user.

    Args:
        out_dir: Output directory to check

    Returns:
        True if should proceed, False to abort
    """
    llms_exists = (out_dir / "llms.txt").exists()
    full_exists = (out_dir / "llms-full.txt").exists()

    if llms_exists or full_exists:
        try:
            response = input(
                f"\nOutput files already exist in {out_dir}\n"
                f"Replace them? [y/N]: "
            ).strip().lower()
            return response in {"y", "yes"}
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            return False
    return True


def collect_entries(
    content_root: Path,
    include_orphans: bool
) -> list[DocEntry]:
    """
    Collect all documentation entries from content root.

    Args:
        content_root: Root directory containing docs
        include_orphans: Whether to include files not in SUMMARY.md

    Returns:
        List of DocEntry objects

    Raises:
        ProcessingError: If no markdown files found
    """
    summary = content_root / "SUMMARY.md"
    if summary.exists():
        logger.info(f"Parsing {summary}")
        entries = parse_summary(summary, content_root)
        if include_orphans:
            logger.info("Including orphaned markdown files")
            entries = add_orphan_markdown(entries, content_root)
    else:
        logger.info("No SUMMARY.md found, collecting all markdown files")
        entries = collect_markdown_files(content_root)

    if not entries:
        raise ProcessingError(f"No Markdown files found under {content_root}")

    logger.info(f"Found {len(entries)} pages")
    return entries


def write_output_files(
    out_dir: Path,
    title: str,
    description: Optional[str],
    entries: list[DocEntry],
    source_label: str,
    link_base: Optional[str],
    html_links: bool
) -> tuple[Path, Path]:
    """
    Generate and write output files.

    Args:
        out_dir: Output directory
        title: Documentation title
        description: Optional description
        entries: List of documentation entries
        source_label: Source identifier
        link_base: Optional base URL for links
        html_links: Whether to use .html links

    Returns:
        Tuple of (llms_txt_path, llms_full_txt_path)
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Generating llms.txt...")
    llms_txt = render_llms_txt(
        title=title,
        description=description,
        entries=entries,
        link_base=link_base,
        html_links=html_links,
    )

    logger.info("Generating llms-full.txt...")
    llms_full_txt = render_llms_full_txt(
        title=title,
        description=description,
        entries=entries,
        source_label=source_label,
    )

    llms_path = out_dir / "llms.txt"
    full_path = out_dir / "llms-full.txt"

    llms_path.write_text(llms_txt, encoding="utf-8")
    full_path.write_text(llms_full_txt, encoding="utf-8")

    return llms_path, full_path


def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns:
        Parsed arguments namespace
    """
    ap = argparse.ArgumentParser(
        description="Generate llms.txt and llms-full.txt from an mdBook source directory or GitHub tree URL.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s https://github.com/owner/repo/tree/main/docs
  %(prog)s ~/my-docs --link-base https://docs.example.com
  %(prog)s ./docs --html-links --no-include-orphans
        """
    )
    ap.add_argument(
        "input",
        help="Local mdBook/docs path or GitHub URL, e.g. https://github.com/org/repo/tree/main/docs",
    )
    ap.add_argument(
        "--out",
        default=".",
        help="Output directory. Default: current directory.",
    )
    ap.add_argument(
        "--link-base",
        default=None,
        help="Optional public base URL for links in llms.txt, e.g. https://docs.example.com",
    )
    ap.add_argument(
        "--html-links",
        action="store_true",
        help="Convert .md links to .html-style docs links in llms.txt.",
    )
    ap.add_argument(
        "--no-include-orphans",
        action="store_true",
        help="Only include pages referenced by SUMMARY.md.",
    )
    ap.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging.",
    )

    return ap.parse_args()


def main() -> None:
    """
    Main entry point for the mdBook to llms.txt converter.
    """
    args = parse_arguments()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    cleanup_dir = None

    try:
        # Quick check for existing output before expensive operations
        input_path = Path(args.input).expanduser()
        if input_path.exists():
            preliminary_project_name = input_path.name
        else:
            gh = parse_github_url(args.input)
            preliminary_project_name = gh.owner if gh else None

        # Check if output already exists
        if preliminary_project_name:
            base_out_dir = Path(args.out).expanduser().resolve()
            preliminary_out_dir = base_out_dir / "outputs" / preliminary_project_name
            if not check_existing_output(preliminary_out_dir):
                return

        # Materialize input (clone if needed)
        source_root, cleanup_dir, source_label = materialize_input(args.input)

        # Find mdBook content root
        content_root, config = find_mdbook_content_root(source_root)
        logger.info(f"Content root: {content_root}")

        # Collect documentation entries
        entries = collect_entries(
            content_root=content_root,
            include_orphans=not args.no_include_orphans,
        )

        # Infer metadata
        title, description = infer_title_and_description(
            source_root=source_root,
            content_root=content_root,
            config=config,
            source_label=source_label,
        )
        logger.info(f"Title: {title}")

        # Prepare output directory
        base_out_dir = Path(args.out).expanduser().resolve()
        project_name = extract_project_name(source_label, title)
        out_dir = base_out_dir / "outputs" / project_name

        # Generate and write output files
        llms_path, full_path = write_output_files(
            out_dir=out_dir,
            title=title,
            description=description,
            entries=entries,
            source_label=source_label,
            link_base=args.link_base,
            html_links=args.html_links,
        )

        # Print summary
        print(f"\n✓ Success!")
        print(f"  Content root:   {content_root}")
        print(f"  Pages included: {len(entries)}")
        print(f"  Project name:   {project_name}")
        print(f"  Wrote:          {llms_path}")
        print(f"  Wrote:          {full_path}")

    except ValidationError as e:
        logger.error(f"Validation error: {e}")
        sys.exit(1)
    except ProcessingError as e:
        logger.error(f"Processing error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nAborted by user.")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=args.verbose if 'args' in locals() else False)
        sys.exit(1)
    finally:
        if cleanup_dir and cleanup_dir.exists():
            logger.debug(f"Cleaning up {cleanup_dir}")
            shutil.rmtree(cleanup_dir, ignore_errors=True)


if __name__ == "__main__":
    main()