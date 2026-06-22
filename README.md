# mdBook to llms.txt

Convert mdBook documentation (or any Markdown docs) into LLM-friendly text files.

## What it does

Takes a docs repo and generates two files:
- `llms.txt` - Table of contents with links
- `llms-full.txt` - All documentation in one file

Perfect for feeding documentation to Claude, ChatGPT, or other LLMs.

## Installation

Requires Python 3.10+ and git:

```bash
# Clone this repo
git clone https://github.com/YOUR_USERNAME/llmstxt.git
cd llmstxt

# Make it executable
chmod +x mdbook_to_llms_new.py
```

## Usage

### From a GitHub repo:

```bash
./mdbook_to_llms_new.py https://github.com/owner/repo/tree/main/docs
```

### From a local directory:

```bash
./mdbook_to_llms_new.py ~/path/to/docs
```

### With options:

```bash
# Add public URLs to links
./mdbook_to_llms_new.py https://github.com/owner/repo --link-base https://docs.example.com

# Convert .md links to .html
./mdbook_to_llms_new.py https://github.com/owner/repo --html-links

# Only include pages from SUMMARY.md
./mdbook_to_llms_new.py https://github.com/owner/repo --no-include-orphans

# Enable verbose logging
./mdbook_to_llms_new.py https://github.com/owner/repo --verbose
```

## Output

Files are saved to `outputs/{project-name}/`:
- `outputs/project-name/llms.txt`
- `outputs/project-name/llms-full.txt`

If files already exist, you'll be asked if you want to replace them.

## Example

```bash
./mdbook_to_llms_new.py https://github.com/rust-lang/mdBook/tree/master/guide

# Creates:
# outputs/rust-lang/llms.txt
# outputs/rust-lang/llms-full.txt
```

Now you can share `llms-full.txt` with an LLM and ask questions about the documentation.

## Development

### Running Tests

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run tests for modular version
python -m pytest test_mdbook_llms_modular.py -v

# Run tests with coverage
python -m pytest test_mdbook_llms_modular.py --cov=mdbook_llms --cov-report=html

# Run both test suites
python -m pytest test_*.py -v
```

### Code Quality

```bash
# Format code
black mdbook_llms/ mdbook_to_llms_new.py test_*.py

# Lint code
flake8 mdbook_llms/

# Type check
mypy mdbook_llms/
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
│   └── renderer.py          # Output rendering
├── mdbook_to_llms_new.py    # Main entry point (10 lines)
├── mdbook_to_llms.py        # Legacy monolithic version
├── test_mdbook_llms_modular.py  # Test suite (modular)
├── test_mdbook_to_llms.py   # Test suite (legacy)
├── requirements-dev.txt     # Development dependencies
├── outputs/                 # Generated files (gitignored)
│   └── project-name/
│       ├── llms.txt
│       └── llms-full.txt
├── CONTRIBUTING.md
├── IMPROVEMENTS.md
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
