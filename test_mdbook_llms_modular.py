#!/usr/bin/env python3
"""
Test suite for mdbook_llms package.

Run with: python -m pytest test_mdbook_llms_modular.py -v
Or simply: python test_mdbook_llms_modular.py
"""

import tempfile
import unittest
from pathlib import Path

from mdbook_llms.git_utils import parse_github_url
from mdbook_llms.cli import extract_project_name
from mdbook_llms.markdown_utils import (
    clean_title,
    first_h1,
    first_paragraph,
    strip_yaml_frontmatter,
    split_include_spec,
    md_escape_link_text,
)
from mdbook_llms.parser import (
    split_link,
    is_external_link,
    parse_basic_toml,
    find_mdbook_content_root,
)
from mdbook_llms.site_ingester import (
    default_site_prefix,
    is_in_prefix,
    ordered_crawl_urls,
    parse_page,
    parse_sitemap_xml,
    sidebar_entries,
)


class TestGitHubURLParsing(unittest.TestCase):
    """Test parsing of GitHub URLs."""

    def test_basic_repo_url(self):
        """Test parsing basic GitHub repo URL."""
        result = parse_github_url("https://github.com/owner/repo")
        self.assertIsNotNone(result)
        self.assertEqual(result.owner, "owner")
        self.assertEqual(result.repo, "repo")
        self.assertEqual(result.repo_url, "https://github.com/owner/repo.git")
        self.assertEqual(result.tree_parts, [])

    def test_repo_with_tree_path(self):
        """Test parsing GitHub URL with tree path."""
        result = parse_github_url("https://github.com/owner/repo/tree/main/docs")
        self.assertIsNotNone(result)
        self.assertEqual(result.owner, "owner")
        self.assertEqual(result.repo, "repo")
        self.assertEqual(result.tree_parts, ["main", "docs"])

    def test_repo_with_git_extension(self):
        """Test parsing GitHub URL ending with .git."""
        result = parse_github_url("https://github.com/owner/repo.git")
        self.assertIsNotNone(result)
        self.assertEqual(result.repo, "repo")

    def test_invalid_url(self):
        """Test that invalid URLs return None."""
        self.assertIsNone(parse_github_url("https://gitlab.com/owner/repo"))
        self.assertIsNone(parse_github_url("not-a-url"))
        self.assertIsNone(parse_github_url("https://github.com/"))


class TestProjectNameExtraction(unittest.TestCase):
    """Test project name extraction logic."""

    def test_github_owner_extraction(self):
        """Test extracting owner from GitHub label."""
        self.assertEqual(
            extract_project_name("owner/repo@main", "Fallback"),
            "owner"
        )
        self.assertEqual(
            extract_project_name("micasa-dev/micasa@main/docs", "Fallback"),
            "micasa-dev"
        )

    def test_local_path_extraction(self):
        """Test extracting name from local path."""
        self.assertEqual(
            extract_project_name("/path/to/my-project", "Fallback"),
            "my-project"
        )

    def test_fallback_to_title(self):
        """Test falling back to title."""
        result = extract_project_name(".", "My Project Title")
        self.assertEqual(result, "My-Project-Title")


class TestMarkdownParsing(unittest.TestCase):
    """Test markdown parsing utilities."""

    def test_first_h1_extraction(self):
        """Test extracting first H1 from markdown."""
        md = "# My Title\n\nSome content"
        self.assertEqual(first_h1(md), "My Title")

        md = "## Not H1\n# Real Title"
        self.assertEqual(first_h1(md), "Real Title")

        md = "No title here"
        self.assertIsNone(first_h1(md))

    def test_first_paragraph_extraction(self):
        """Test extracting first paragraph from markdown."""
        md = "# Title\n\nThis is the first paragraph."
        self.assertEqual(first_paragraph(md), "This is the first paragraph.")

        md = "---\ntitle: test\n---\n\n# Title\n\nFirst para"
        self.assertEqual(first_paragraph(md), "First para")

    def test_clean_title(self):
        """Test cleaning markdown formatting from titles."""
        self.assertEqual(clean_title("`code` title"), "code title")
        self.assertEqual(clean_title("Title <span>tag</span>"), "Title tag")
        self.assertEqual(clean_title("Back\\slash"), "Backslash")


class TestLinkProcessing(unittest.TestCase):
    """Test link processing utilities."""

    def test_split_link(self):
        """Test splitting links into path and fragment."""
        self.assertEqual(split_link("page.md#section"), ("page.md", "#section"))
        self.assertEqual(split_link("page.md"), ("page.md", ""))

    def test_is_external_link(self):
        """Test external link detection."""
        self.assertTrue(is_external_link("https://example.com"))
        self.assertTrue(is_external_link("http://example.com"))
        self.assertTrue(is_external_link("mailto:test@example.com"))
        self.assertFalse(is_external_link("page.md"))
        self.assertFalse(is_external_link("/path/to/file"))

    def test_md_escape_link_text(self):
        """Test escaping square brackets in link text."""
        self.assertEqual(md_escape_link_text("[text]"), r"\[text\]")
        self.assertEqual(md_escape_link_text("normal"), "normal")


