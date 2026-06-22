"""Static website ingestion utilities."""

from __future__ import annotations

import logging
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib import robotparser
from urllib.parse import urljoin, urlparse, urlunparse
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup, Tag
from markdownify import markdownify as html_to_markdown

from .exceptions import ProcessingError, ValidationError
from .markdown_utils import clean_title
from .models import DocEntry

logger = logging.getLogger(__name__)


DEFAULT_USER_AGENT = "llmstxt/1.0 (+https://github.com/rpruizc/llmstxt)"


@dataclass
class SitePage:
    """A fetched documentation page."""

    url: str
    title: str
    description: Optional[str]
    markdown: str
    section: str


@dataclass
class SiteIngestionResult:
    """Result of static website ingestion."""

    source_root: Path
    content_root: Path
    cleanup_dir: Path
    source_label: str
    title: str
    description: Optional[str]
    project_name: str
    entries: list[DocEntry]


class SiteClient:
    """Small HTTP client for same-origin static docs ingestion."""

    def __init__(self, user_agent: str, timeout: float) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        self._robots: dict[str, robotparser.RobotFileParser] = {}

    def fetch_text(self, url: str) -> tuple[str, str]:
        """
        Fetch a URL as text.

        Args:
            url: URL to fetch

        Returns:
            Tuple of response text and content type

        Raises:
            ProcessingError: If the request fails
        """
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ProcessingError(f"Failed to fetch {url}: {exc}") from exc

        return response.text, response.headers.get("content-type", "")

    def can_fetch(self, url: str) -> bool:
        """
        Check conventional robots.txt rules for a URL.

        Args:
            url: URL to check

        Returns:
            True if robots.txt allows the configured user agent
        """
        parsed = urlparse(url)
        origin = origin_for(url)
        if origin not in self._robots:
            rp = robotparser.RobotFileParser()
            robots_url = urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))
            try:
                response = self.session.get(robots_url, timeout=self.timeout)
                if response.status_code == 200:
                    rp.parse(response.text.splitlines())
                else:
                    rp.parse([])
            except requests.RequestException:
                rp.parse([])
            self._robots[origin] = rp

        return self._robots[origin].can_fetch(self.user_agent, url)


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


def origin_for(url: str) -> str:
    """
    Return the scheme and host for a URL.

    Args:
        url: Absolute URL

    Returns:
        Origin string
    """
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))


def normalize_url(url: str) -> str:
    """
    Normalize a URL for crawling and output.

    Args:
        url: URL to normalize

    Returns:
        URL without query or fragment
    """
    parsed = urlparse(url)
    path = parsed.path or "/"
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def url_key(url: str) -> str:
    """
    Return a stable dedupe key for a URL.

    Args:
        url: URL to key

    Returns:
        Normalized URL key
    """
    normalized = normalize_url(url)
    parsed = urlparse(normalized)
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", "", ""))


def default_site_prefix(start_url: str) -> str:
    """
    Infer a conservative same-site crawl prefix.

    Args:
        start_url: Start URL

    Returns:
        URL path prefix to crawl
    """
    path = urlparse(start_url).path or "/"
    if path == "/docs" or path.startswith("/docs/"):
        return "/docs/"

    if path.endswith("/"):
        return path

    parent = path.rsplit("/", 1)[0]
    return (parent or "/") + "/"


def same_origin(url: str, origin: str) -> bool:
    """
    Check whether a URL belongs to an origin.

    Args:
        url: URL to check
        origin: Origin string

    Returns:
        True if URL is same-origin
    """
    return origin_for(url) == origin


def is_in_prefix(url: str, prefix: str) -> bool:
    """
    Check whether a URL path is inside a crawl prefix.

    Args:
        url: URL to check
        prefix: Path prefix

    Returns:
        True if URL path starts with the prefix
    """
    path = urlparse(url).path or "/"
    return path.startswith(prefix) or path.rstrip("/") == prefix.rstrip("/")


