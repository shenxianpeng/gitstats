# GitHub Copilot Instructions for GitStats

## Project Overview

GitStats is a Python-based tool that generates insightful visual reports from Git repositories. It analyzes Git history and produces HTML reports with statistics about commits, authors, activity patterns, files, lines of code, and tags.

### Key Features
- General statistics: total files, lines, commits, authors, age
- Activity analysis: commits by hour, day, week, month, year
- Author statistics: contributions, first/last commits, active periods
- File analysis: file count trends, extensions
- Line of code tracking over time
- Tag analysis by date and author
- Customizable via `gitstats.conf`
- Cross-platform support (Linux, Windows, macOS)

## Project Structure

```
gitstats/
├── gitstats/          # Main package directory
│   ├── main.py        # Entry point and DataCollector class
│   ├── report_creator.py  # HTMLReportCreator for generating reports
│   ├── utils.py       # Utility functions for Git operations
│   └── __init__.py    # Package initialization and config loading
├── docs/              # Sphinx documentation
├── .github/           # GitHub workflows and configurations
├── pyproject.toml     # Project configuration and dependencies
├── noxfile.py         # Development automation tasks
└── gitstats.conf      # Default configuration file
```

## Technology Stack

- **Language**: Python 3.9+
- **Dependencies**: gnuplot-wheel for chart generation
- **Build System**: setuptools with setuptools-scm for versioning
- **Documentation**: Sphinx with Read the Docs theme
- **Task Runner**: Nox for development tasks
- **Linting**: ruff, mypy, pre-commit hooks
- **Code Quality**: pre-commit with multiple hooks

## Development Guidelines

### Code Style

1. **Python Version**: Compatible with Python 3.9, 3.10, 3.11, 3.12, 3.13, 3.14
2. **Formatting**: Uses ruff for linting and formatting
3. **Type Hints**: MyPy is enabled; use type hints where appropriate
4. **Import Order**: Follow standard Python import conventions
5. **Environment**: Uses `os.environ["LC_ALL"] = "C"` for consistent output

### Configuration System

- Configuration is loaded via `load_config()` from `__init__.py`
- Default config is in `gitstats.conf`
- Config values include:
  - `max_domains`: Maximum number of domains to show
  - `max_ext_length`: Maximum extension length
  - `max_authors`: Maximum number of authors to display
  - `authors_top`: Number of top authors to highlight
  - `processes`: Number of parallel processes (default: 8)
  - Date ranges, author filters, and file exclusions

### Parallel Processing

- Uses multiprocessing with `parallel_map_with_fallback()` function
- Automatically falls back to sequential processing if multiprocessing is unavailable
- Configured via `conf["processes"]` setting

### Key Classes and Functions

#### DataCollector (main.py)
- Manages data collection from Git repositories
- Tracks activity patterns, authors, commits, lines of code
- Methods for analyzing Git history and generating statistics

#### HTMLReportCreator (report_creator.py)
- Generates HTML reports from collected data
- Creates charts using gnuplot
- Handles template rendering and output file generation

#### Utility Functions (utils.py)
- `get_pipe_output()`: Execute Git commands and capture output
- `get_commit_range()`: Determine commit range for analysis
- `get_version()`: Get gitstats version
- `should_exclude_file()`: Check if file should be excluded

## Development Workflow

### Setting Up Development Environment

```bash
pip install nox
pip install -e ".[dev,docs]"
pre-commit install
```

### Running Tasks with Nox

- `nox -s lint` - Run all linters and pre-commit hooks
- `nox -s build` - Generate a test report
- `nox -s preview` - Build and preview report locally on port 8000
- `nox -s docs` - Build Sphinx documentation
- `nox -s docs-live` - Live documentation preview with auto-reload
- `nox -s image` - Build Docker image
- `nox -s publish_image` - Publish Docker image to GHCR

### Pre-commit Hooks

The project uses several pre-commit hooks:
- YAML and TOML validation
- Trailing whitespace and end-of-file fixes
- RST file validation
- MyPy type checking
- Ruff linting and formatting
- Codespell for spell checking

Always run `pre-commit run --all-files` before committing.

### Testing

- No dedicated test framework currently (uses manual testing via `nox -s build`)
- Test by running gitstats on the repository itself
- Verify generated reports in `test-report/` directory
- Check both HTML output and optional JSON format

## Git Workflow

### Command Line Usage

```bash
gitstats <gitpath> <outputpath>
gitstats . report  # Analyze current repo, output to 'report/'
gitstats . report -f json  # Also generate JSON output
```

### Git Operations

- Uses `git log`, `git ls-tree`, `git rev-list`, etc. via `get_pipe_output()`
- All Git commands are executed with `LC_ALL=C` for consistent output
- Handles commit ranges, branch analysis, and tag information
- Supports filtering by date, author, and file extensions

## Documentation

- Documentation is in `docs/source/` using Sphinx
- Format: reStructuredText (.rst)
- Includes:
  - Getting started guide
  - Configuration reference
  - FAQ
  - Integration examples
  - Changelog
- Build with `nox -s docs` or preview with `nox -s docs-live`

## Contribution Guidelines

1. Fork and clone the repository
2. Create a feature branch
3. Install development dependencies: `pip install -e ".[dev,docs]"`
4. Make changes following the code style guidelines
5. Run linters: `nox -s lint`
6. Test your changes: `nox -s build` and verify the report
7. Update documentation if needed
8. Submit a pull request

## Common Patterns

### Adding New Statistics

1. Add data structure to `DataCollector.__init__()` in `main.py`
2. Collect data in appropriate method (e.g., `collect_data()`)
3. Add rendering logic in `HTMLReportCreator` in `report_creator.py`
4. Update templates or create new HTML sections
5. Consider adding configuration options to `gitstats.conf`

### Working with Git Data

- Use `get_pipe_output()` for all Git command execution
- Handle errors gracefully (Git commands may fail)
- Parse Git output carefully (dates, hashes, authors)
- Consider performance with large repositories

### Configuration Changes

1. Add default value to `gitstats.conf`
2. Document in `docs/source/configuration.rst`
3. Use via `conf['your_key']` after loading config
4. Handle missing or invalid config values gracefully

## Troubleshooting

- **Multiprocessing fails**: Automatically falls back to sequential processing
- **gnuplot errors**: Ensure gnuplot-wheel is installed correctly
- **Git command failures**: Check repository path and Git installation
- **Memory issues with large repos**: Adjust `processes` in config or use date filtering

## Additional Resources

- Documentation: https://gitstats.readthedocs.io/
- Example Report: https://shenxianpeng.github.io/gitstats/index.html
- Repository: https://github.com/shenxianpeng/gitstats
- Issue Tracker: https://github.com/shenxianpeng/gitstats/issues