class TestStaticSiteIngestion(unittest.TestCase):
    """Test static website ingestion helpers."""

    def test_parse_sitemap_index_and_urlset(self):
        """Test parsing sitemap index and urlset XML."""
        index_xml = """<?xml version="1.0"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <sitemap><loc>https://example.com/sitemap-0.xml</loc></sitemap>
        </sitemapindex>
        """
        pages, sitemaps = parse_sitemap_xml(index_xml)
        self.assertEqual(pages, [])
        self.assertEqual(sitemaps, ["https://example.com/sitemap-0.xml"])

        urlset_xml = """<?xml version="1.0"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://example.com/docs/</loc></url>
          <url><loc>https://example.com/docs/getting-started/</loc></url>
        </urlset>
        """
        pages, sitemaps = parse_sitemap_xml(urlset_xml)
        self.assertEqual(sitemaps, [])
        self.assertEqual(pages, [
            "https://example.com/docs/",
            "https://example.com/docs/getting-started/",
        ])

    def test_default_site_prefix(self):
        """Test conservative default site prefix inference."""
        self.assertEqual(
            default_site_prefix("https://fastapicloud.com/docs/getting-started/"),
            "/docs/",
        )
        self.assertEqual(
            default_site_prefix("https://example.com/guide/intro/"),
            "/guide/intro/",
        )
        self.assertEqual(
            default_site_prefix("https://example.com/guide/intro.html"),
            "/guide/",
        )
        self.assertTrue(is_in_prefix("https://example.com/docs", "/docs/"))

    def test_ordered_crawl_urls_filters_dedupes_and_limits(self):
        """Test crawl ordering, prefix filtering, dedupe, and max pages."""
        start = "https://example.com/docs/getting-started/"
        sitemap_urls = [
            "https://example.com/docs/getting-started/",
            "https://example.com/docs/cli/",
            "https://example.com/blog/post/",
            "https://other.example.com/docs/outside/",
        ]
        sidebar = [
            ("https://example.com/docs/intro/", "Getting Started"),
            ("https://example.com/docs/cli/", "CLI"),
        ]

        urls, sections = ordered_crawl_urls(
            sitemap_urls=sitemap_urls,
            sidebar=sidebar,
            fallback_links=[],
            start_url=start,
            prefix="/docs/",
            max_pages=3,
        )

        self.assertEqual(urls, [
            "https://example.com/docs/getting-started/",
            "https://example.com/docs/cli/",
        ])
        self.assertEqual(sections, {
            "https://example.com/docs/intro": "Getting Started",
            "https://example.com/docs/cli": "CLI",
        })

    def test_starlight_sidebar_entries_preserve_sections(self):
        """Test parsing Starlight-style sidebar groups."""
        html = """
        <nav class="sidebar" aria-label="Main">
          <details open>
            <summary><span class="large">Getting Started</span></summary>
            <ul>
              <li><a href="/docs/getting-started/">Quick Start</a></li>
              <li><a href="/docs/getting-started/existing-project/">Existing</a></li>
            </ul>
          </details>
          <details open>
            <summary><span class="large">FastAPI Cloud CLI</span></summary>
            <ul>
              <li><a href="/docs/fastapi-cloud-cli/login/">Login</a></li>
            </ul>
          </details>
        </nav>
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        entries = sidebar_entries(soup, "https://fastapicloud.com/docs/getting-started/")

        self.assertEqual(entries, [
            ("https://fastapicloud.com/docs/getting-started/", "Getting Started"),
            (
                "https://fastapicloud.com/docs/getting-started/existing-project/",
                "Getting Started",
            ),
            ("https://fastapicloud.com/docs/fastapi-cloud-cli/login/", "FastAPI Cloud CLI"),
        ])

    def test_starlight_content_extraction_removes_navigation_noise(self):
        """Test extracting clean Markdown from Starlight-style HTML."""
        html = """
        <html>
          <head>
            <title>Quick Start | FastAPI Cloud Docs</title>
            <link rel="canonical" href="https://fastapicloud.com/docs/getting-started/">
            <meta name="description" content="FastAPI Cloud docs">
          </head>
          <body>
            <nav class="sidebar">Sidebar</nav>
            <div class="content-panel"><h1 id="_top">Quick Start</h1></div>
            <main>
              <div aria-label="On this page">On this page</div>
              <div class="sl-markdown-content">
                <p>Get your app deployed.</p>
                <div class="sl-heading-wrapper level-h2">
                  <h2 id="create">Create Your Project</h2>
                  <a class="sl-anchor-link" href="#create">
                    <span class="sr-only">Section titled Create Your Project</span>
                  </a>
                </div>
                <div class="tablist-wrapper"><ul role="tablist"><li>Using uv</li></ul></div>
                <div role="tabpanel">
                  <div class="expressive-code">
                    <figure>
                      <pre data-language="bash"><code>ignored</code></pre>
                      <button data-code="uvx fastapi-new myapp&#x7f;cd myapp"></button>
                    </figure>
                  </div>
                </div>
              </div>
            </main>
            <footer>Footer</footer>
          </body>
        </html>
        """

        page = parse_page(html, "https://fastapicloud.com/docs/getting-started/", "Docs")

        self.assertEqual(page.title, "Quick Start")
        self.assertEqual(page.url, "https://fastapicloud.com/docs/getting-started/")
        self.assertIn("# Quick Start", page.markdown)
        self.assertIn("Get your app deployed.", page.markdown)
        self.assertIn("uvx fastapi-new myapp", page.markdown)
        self.assertIn("cd myapp", page.markdown)
        self.assertNotIn("On this page", page.markdown)
        self.assertNotIn("Section titled", page.markdown)
        self.assertNotIn("Sidebar", page.markdown)


class TestYAMLFrontmatter(unittest.TestCase):
    """Test YAML frontmatter handling."""

    def test_strip_frontmatter(self):
        """Test removing YAML frontmatter."""
        md = "---\ntitle: test\n---\n\nContent here"
        result = strip_yaml_frontmatter(md)
        self.assertEqual(result.strip(), "Content here")

    def test_no_frontmatter(self):
        """Test handling markdown without frontmatter."""
        md = "# Title\n\nContent"
        result = strip_yaml_frontmatter(md)
        self.assertEqual(result, md)


class TestIncludeSpec(unittest.TestCase):
    """Test mdBook include specification parsing."""

    def test_simple_include(self):
        """Test parsing simple include."""
        path, start, end = split_include_spec("file.rs")
        self.assertEqual(path, "file.rs")
        self.assertIsNone(start)
        self.assertIsNone(end)

    def test_include_with_start(self):
        """Test parsing include with start line."""
        path, start, end = split_include_spec("file.rs:10")
        self.assertEqual(path, "file.rs")
        self.assertEqual(start, 10)
        self.assertIsNone(end)

    def test_include_with_range(self):
        """Test parsing include with line range."""
        path, start, end = split_include_spec("file.rs:10:20")
        self.assertEqual(path, "file.rs")
        self.assertEqual(start, 10)
        self.assertEqual(end, 20)

    def test_include_with_end_only(self):
        """Test parsing include with end line only."""
        path, start, end = split_include_spec("file.rs::20")
        self.assertEqual(path, "file.rs")
        self.assertIsNone(start)
        self.assertEqual(end, 20)


class TestTOMLParsing(unittest.TestCase):
    """Test basic TOML parsing."""

    def test_parse_basic_toml(self):
        """Test parsing simple TOML file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write('[book]\ntitle = "Test Book"\ndescription = "A test"\n')
            f.write('[build]\nsrc = "src"\n')
            f.flush()

            result = parse_basic_toml(Path(f.name))

            self.assertIn('book', result)
            self.assertEqual(result['book']['title'], 'Test Book')
            self.assertEqual(result['book']['description'], 'A test')
            self.assertIn('build', result)
            self.assertEqual(result['build']['src'], 'src')

            Path(f.name).unlink()

    def test_parse_nonexistent_toml(self):
        """Test parsing non-existent TOML file."""
        result = parse_basic_toml(Path("/nonexistent/file.toml"))
        self.assertEqual(result, {})