def text_from_node(node: Optional[Tag]) -> str:
    """
    Extract normalized text from a BeautifulSoup node.

    Args:
        node: HTML node

    Returns:
        Collapsed text
    """
    if node is None:
        return ""
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def meta_content(soup: BeautifulSoup, selector: str) -> Optional[str]:
    """
    Extract content from a meta selector.

    Args:
        soup: Parsed HTML
        selector: CSS selector

    Returns:
        Meta content, if present
    """
    node = soup.select_one(selector)
    if isinstance(node, Tag):
        value = node.get("content")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def canonical_url(soup: BeautifulSoup, page_url: str) -> str:
    """
    Extract a page canonical URL.

    Args:
        soup: Parsed HTML
        page_url: Fetched page URL

    Returns:
        Absolute canonical URL
    """
    link = soup.select_one("link[rel~=canonical][href]")
    if isinstance(link, Tag):
        href = link.get("href")
        if isinstance(href, str) and href.strip():
            return normalize_url(urljoin(page_url, href.strip()))
    return normalize_url(page_url)


def page_title(soup: BeautifulSoup) -> str:
    """
    Extract the title for a page.

    Args:
        soup: Parsed HTML

    Returns:
        Clean page title
    """
    h1 = text_from_node(soup.find("h1"))
    if h1:
        return clean_title(h1)

    og_title = meta_content(soup, 'meta[property="og:title"]')
    if og_title:
        return clean_title(og_title)

    if soup.title and soup.title.string:
        title = soup.title.string.split("|", 1)[0]
        return clean_title(title)

    return "Untitled"


def site_title(soup: BeautifulSoup, fallback: str) -> str:
    """
    Extract a documentation site title.

    Args:
        soup: Parsed start page HTML
        fallback: Fallback title

    Returns:
        Site title
    """
    og_site_name = meta_content(soup, 'meta[property="og:site_name"]')
    if og_site_name:
        return clean_title(og_site_name)

    if soup.title and soup.title.string:
        title = soup.title.string.strip()
        if "|" in title:
            return clean_title(title.split("|")[-1])
        return clean_title(title)

    return fallback


def site_description(soup: BeautifulSoup) -> Optional[str]:
    """
    Extract a site description.

    Args:
        soup: Parsed start page HTML

    Returns:
        Description, if present
    """
    return (
        meta_content(soup, 'meta[name="description"]')
        or meta_content(soup, 'meta[property="og:description"]')
    )


def parse_sitemap_xml(xml_text: str) -> tuple[list[str], list[str]]:
    """
    Parse sitemap XML.

    Args:
        xml_text: Sitemap XML text

    Returns:
        Tuple of (page_urls, nested_sitemap_urls)
    """
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        raise ProcessingError(f"Invalid sitemap XML: {exc}") from exc

    page_urls: list[str] = []
    sitemap_urls: list[str] = []

    locs = [
        elem.text.strip()
        for elem in root.iter()
        if elem.tag.endswith("loc") and elem.text and elem.text.strip()
    ]

    if root.tag.endswith("sitemapindex"):
        return [], locs

    if root.tag.endswith("urlset"):
        return locs, []

    return page_urls, sitemap_urls


def sitemap_links_from_page(soup: BeautifulSoup, page_url: str) -> list[str]:
    """
    Extract sitemap links from page metadata.

    Args:
        soup: Parsed page
        page_url: Page URL for resolving relative links

    Returns:
        Absolute sitemap URLs
    """
    links: list[str] = []
    for link in soup.select("link[href]"):
        rel = link.get("rel")
        rel_values = rel if isinstance(rel, list) else [rel]
        if not any(str(value).lower() == "sitemap" for value in rel_values if value):
            continue
        href = link.get("href")
        if isinstance(href, str) and href.strip():
            links.append(normalize_url(urljoin(page_url, href.strip())))
    return links


