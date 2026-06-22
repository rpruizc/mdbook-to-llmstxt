"""Command-line interface for mdbook_llms."""

import argparse
import logging
import re
import shutil
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from .exceptions import ValidationError, ProcessingError
from .git_utils import parse_github_url, materialize_input
from .models import DocEntry
from .parser import find_mdbook_content_root, parse_summary, add_orphan_markdown, collect_markdown_files, infer_title_and_description
from .renderer import render_llms_txt, render_llms_full_txt

logger = logging.getLogger(__name__)

DEFAULT_SITE_USER_AGENT = "llmstxt/1.0 (+https://github.com/rpruizc/llmstxt)"


def is_http_url(value: str) -> bool:
    """
    Check whether a value is an HTTP(S) URL.

    Args:
        value: Input value

    Returns:
        True for http:// or https:// URLs
    """
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_website_input(value: str) -> bool:
    """
    Check whether an input should use website ingestion.

    Args:
        value: CLI input value

    Returns:
        True for non-GitHub HTTP(S) URLs
    """
    return is_http_url(value) and parse_github_url(value) is None


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
        description=(
            "Generate llms.txt and llms-full.txt from an mdBook source directory, "
            "GitHub tree URL, or static documentation website."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s https://github.com/owner/repo/tree/main/docs
  %(prog)s ~/my-docs --link-base https://docs.example.com
  %(prog)s ./docs --html-links --no-include-orphans
  %(prog)s https://fastapicloud.com/docs/getting-started/ --max-pages 80
        """
    )
    ap.add_argument(
        "input",
        help=(
            "Local mdBook/docs path, GitHub URL, or static docs website URL, "
            "e.g. https://github.com/org/repo/tree/main/docs"
        ),
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
        "--site-prefix",
        default=None,
        help=(
            "Website crawl path prefix, e.g. /docs/. Defaults to /docs/ when the "
            "input URL is under /docs/, otherwise the input URL directory."
        ),
    )
    ap.add_argument(
        "--max-pages",
        type=int,
        default=100,
        help="Maximum website pages to fetch. Default: 100.",
    )
    ap.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="Website request timeout in seconds. Default: 20.",
    )
    ap.add_argument(
        "--user-agent",
        default=DEFAULT_SITE_USER_AGENT,
        help="User agent to use when fetching websites.",
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
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s: %(message)s'
    )

    args = parse_arguments()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    cleanup_dir = None

    try:
        # Quick check for existing output before expensive operations
        input_path = Path(args.input).expanduser()
        if input_path.exists():
            preliminary_project_name = input_path.name
        else:
            gh = parse_github_url(args.input)
            if gh:
                preliminary_project_name = gh.owner
            elif is_website_input(args.input):
                preliminary_project_name = urlparse(args.input).netloc
            else:
                preliminary_project_name = None

        # Check if output already exists
        if preliminary_project_name:
            base_out_dir = Path(args.out).expanduser().resolve()
            preliminary_out_dir = base_out_dir / "outputs" / preliminary_project_name
            if not check_existing_output(preliminary_out_dir):
                return

        if is_website_input(args.input):
            from .site_ingester import ingest_site

            result = ingest_site(
                start_url=args.input,
                site_prefix=args.site_prefix,
                max_pages=args.max_pages,
                timeout=args.timeout,
                user_agent=args.user_agent,
            )
            cleanup_dir = result.cleanup_dir
            logger.info(f"Content root: {result.content_root}")
            logger.info(f"Title: {result.title}")

            base_out_dir = Path(args.out).expanduser().resolve()
            out_dir = base_out_dir / "outputs" / result.project_name

            llms_path, full_path = write_output_files(
                out_dir=out_dir,
                title=result.title,
                description=result.description,
                entries=result.entries,
                source_label=result.source_label,
                link_base=args.link_base,
                html_links=args.html_links,
            )

            print("\n✓ Success!")
            print(f"  Content root:   {result.content_root}")
            print(f"  Pages included: {len(result.entries)}")
            print(f"  Project name:   {result.project_name}")
            print(f"  Wrote:          {llms_path}")
            print(f"  Wrote:          {full_path}")
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
        print("\n✓ Success!")
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
