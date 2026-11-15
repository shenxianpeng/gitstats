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

## Tech Stack

Python 3.10+ | Chart.js (bundled, browser-side) | Sphinx | Nox | ruff + mypy + pre-commit

## Conventions

- PR target branch: `main`
- Always run `nox -s lint` before committing
- `gitstats/` and `scripts/` are type-checked as `mypy --strict` checks (see `[tool.mypy]` in `pyproject.toml`): annotate every new function, and add a new script to the list there
- Git commands use `LC_ALL=C` for reproducible output
- Use `parallel_map_with_fallback()` for parallel processing — falls back to sequential
- Charts rendered browser-side via bundled `chart.umd.min.js`

## Language

Always reply in the same language the user writes in. If the user writes in Chinese, respond in Chinese.