def discover_sitemap_urls(
    client: SiteClient,
    start_url: str,
    start_soup: BeautifulSoup,
) -> list[str]:
    """
    Discover page URLs from linked and conventional sitemaps.

    Args:
        client: Site HTTP client
        start_url: Start URL
        start_soup: Parsed start page

    Returns:
        Page URLs found in sitemaps
    """
    origin = origin_for(start_url)
    candidates = sitemap_links_from_page(start_soup, start_url)
    candidates.extend([
        urljoin(origin, "/sitemap.xml"),
        urljoin(origin, "/sitemap-index.xml"),
    ])

    seen_sitemaps: set[str] = set()
    seen_pages: set[str] = set()
    page_urls: list[str] = []
    queue = []

    for candidate in candidates:
        key = url_key(candidate)
        if key not in seen_sitemaps:
            seen_sitemaps.add(key)
            queue.append(candidate)

    while queue:
        sitemap_url = queue.pop(0)
        try:
            xml_text, _ = client.fetch_text(sitemap_url)
        except ProcessingError as exc:
            logger.debug("Skipping unavailable sitemap %s: %s", sitemap_url, exc)
            continue

        pages, nested = parse_sitemap_xml(xml_text)
        for nested_url in nested:
            normalized = normalize_url(nested_url)
            key = url_key(normalized)
            if same_origin(normalized, origin) and key not in seen_sitemaps:
                seen_sitemaps.add(key)
                queue.append(normalized)

        for page_url in pages:
            normalized = normalize_url(page_url)
            key = url_key(normalized)
            if same_origin(normalized, origin) and key not in seen_pages:
                seen_pages.add(key)
                page_urls.append(normalized)

    return page_urls


def sidebar_entries(
    soup: BeautifulSoup,
    page_url: str,
) -> list[tuple[str, str]]:
    """
    Extract ordered navigation entries from a docs sidebar.

    Args:
        soup: Parsed page HTML
        page_url: Page URL for resolving relative links

    Returns:
        List of (absolute_url, section)
    """
    sidebar = (
        soup.select_one("nav.sidebar")
        or soup.select_one("#starlight__sidebar")
        or soup.select_one('[aria-label="Main"]')
    )
    if not isinstance(sidebar, Tag):
        return []

    entries: list[tuple[str, str]] = []
    seen: set[str] = set()

    details_nodes = sidebar.select("details")
    for details in details_nodes:
        summary = details.find("summary")
        section = text_from_node(summary) or "Docs"
        for link in details.select("a[href]"):
            href = link.get("href")
            if not isinstance(href, str) or not href.strip():
                continue
            absolute = normalize_url(urljoin(page_url, href.strip()))
            key = url_key(absolute)
            if key in seen:
                continue
            seen.add(key)
            entries.append((absolute, section))

    if entries:
        return entries

    for link in sidebar.select("a[href]"):
        href = link.get("href")
        if not isinstance(href, str) or not href.strip():
            continue
        absolute = normalize_url(urljoin(page_url, href.strip()))
        key = url_key(absolute)
        if key in seen:
            continue
        seen.add(key)
        entries.append((absolute, "Docs"))

    return entries


def page_links(
    soup: BeautifulSoup,
    page_url: str,
) -> list[str]:
    """
    Extract same-page link candidates from a page.

    Args:
        soup: Parsed page
        page_url: Page URL for resolving relative links

    Returns:
        Absolute URLs
    """
    links: list[str] = []
    seen: set[str] = set()

    for link in soup.select("a[href]"):
        href = link.get("href")
        if not isinstance(href, str) or not href.strip():
            continue
        if href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        absolute = normalize_url(urljoin(page_url, href.strip()))
        key = url_key(absolute)
        if key in seen:
            continue
        seen.add(key)
        links.append(absolute)

    return links


