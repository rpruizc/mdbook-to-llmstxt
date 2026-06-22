"""Git and GitHub-related utilities."""

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from .exceptions import ValidationError, ProcessingError
from .models import GitHubRepo

logger = logging.getLogger(__name__)


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
        logger.error(
            f"Command failed: {' '.join(cmd)}\n"
            f"Exit code: {p.returncode}\n"
            f"stdout: {p.stdout}\n"
            f"stderr: {p.stderr}"
        )
        raise SystemExit(1)
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
