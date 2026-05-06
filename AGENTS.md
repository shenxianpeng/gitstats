# Project Context

GitStats is a Python CLI tool that generates HTML/JSON reports with statistics from Git repositories (commits, authors, activity, files, LOC, tags).

## Build & Test Commands

```bash
nox -s lint      # Run ruff, mypy, pre-commit checks
nox -s build     # Generate test report into test-report/
nox -s preview   # Build report + serve on http://127.0.0.1:8000
nox -s docs      # Build Sphinx docs to docs/build/html/
```

Before committing: `pre-commit run --all-files`

## Architecture

| Module | Purpose |
|--------|---------|
| `gitstats/main.py` | Entry point and `DataCollector` class |
| `gitstats/report_creator.py` | `HTMLReportCreator` — generates HTML with Chart.js |
| `gitstats/utils.py` | Git command helpers (`get_pipe_output`, etc.) |
| `gitstats/__init__.py` | Config loading via `load_config()` |
| `gitstats.conf` | Default config (max_authors, processes, exclusions, …) |
| `noxfile.py` | Dev automation tasks |

## Tech Stack

Python 3.10+ | Chart.js (bundled, browser-side) | Sphinx | Nox | ruff + mypy + pre-commit

## Conventions

- PR target branch: `main`
- Always run `nox -s lint` before committing
- Git commands use `LC_ALL=C` for reproducible output
- Use `parallel_map_with_fallback()` for parallel processing — falls back to sequential
- Charts rendered browser-side via bundled `chart.umd.min.js`

## Language

Always reply in the same language the user writes in. If the user writes in Chinese, respond in Chinese.