def section_from_url(url: str, prefix: str) -> str:
    """
    Infer a section title from a URL path.

    Args:
        url: Page URL
        prefix: Crawl path prefix

    Returns:
        Human-readable section title
    """
    path = urlparse(url).path
    if path.startswith(prefix):
        path = path[len(prefix):]
    first = path.strip("/").split("/", 1)[0]
    if not first:
        return "Docs"
    return first.replace("-", " ").replace("_", " ").title()


def ordered_crawl_urls(
    sitemap_urls: list[str],
    sidebar: list[tuple[str, str]],
    fallback_links: list[str],
    start_url: str,
    prefix: str,
    max_pages: int,
) -> tuple[list[str], dict[str, str]]:
    """
    Merge sitemap and navigation discovery into an ordered crawl list.

    Args:
        sitemap_urls: URLs discovered from sitemaps
        sidebar: Ordered sidebar URLs with sections
        fallback_links: Links from the start page
        start_url: Canonical start URL
        prefix: Crawl path prefix
        max_pages: Maximum pages to crawl

    Returns:
        Tuple of ordered URLs and section map
    """
    origin = origin_for(start_url)
    section_map: dict[str, str] = {
        url_key(url): section for url, section in sidebar if same_origin(url, origin)
    }
    for url, section in sidebar:
        if not same_origin(url, origin):
            continue
        parsed = urlparse(url)
        if not parsed.path.startswith(prefix):
            continue
        remainder = parsed.path[len(prefix):].strip("/")
        if not remainder:
            continue
        first_segment = remainder.split("/", 1)[0]
        index_path = prefix + first_segment + "/"
        index_url = urlunparse((parsed.scheme, parsed.netloc, index_path, "", "", ""))
        section_map.setdefault(url_key(index_url), section)
    ordered: list[str] = []
    seen: set[str] = set()

    def add(url: str) -> None:
        normalized = normalize_url(url)
        key = url_key(normalized)
        if key in seen:
            return
        if not same_origin(normalized, origin):
            return
        if not is_in_prefix(normalized, prefix):
            return
        seen.add(key)
        ordered.append(normalized)

    add(start_url)

    sitemap_keys = {url_key(url) for url in sitemap_urls}
    for url, _section in sidebar:
        if sitemap_keys and url_key(url) not in sitemap_keys:
            continue
        add(url)

    source_urls = sitemap_urls if sitemap_urls else fallback_links
    for url in source_urls:
        add(url)

    return ordered[:max_pages], section_map


def replace_expressive_code_blocks(soup: BeautifulSoup) -> None:
    """
    Replace Starlight expressive-code wrappers with normal pre/code blocks.

    Args:
        soup: Parsed HTML to mutate
    """
    for container in soup.select(".expressive-code"):
        code_text = None
        button = container.select_one("button[data-code]")
        if isinstance(button, Tag):
            value = button.get("data-code")
            if isinstance(value, str):
                code_text = value.replace("\x7f", "\n")

        pre = container.find("pre")
        language = ""
        if isinstance(pre, Tag):
            value = pre.get("data-language")
            if isinstance(value, str):
                language = value
            if code_text is None:
                lines = []
                for line in pre.select(".ec-line"):
                    code = line.select_one(".code")
                    lines.append((code or line).get_text("", strip=False))
                code_text = "\n".join(lines) if lines else pre.get_text("\n", strip=False)

        if code_text is None:
            code_text = container.get_text("\n", strip=True)

        new_pre = soup.new_tag("pre")
        new_code = soup.new_tag("code")
        if language:
            new_code["class"] = [f"language-{language}"]
        new_code.string = code_text.strip("\n")
        new_pre.append(new_code)
        container.replace_with(new_pre)


def absolutize_content_links(soup: BeautifulSoup, page_url: str) -> None:
    """
    Resolve relative links and image sources before Markdown conversion.

    Args:
        soup: Parsed content
        page_url: Current page URL
    """
    for link in soup.select("a[href]"):
        href = link.get("href")
        if isinstance(href, str) and href.strip() and not href.startswith(("mailto:", "tel:")):
            link["href"] = urljoin(page_url, href.strip())

    for img in soup.select("img[src]"):
        src = img.get("src")
        if isinstance(src, str) and src.strip():
            img["src"] = urljoin(page_url, src.strip())


