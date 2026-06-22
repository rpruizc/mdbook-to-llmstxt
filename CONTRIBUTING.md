# Contributing to mdBook to llms.txt

Thank you for your interest in contributing! This guide will help you get started.

## Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/rpruizc/llmstxt.git
   cd llmstxt
   ```

2. **Install development dependencies**
   ```bash
   uv sync --dev
   ```

3. **Verify your setup**
   ```bash
   uv run pytest test_*.py
   ```

## Development Workflow

### Making Changes

1. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Follow existing code style
   - Add docstrings to new functions
   - Include type hints
   - Update tests as needed

3. **Run tests**
   ```bash
   uv run pytest test_mdbook_to_llms.py -v
   ```

4. **Format your code**
   ```bash
   uv run black mdbook_to_llms.py test_mdbook_to_llms.py
   ```

5. **Commit your changes**
   ```bash
   git add .
   git commit -m "feat: add your feature description"
   ```

### Commit Message Convention

Use conventional commits:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `test:` - Test additions or changes
- `refactor:` - Code refactoring
- `chore:` - Maintenance tasks

### Pull Request Process

1. Push your branch to GitHub
2. Open a pull request against `main`
3. Describe your changes clearly
4. Link any related issues
5. Wait for review

## Code Style

### Python Style

- **PEP 8** compliant (enforced by `black`)
- **Type hints** on all function signatures
- **Docstrings** on all public functions (Google style)
- **Line length**: 100 characters max (black default)

Example:
```python
def my_function(param: str, optional: Optional[int] = None) -> bool:
    """
    Short description of what the function does.

    Longer explanation if needed.

    Args:
        param: Description of param
        optional: Description of optional parameter

    Returns:
        Description of return value

    Raises:
        ValueError: When something goes wrong
    """
    # Implementation
    return True
```

### Testing

- **Write tests** for all new functionality
- **Maintain coverage** - aim for >80%
- **Test edge cases** - don't just test the happy path
- **Use descriptive names** - test names should explain what they test

Example:
```python
def test_parse_github_url_with_tree_path(self):
    """Test parsing GitHub URL with tree path."""
    result = parse_github_url("https://github.com/owner/repo/tree/main/docs")
    self.assertEqual(result.tree_parts, ["main", "docs"])
```

## Architecture

### Key Components

1. **Input materialization** - `materialize_input()`
   - Handles both local paths and GitHub URLs
   - Clones repos to temp directories

2. **Content discovery** - `find_mdbook_content_root()`
   - Locates SUMMARY.md and content root
   - Parses book.toml configuration

3. **Entry collection** - `collect_entries()`
   - Parses SUMMARY.md structure
   - Finds orphaned markdown files

4. **Output generation** - `write_output_files()`
   - Renders llms.txt and llms-full.txt
   - Expands mdBook includes

### Adding New Features

When adding features:
1. **Keep functions small** - single responsibility
2. **Use type hints** - helps catch bugs early
3. **Add docstrings** - explain the why, not just the what
4. **Handle errors gracefully** - raise custom exceptions with helpful messages
5. **Log appropriately** - use `logger.debug()` for verbose, `logger.info()` for important

## Common Tasks

### Adding a New Command-Line Option

1. Add argument in `parse_arguments()`
2. Pass through to relevant function
3. Add test case
4. Update README.md

### Adding Support for New Documentation Format

1. Create parsing function (e.g., `parse_sphinx_index()`)
2. Add detection logic in `find_content_root()`
3. Write comprehensive tests
4. Document the new format in README.md

### Improving Error Messages

When improving error messages:
- **Be specific** - tell the user exactly what went wrong
- **Be actionable** - suggest how to fix it
- **Show context** - include relevant file paths or values

Example:
```python
raise ValidationError(
    f"Input must be a local path or GitHub URL.\n"
    f"Got: {value}\n"
    f"Example: https://github.com/owner/repo/tree/main/docs"
)
```

## Questions?

If you have questions:
- Open a discussion on GitHub
- Check existing issues for similar questions
- Review the test suite for examples

Thank you for contributing!
