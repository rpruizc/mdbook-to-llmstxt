# mdBook to llms.txt

Convert mdBook documentation, Markdown docs, or static documentation websites into LLM-friendly text files.

## What it does

Takes a docs repo or static docs website and generates two files:
- `llms.txt` - Table of contents with links
- `llms-full.txt` - All documentation in one file

Perfect for feeding documentation to Claude, ChatGPT, or other LLMs.

## Installation

Requires [uv](https://docs.astral.sh/uv/) and git for GitHub inputs:

```bash
# Clone this repo
git clone https://github.com/rpruizc/llmstxt.git
cd llmstxt

# Install dependencies
uv sync
```

## Usage

### From a GitHub repo:

```bash
uv run mdbook-to-llms https://github.com/owner/repo/tree/main/docs
```

### From a local directory:

```bash
uv run mdbook-to-llms ~/path/to/docs
```

### From a static docs website:

```bash
uv run mdbook-to-llms https://fastapicloud.com/docs/getting-started/ --max-pages 80
```

### With options:

```bash
# Add public URLs to links
uv run mdbook-to-llms https://github.com/owner/repo --link-base https://docs.example.com

# Convert .md links to .html
uv run mdbook-to-llms https://github.com/owner/repo --html-links

# Only include pages from SUMMARY.md
uv run mdbook-to-llms https://github.com/owner/repo --no-include-orphans

# Enable verbose logging
uv run mdbook-to-llms https://github.com/owner/repo --verbose

# Restrict website crawling to a path prefix
uv run mdbook-to-llms https://docs.example.com/guide/intro/ --site-prefix /guide/

# Tune website crawling
uv run mdbook-to-llms https://docs.example.com/docs/ --max-pages 200 --timeout 30
```

## Output

Files are saved to `outputs/{project-name}/`:
- `outputs/project-name/llms.txt`
- `outputs/project-name/llms-full.txt`

If files already exist, you'll be asked if you want to replace them.

## Example

```bash
uv run mdbook-to-llms https://github.com/rust-lang/mdBook/tree/master/guide

# Creates:
# outputs/rust-lang/llms.txt
# outputs/rust-lang/llms-full.txt
```

Now you can share `llms-full.txt` with an LLM and ask questions about the documentation.

## Development

### Running Tests

```bash
# Install development dependencies
uv sync --dev

# Run tests for modular version
uv run pytest test_mdbook_llms_modular.py -v

# Run tests with coverage
uv run pytest test_mdbook_llms_modular.py --cov=mdbook_llms --cov-report=html

# Run both test suites
uv run pytest test_*.py -v
```

### Code Quality

```bash
# Format code
uv run black mdbook_llms/ mdbook_to_llms_new.py test_*.py

# Lint code
uv run flake8 mdbook_llms/

# Type check
uv run mypy mdbook_llms/
```

### Project Structure

```
llmstxt/
├── mdbook_llms/             # Core package (modular)
│   ├── __init__.py
│   ├── cli.py              # Command-line interface
│   ├── exceptions.py        # Custom exceptions
│   ├── git_utils.py         # Git/GitHub utilities
│   ├── markdown_utils.py    # Markdown processing
│   ├── models.py            # Data models
│   ├── parser.py            # mdBook parsing
│   ├── renderer.py          # Output rendering
│   └── site_ingester.py     # Static website ingestion
├── mdbook_to_llms_new.py    # Main entry point (10 lines)
├── mdbook_to_llms.py        # Legacy monolithic version
├── test_mdbook_llms_modular.py  # Test suite (modular)
├── test_mdbook_to_llms.py   # Test suite (legacy)
├── pyproject.toml           # Project metadata and dependencies
├── uv.lock                  # Locked dependency versions
├── outputs/                 # Generated files (gitignored)
│   └── project-name/
│       ├── llms.txt
│       └── llms-full.txt
├── CONTRIBUTING.md
├── CHANGELOG.md
├── LICENSE
└── README.md
```

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Credits

Inspired by the [llms.txt](https://llmstxt.org/) format.
