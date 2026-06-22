# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- Comprehensive type hints throughout the codebase
- Docstrings for all public functions (Google style)
- Custom exception classes (`ValidationError`, `ProcessingError`)
- Logging system with `--verbose` flag for debug output
- Dataclasses for structured data (`GitHubRepo`, `DocEntry`, `ProcessingConfig`)
- Test suite with 22 test cases covering critical functionality
- Development dependencies in `requirements-dev.txt`
- Contributing guidelines in `CONTRIBUTING.md`
- Comprehensive `.gitignore` file
- Better error messages with actionable suggestions
- Early validation before expensive operations (cloning)
- Check for existing output files with user confirmation

### Changed
- Refactored monolithic `main()` function into smaller, focused functions
- Replaced `print()` statements with proper logging
- Improved error handling with specific exception types
- Better user-facing output formatting
- Enhanced CLI help text with examples

### Fixed
- Path resolution issues on macOS (symlink handling in tests)

## [1.0.0] - Initial Release

### Added
- Initial implementation
- GitHub URL support with branch/path parsing
- Local directory support
- mdBook SUMMARY.md parsing
- Orphaned file detection
- YAML frontmatter stripping
- mdBook `{{#include}}` directive expansion
- Line range support for includes
- Project name extraction
- Output organization in `outputs/{project-name}/`
- `llms.txt` generation (table of contents)
- `llms-full.txt` generation (full documentation)
- Optional `--link-base` for public URLs
- Optional `--html-links` for .html conversion
- Optional `--no-include-orphans` flag
