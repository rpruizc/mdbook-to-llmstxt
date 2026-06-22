# Modular Architecture

This document explains the modular architecture of the `mdbook_llms` package.

## Overview

The codebase has been refactored from a single 1368-line file into a well-organized package with 7 focused modules, each with a clear responsibility.

## Module Breakdown

### 1. `__init__.py` (18 lines)
**Purpose:** Package initialization and public API

Exports the main public interfaces:
- Data models: `GitHubRepo`, `DocEntry`, `ProcessingConfig`
- Exceptions: `ValidationError`, `ProcessingError`

### 2. `exceptions.py` (11 lines)
**Purpose:** Custom exception definitions

- `ValidationError` - Input validation failures
- `ProcessingError` - Documentation processing failures

**Why separate?** Clear error hierarchy, easy to extend, imported by multiple modules.

### 3. `models.py` (37 lines)
**Purpose:** Data structures

Contains all dataclass definitions:
- `GitHubRepo` - Parsed GitHub repository information
- `DocEntry` - Documentation page entry
- `ProcessingConfig` - Processing configuration

**Why separate?** Centralized data definitions, no circular dependencies.

### 4. `git_utils.py` (265 lines)
**Purpose:** Git and GitHub operations

Functions:
- `parse_github_url()` - Parse GitHub URLs
- `clone_repo()` - Clone repositories
- `materialize_input()` - Convert input to local path
- `remote_refs()` - Fetch remote branches/tags
- `validate_environment()` - Check for required tools

**Why separate?** Isolates all git-related logic, could be replaced with other VCS systems.

### 5. `markdown_utils.py` (228 lines)
**Purpose:** Markdown parsing and processing