def remove_noise(soup: BeautifulSoup) -> None:
    """
    Remove non-content elements before Markdown conversion.

    Args:
        soup: Parsed HTML to mutate
    """
    selectors = [
        "script",
        "style",
        "link",
        "template",
        "svg",
        "button",
        "nav",
        "header",
        "footer",
        "site-search",
        "starlight-theme-select",
        "starlight-menu-button",
        ".sl-anchor-link",
        ".sr-only",
        ".copy",
        ".tablist-wrapper",
        '[role="tablist"]',
        '[aria-label="Search"]',
        '[aria-label="On this page"]',
    ]
    for selector in selectors:
        for node in soup.select(selector):
            node.decompose()


def content_node(soup: BeautifulSoup) -> Optional[Tag]:
    """
    Find the main documentation content node.

    Args:
        soup: Parsed page

    Returns:
        Main content node, if found
    """
    for selector in [".sl-markdown-content", "article", "main", '[role="main"]']:
        node = soup.select_one(selector)
        if isinstance(node, Tag):
            return node
    return None


def extract_markdown(soup: BeautifulSoup, page_url: str, title: str) -> str:
    """
    Extract Markdown content from a static HTML page.

    Args:
        soup: Parsed page
        page_url: Current page URL
        title: Page title

    Returns:
        Markdown body
    """
    replace_expressive_code_blocks(soup)
    node = content_node(soup)
    if not isinstance(node, Tag):
        raise ProcessingError(f"Could not find main content in {page_url}")

    remove_noise(node)
    absolutize_content_links(node, page_url)

    markdown = html_to_markdown(
        str(node),
        heading_style="ATX",
        bullets="-",
        strip=["script", "style"],
    )
    markdown = markdown.replace("\r\n", "\n")
    markdown = re.sub(r"\n[ \t]+\n", "\n\n", markdown)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    markdown = markdown.strip()

    if not markdown.startswith("# "):
        markdown = f"# {title}\n\n{markdown}" if markdown else f"# {title}"

    return markdown.strip() + "\n"


def parse_page(html: str, page_url: str, section: str) -> SitePage:
    """
    Parse a fetched HTML page into Markdown.

    Args:
        html: HTML text
        page_url: Page URL
        section: Documentation section

    Returns:
        Parsed site page
    """
    soup = BeautifulSoup(html, "html.parser")
    canonical = canonical_url(soup, page_url)
    title = page_title(soup)
    description = site_description(soup)
    markdown = extract_markdown(soup, canonical, title)
    return SitePage(
        url=canonical,
        title=title,
        description=description,
        markdown=markdown,
        section=section,
    )


def safe_page_filename(url: str) -> str:
    """
    Convert a URL into a safe temporary Markdown filename.

    Args:
        url: Page URL

    Returns:
        Markdown filename
    """
    path = urlparse(url).path.strip("/") or "index"
    path = re.sub(r"[^A-Za-z0-9._/-]+", "-", path)
    path = path.strip("/").replace("/", "__") or "index"
    return f"{path}.md"


def rel_for_url(url: str) -> str:
    """
    Convert a URL into the renderer's source label.

    Args:
        url: Page URL

    Returns:
        URL path without leading slash
    """
    path = urlparse(url).path.lstrip("/")
    return path or "/"