class TestEndToEnd(unittest.TestCase):
    """End-to-end integration tests."""

    def setUp(self):
        """Create temporary test directory structure."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

        # Create a simple mdBook structure
        src = self.temp_path / "src"
        src.mkdir()

        (src / "SUMMARY.md").write_text(
            "# Summary\n\n- [Introduction](intro.md)\n- [Chapter 1](chapter1.md)\n"
        )
        (src / "intro.md").write_text("# Introduction\n\nWelcome to the docs.")
        (src / "chapter1.md").write_text("# Chapter 1\n\nFirst chapter content.")

        (self.temp_path / "book.toml").write_text(
            '[book]\ntitle = "Test Book"\ndescription = "Test Description"\n'
        )

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_find_content_root(self):
        """Test finding mdBook content root."""
        content_root, config = find_mdbook_content_root(self.temp_path)

        # Resolve both paths to handle symlinks (e.g., /var vs /private/var on macOS)
        self.assertEqual(content_root.resolve(), (self.temp_path / "src").resolve())
        self.assertEqual(config['book']['title'], 'Test Book')


def run_tests():
    """Run all tests."""
    unittest.main(argv=[''], verbosity=2, exit=False)


if __name__ == "__main__":
    # Allow running with pytest or directly
    try:
        import pytest
        pytest.main([__file__, "-v"])
    except ImportError:
        print("pytest not found, running with unittest...")
        run_tests()