Functions:
- `first_h1()`, `first_paragraph()` - Extract metadata
- `clean_title()` - Clean formatting
- `strip_yaml_frontmatter()` - Remove frontmatter
- `expand_mdbook_includes()` - Process {{#include}} directives
- `split_include_spec()` - Parse include syntax

**Why separate?** Pure markdown processing, no I/O or side effects, highly testable.

### 6. `parser.py` (367 lines)
**Purpose:** mdBook-specific parsing

Functions:
- `parse_basic_toml()` - Parse book.toml
- `find_mdbook_content_root()` - Locate content directory
- `parse_summary()` - Parse SUMMARY.md
- `collect_markdown_files()` - Find all markdown files
- `add_orphan_markdown()` - Include unlinked files
- `infer_title_and_description()` - Extract metadata

**Why separate?** All mdBook-specific logic in one place, easy to add support for other formats.

### 7. `renderer.py` (180 lines)
**Purpose:** Output file generation

Functions:
- `render_llms_txt()` - Generate table of contents
- `render_llms_full_txt()` - Generate full documentation
- `link_for()` - Generate appropriate links
- `group_entries()` - Group by section

**Why separate?** Output formatting logic, easy to add new output formats.

### 8. `cli.py` (314 lines)
**Purpose:** Command-line interface

Functions:
- `main()` - Main entry point
- `parse_arguments()` - Argument parsing
- `extract_project_name()` - Determine output directory
- `check_existing_output()` - Prompt before overwrite
- `collect_entries()` - Orchestrate entry collection
- `write_output_files()` - Orchestrate file writing

**Why separate?** CLI concerns separate from core logic, easy to add web interface or API.

## Benefits of Modular Structure

### 1. **Clear Responsibilities**
Each module has a single, well-defined purpose. No confusion about where code belongs.

### 2. **Easy to Navigate**
- Need to modify git operations? → `git_utils.py`
- Need to change output format? → `renderer.py`
- Need to support a new doc format? → Add to `parser.py`

### 3. **Better Testability**
- Pure functions (markdown_utils) are trivial to test
- Each module can be tested independently
- Mock dependencies easily (e.g., mock git operations)

### 4. **Reduced Cognitive Load**
- Largest module is 367 lines (parser.py)
- Most modules are < 300 lines
- Can understand one module without loading entire codebase into memory

### 5. **Parallel Development**
Multiple developers can work on different modules without conflicts:
- Dev A adds new output format → `renderer.py`
- Dev B adds Sphinx support → `parser.py`
- Dev C improves git performance → `git_utils.py`

### 6. **Easy to Extend**
Want to add a new feature?

**Add new doc format (e.g., Sphinx):**
1. Add parsing logic to `parser.py`
2. Update `find_content_root()` to detect Sphinx
3. Done - no other modules affected

**Add JSON output:**
1. Add `render_json()` to `renderer.py`
2. Add `--format json` to `cli.py`
3. Done

**Add GitLab support:**
1. Add `parse_gitlab_url()` to `git_utils.py`
2. Update `materialize_input()`
3. Done

### 7. **Reusable Components**
Modules can be imported and used independently:

```python
# Use just the markdown processing
from mdbook_llms.markdown_utils import expand_mdbook_includes

# Use just the git utilities
from mdbook_llms.git_utils import clone_repo, parse_github_url

# Use just the renderer
from mdbook_llms.renderer import render_llms_txt
```

## Module Dependencies

```
cli.py
├── git_utils.py
│   ├── models.py
│   └── exceptions.py
├── parser.py
│   ├── models.py
│   ├── markdown_utils.py
│   └── exceptions.py
├── renderer.py
│   ├── models.py
│   └── markdown_utils.py
└── exceptions.py

No circular dependencies!
```

## Comparison: Before vs After

### Before (Monolithic)
```
mdbook_to_llms.py: 1368 lines
├── Imports
├── Constants
├── 50+ functions in no particular order
├── main() function (100+ lines)
└── if __name__ == "__main__"
```

**Problems:**
- Hard to find specific functionality
- Changes affect entire file
- Testing requires mocking entire module
- Merge conflicts likely

### After (Modular)
```
mdbook_llms/
├── __init__.py: 18 lines
├── exceptions.py: 11 lines (2 classes)
├── models.py: 37 lines (3 dataclasses)
├── git_utils.py: 265 lines (8 functions)
├── markdown_utils.py: 228 lines (9 functions)
├── parser.py: 367 lines (10 functions)
├── renderer.py: 180 lines (4 functions)
└── cli.py: 314 lines (7 functions)

mdbook_to_llms_new.py: 10 lines (entry point)
```

**Benefits:**
- Easy to locate functionality
- Changes isolated to specific modules
- Test individual modules independently
- Minimal merge conflicts

## Best Practices Applied

1. **Single Responsibility Principle**
   - Each module does one thing well

2. **Open/Closed Principle**
   - Easy to extend (add new formats) without modifying existing code

3. **Dependency Inversion**
   - CLI depends on abstractions (functions), not concrete implementations

4. **Don't Repeat Yourself (DRY)**
   - Common markdown processing in `markdown_utils.py`
   - Shared models in `models.py`

5. **Separation of Concerns**
   - I/O separate from logic
   - Parsing separate from rendering
   - CLI separate from core functionality

## Migration Path

Both versions coexist:

- **Legacy:** `mdbook_to_llms.py` (1368 lines, single file)
- **New:** `mdbook_to_llms_new.py` → `mdbook_llms/` package

Users can migrate gradually. Both versions have identical functionality.

To switch:
```bash
# Old
./mdbook_to_llms.py input

# New
./mdbook_to_llms_new.py input
```

Once comfortable with the new version, delete `mdbook_to_llms.py`.

## Future Enhancements Enabled by This Architecture

1. **Plugin System**
   ```python
   # Custom parser plugin
   from mdbook_llms.parser import register_parser
   
   @register_parser('sphinx')
   def parse_sphinx(root): ...
   ```

2. **Async Support**
   ```python
   # Add async variants in git_utils.py
   async def clone_repo_async(...): ...
   ```

3. **Multiple Output Formats**
   ```python
   # Add to renderer.py
   def render_json(...): ...
   def render_xml(...): ...
   def render_sqlite(...): ...
   ```

4. **Progress Callbacks**
   ```python
   # Add to cli.py
   def main(progress_callback=None):
       if progress_callback:
           progress_callback(percent=50, msg="Parsing...")
   ```

5. **Web API**
   ```python
   # New file: api.py
   from fastapi import FastAPI
   from mdbook_llms.git_utils import materialize_input
   from mdbook_llms.parser import find_mdbook_content_root
   
   @app.post("/convert")
   async def convert(url: str): ...
   ```

## Summary

The modular architecture transforms a 1368-line script into:
- **7 focused modules** (11-367 lines each)
- **No circular dependencies**
- **Clear separation of concerns**
- **Easy to test, extend, and maintain**

This is production-grade software architecture suitable for long-term maintenance and collaborative development.
