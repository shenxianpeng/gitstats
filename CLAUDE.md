# Memory

## Me
Xianpeng Shen (shenxianpeng), DevOps engineer. Maintains the gitstats open source project.

## People
| Who | Role |
|-----|------|
| **Heikki Hokkanen** | Original author (hoxu), most commits historically |
| **dependabot** | Bot — automated dependency updates |
| **Copilot** | Bot — AI-assisted contributions |

## Projects
| Name | What |
|------|------|
| **gitstats** | Python tool that generates HTML/JSON reports with statistics from Git repos (commits, authors, activity, files, LOC, tags) |

## Tech Stack
- Python 3.9+ | gnuplot-wheel (charts) | Sphinx (docs) | Nox (task runner)
- Linting: ruff, mypy, pre-commit
- Config: `gitstats.conf`

## Key Commands
- `nox -s lint` — run linters
- `nox -s build` — generate test report
- `nox -s preview` — build + preview on port 8000
- `nox -s docs` — build docs
- `pre-commit run --all-files` — before committing

## Key Files
- `gitstats/main.py` — DataCollector class, entry point
- `gitstats/report_creator.py` — HTMLReportCreator
- `gitstats/utils.py` — Git command helpers
- `gitstats/__init__.py` — config loading
- `gitstats.conf` — default configuration
- `noxfile.py` — dev automation

## Preferences
- Branch for PRs: `main`
- Always run `nox -s lint` before committing