def ingest_site(
    start_url: str,
    site_prefix: Optional[str],
    max_pages: int,
    timeout: float,
    user_agent: str,
) -> SiteIngestionResult:
    """
    Ingest a static documentation website into temporary Markdown files.

    Args:
        start_url: Start URL
        site_prefix: Optional crawl path prefix
        max_pages: Maximum pages to crawl
        timeout: HTTP timeout in seconds
        user_agent: User agent for HTTP requests

    Returns:
        Site ingestion result
    """
    if not is_http_url(start_url):
        raise ValidationError(f"Website input must be an http(s) URL: {start_url}")
    if max_pages < 1:
        raise ValidationError("--max-pages must be at least 1")
    if timeout <= 0:
        raise ValidationError("--timeout must be greater than 0")

    start_url = normalize_url(start_url)
    prefix = site_prefix or default_site_prefix(start_url)
    if not prefix.startswith("/"):
        prefix = "/" + prefix
    if not prefix.endswith("/"):
        prefix += "/"

    client = SiteClient(user_agent=user_agent, timeout=timeout)
    if not client.can_fetch(start_url):
        raise ProcessingError(f"robots.txt disallows fetching {start_url}")

    start_html, content_type = client.fetch_text(start_url)
    if "html" not in content_type.lower() and content_type:
        raise ProcessingError(f"Start URL is not HTML: {start_url} ({content_type})")

    start_soup = BeautifulSoup(start_html, "html.parser")
    canonical_start = canonical_url(start_soup, start_url)
    origin = origin_for(canonical_start)
    title = site_title(start_soup, fallback=urlparse(canonical_start).netloc)
    description = site_description(start_soup)

    nav_entries = [
        (url, section)
        for url, section in sidebar_entries(start_soup, canonical_start)
        if same_origin(url, origin) and is_in_prefix(url, prefix)
    ]
    fallback = [
        url
        for url in page_links(start_soup, canonical_start)
        if same_origin(url, origin) and is_in_prefix(url, prefix)
    ]
    sitemap_urls = [
        url
        for url in discover_sitemap_urls(client, canonical_start, start_soup)
        if same_origin(url, origin) and is_in_prefix(url, prefix)
    ]
    crawl_urls, section_map = ordered_crawl_urls(
        sitemap_urls=sitemap_urls,
        sidebar=nav_entries,
        fallback_links=fallback,
        start_url=canonical_start,
        prefix=prefix,
        max_pages=max_pages,
    )

    if not crawl_urls:
        raise ProcessingError(f"No crawlable documentation pages found under {prefix}")

    temp_root = Path(tempfile.mkdtemp(prefix="llmstxt-site-"))
    content_root = temp_root / "pages"
    content_root.mkdir(parents=True, exist_ok=True)

    entries: list[DocEntry] = []
    used_filenames: set[str] = set()

    for page_url in crawl_urls:
        if not client.can_fetch(page_url):
            logger.warning("Skipping robots.txt-disallowed URL: %s", page_url)
            continue

        try:
            html, page_content_type = client.fetch_text(page_url)
        except ProcessingError as exc:
            logger.warning("%s", exc)
            continue

        if "html" not in page_content_type.lower() and page_content_type:
            logger.debug("Skipping non-HTML URL: %s (%s)", page_url, page_content_type)
            continue

        section = section_map.get(url_key(page_url), section_from_url(page_url, prefix))
        try:
            page = parse_page(html, page_url, section=section)
        except ProcessingError as exc:
            logger.warning("%s", exc)
            continue

        filename = safe_page_filename(page.url)
        if filename in used_filenames:
            stem = filename[:-3]
            suffix = 2
            while f"{stem}-{suffix}.md" in used_filenames:
                suffix += 1
            filename = f"{stem}-{suffix}.md"
        used_filenames.add(filename)

        path = content_root / filename
        path.write_text(page.markdown, encoding="utf-8")
        entries.append(DocEntry(
            title=page.title,
            path=path,
            rel=rel_for_url(page.url),
            fragment="",
            section=page.section,
            url=page.url,
        ))

    if not entries:
        raise ProcessingError(f"No documentation pages could be extracted from {start_url}")

    return SiteIngestionResult(
        source_root=temp_root,
        content_root=content_root,
        cleanup_dir=temp_root,
        source_label=canonical_start,
        title=title,
        description=description,
        project_name=urlparse(canonical_start).netloc,
        entries=entries,
    )
