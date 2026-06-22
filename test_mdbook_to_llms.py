#!/usr/bin/env python3
"""
Test suite for mdbook_to_llms.py

Run with: python -m pytest test_mdbook_to_llms.py -v
Or simply: python test_mdbook_to_llms.py
"""

import tempfile
import unittest
from pathlib import Path

from mdbook_to_llms import (
    parse_github_url,
    extract_project_name,
    clean_title,
    split_link,
    is_external_link,
    first_h1,
    first_paragraph,
    strip_yaml_frontmatter,
    split_include_spec,
    parse_basic_toml,
    md_escape_link_text,
    GitHubRepo,
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
        from mdbook_to_llms import find_mdbook_content_root

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
