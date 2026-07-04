"""Shared fixtures for gitstats tests."""

import datetime
import os
import shutil
import subprocess
import tempfile
from unittest.mock import Mock

import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory that is cleaned up after the test."""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def git_repo(temp_dir):
    """Create a minimal git repository with a few commits for integration tests.

    Creates a repo at temp_dir/git_repo with:
        - 3 commits by 2 authors
        - files with different extensions
        - at least one tag
    """
    repo_path = os.path.join(temp_dir, "git_repo")
    os.makedirs(repo_path)

    def _run_git(*args):
        subprocess.run(
            ["git"] + list(args),
            cwd=repo_path,
            check=True,
            env={**os.environ, "LC_ALL": "C", "GIT_AUTHOR_DATE": "", "GIT_COMMITTER_DATE": ""},
            capture_output=True,
        )

    def _run_git_author(name, email, date, *args):
        env = {
            **os.environ,
            "LC_ALL": "C",
            "GIT_AUTHOR_NAME": name,
            "GIT_AUTHOR_EMAIL": email,
            "GIT_COMMITTER_NAME": name,
            "GIT_COMMITTER_EMAIL": email,
            "GIT_AUTHOR_DATE": date,
            "GIT_COMMITTER_DATE": date,
        }
        subprocess.run(
            ["git"] + list(args),
            cwd=repo_path,
            check=True,
            env=env,
            capture_output=True,
        )

    # Initialize repo
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Commit 1: alice creates initial files
    with open(os.path.join(repo_path, "README.md"), "w") as f:
        f.write("# Test Repo\n\nHello world.\n")
    with open(os.path.join(repo_path, "main.py"), "w") as f:
        f.write("print('hello')\nprint('world')\n")
    _run_git("add", "README.md", "main.py")
    _run_git_author(
        "Alice Smith",
        "alice@example.com",
        "2023-01-15T10:00:00",
        "commit",
        "-m",
        "Initial commit",
    )

    # Commit 2: bob adds a file
    with open(os.path.join(repo_path, "utils.py"), "w") as f:
        f.write("def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n")
    _run_git("add", "utils.py")
    _run_git_author(
        "Bob Jones",
        "bob@example.com",
        "2023-02-20T14:00:00",
        "commit",
        "-m",
        "Add utils module",
    )

    # Tag the first release
    _run_git("tag", "v1.0.0")

    # Commit 3: alice modifies main.py
    with open(os.path.join(repo_path, "main.py"), "w") as f:
        f.write("print('hello, world!')\nprint('foo')\nprint('bar')\n")
    _run_git("add", "main.py")
    _run_git_author(
        "Alice Smith",
        "alice@example.com",
        "2023-03-10T08:30:00",
        "commit",
        "-m",
        "Improve greeting",
    )

    # Commit 4: alice adds a binary file (image)
    with open(os.path.join(repo_path, "logo.png"), "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    _run_git("add", "logo.png")
    _run_git_author(
        "Alice Smith",
        "alice@example.com",
        "2023-04-05T16:00:00",
        "commit",
        "-m",
        "Add logo",
    )

    # Tag the second release
    _run_git("tag", "v1.1.0")

    # Commit 5: alice adds a .gitignore
    with open(os.path.join(repo_path, ".gitignore"), "w") as f:
        f.write("*.pyc\n__pycache__/\n")
    _run_git("add", ".gitignore")
    _run_git_author(
        "Alice Smith",
        "alice@example.com",
        "2023-05-01T09:00:00",
        "commit",
        "-m",
        "Add gitignore",
    )

    return repo_path


@pytest.fixture
def git_repo_minimal(temp_dir):
    """Minimal git repo with exactly 2 commits for fast tests."""
    repo_path = os.path.join(temp_dir, "git_repo_minimal")
    os.makedirs(repo_path)

    env = {**os.environ, "LC_ALL": "C"}

    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True, env=env)
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        env=env,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        env=env,
    )

    with open(os.path.join(repo_path, "file.txt"), "w") as f:
        f.write("line 1\n")
    subprocess.run(
        ["git", "add", "file.txt"], cwd=repo_path, check=True, capture_output=True, env=env
    )
    env.update(
        {"GIT_AUTHOR_DATE": "2023-06-01T12:00:00", "GIT_COMMITTER_DATE": "2023-06-01T12:00:00"}
    )
    subprocess.run(
        ["git", "commit", "-m", "first"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        env=env,
    )

    return repo_path


@pytest.fixture
def mock_data_collector():
    """Create a highly simplified DataCollector-like object for testing report generation.

    Returns a mock with minimal attributes needed by HTMLReportCreator.
    """
    data = Mock()
    data.project_name = "test-project"
    data.get_stamp_created.return_value = 1000000.0

    # General stats
    data.total_authors = 3
    data.total_commits = 50
    data.total_files = 25
    data.total_lines = 2000
    data.total_lines_added = 3000
    data.total_lines_removed = 1000
    data.total_size = 50000

    data.get_total_authors.return_value = 3
    data.get_total_commits.return_value = 50
    data.get_total_files.return_value = 25
    data.get_total_loc.return_value = 2000
    data.get_total_size.return_value = 50000

    # Dates
    data.first_commit_stamp = 1670000000
    data.last_commit_stamp = 1680000000
    data.get_first_commit_date.return_value = datetime.datetime(2022, 12, 1, 0, 0)
    data.get_last_commit_date.return_value = datetime.datetime(2023, 4, 1, 0, 0)

    # Active days
    data.get_active_days.return_value = {"2023-01-01", "2023-01-15", "2023-02-01", "2023-03-10"}
    data.get_longest_streak.return_value = 4
    data.longest_streak = 4
    data.get_commit_delta_days.return_value = 120

    # Activity
    data.activity_by_hour_of_day = {9: 10, 14: 15, 16: 8}
    data.activity_by_hour_of_day_busiest = 15
    data.get_activity_by_hour_of_day.return_value = data.activity_by_hour_of_day

    data.activity_by_day_of_week = {0: 8, 1: 10, 2: 12, 3: 7, 4: 9, 5: 2, 6: 2}
    data.get_activity_by_day_of_week.return_value = data.activity_by_day_of_week

    data.activity_by_hour_of_week = {d: {h: 1 for h in range(9, 17)} for d in range(5)}
    data.activity_by_hour_of_week_busiest = 2

    data.activity_by_month_of_year = {1: 5, 2: 10, 3: 15, 4: 8, 5: 7, 6: 5}
    data.commits_by_month = {
        "2023-01": 5,
        "2023-02": 10,
        "2023-03": 15,
        "2023-04": 8,
        "2023-05": 7,
        "2023-06": 5,
    }
    data.commits_by_year = {2023: 50}

    data.lines_added_by_month = {
        "2023-01": 300,
        "2023-02": 600,
        "2023-03": 900,
    }
    data.lines_removed_by_month = {
        "2023-01": 100,
        "2023-02": 200,
        "2023-03": 300,
    }
    data.lines_added_by_year = {2023: 3000}
    data.lines_removed_by_year = {2023: 1000}

    data.activity_by_year_week = {"2023-01": 5, "2023-02": 10}

    # Authors
    data.authors = {
        "Alice Smith": {
            "commits": 30,
            "lines_added": 2000,
            "lines_removed": 500,
            "date_first": "2023-01-15",
            "date_last": "2023-06-15",
            "timedelta": datetime.timedelta(days=150),
            "active_days": {f"2023-{m:02d}-{d:02d}" for m in range(1, 7) for d in (1, 15)},
            "place_by_commits": 1,
            "commits_frac": 60.0,
        },
        "Bob Jones": {
            "commits": 15,
            "lines_added": 800,
            "lines_removed": 300,
            "date_first": "2023-02-01",
            "date_last": "2023-05-30",
            "timedelta": datetime.timedelta(days=118),
            "active_days": {f"2023-{m:02d}-01" for m in range(2, 6)},
            "place_by_commits": 2,
            "commits_frac": 30.0,
        },
        "Charlie Brown": {
            "commits": 5,
            "lines_added": 200,
            "lines_removed": 200,
            "date_first": "2023-03-10",
            "date_last": "2023-04-20",
            "timedelta": datetime.timedelta(days=41),
            "active_days": {f"2023-03-{d:02d}" for d in (10, 20)},
            "place_by_commits": 3,
            "commits_frac": 10.0,
        },
    }
    data.get_authors.side_effect = lambda limit=None: (
        list(data.authors.keys()) if limit is None else list(data.authors.keys())[:limit]
    )
    data.get_author_info.side_effect = lambda author: data.authors.get(author, {})

    # Author time series
    data.changes_by_date_by_author = {}

    # Author of month/year
    data.author_of_month = {
        "2023-01": {"Alice Smith": 5},
        "2023-02": {"Alice Smith": 6, "Bob Jones": 4},
        "2023-03": {"Alice Smith": 8, "Bob Jones": 5, "Charlie Brown": 2},
        "2023-04": {"Alice Smith": 5, "Bob Jones": 2, "Charlie Brown": 1},
        "2023-05": {"Alice Smith": 4, "Bob Jones": 3},
        "2023-06": {"Alice Smith": 2, "Bob Jones": 1, "Charlie Brown": 2},
    }
    data.author_of_year = {
        2023: {"Alice Smith": 30, "Bob Jones": 15, "Charlie Brown": 5},
    }

    # Domains
    data.domains = {
        "example.com": {"commits": 30},
        "test.org": {"commits": 15},
        "unknown.com": {"commits": 5},
    }
    data.get_domains.return_value = list(data.domains.keys())
    data.get_domain_info.side_effect = lambda d: data.domains.get(d, {"commits": 0})

    # File stats
    data.files_by_stamp = {}
    data.extensions = {
        "py": {"files": 10, "lines": 800},
        "md": {"files": 5, "lines": 200},
        "txt": {"files": 3, "lines": 100},
    }
    data.file_churn = {
        "main.py": 15,
        "utils.py": 10,
        "README.md": 8,
        "tests/test_main.py": 5,
        "Dockerfile": 2,
    }

    # Collaboration network (mock data for page generation tests)
    data.author_files = {
        "Alice Smith": {"main.py": 5, "utils.py": 3, "README.md": 2},
        "Bob Jones": {"main.py": 3, "utils.py": 4, "README.md": 1, "Makefile": 2},
        "Charlie Brown": {"utils.py": 1, "README.md": 1},
    }
    data.collaboration_graph = {
        "Alice Smith": {"Bob Jones": 3, "Charlie Brown": 1},
        "Bob Jones": {"Alice Smith": 3, "Charlie Brown": 1},
        "Charlie Brown": {"Alice Smith": 1, "Bob Jones": 1},
    }

    # Changes by date (lines)
    data.changes_by_date = {}

    # Tags
    data.tags = {
        "v1.0.0": {
            "date": "2023-02-20",
            "commits": 2,
            "authors": {"Alice Smith": 1, "Bob Jones": 1},
            "hash": "abc123",
            "stamp": 1677000000,
        },
        "v1.1.0": {
            "date": "2023-04-05",
            "commits": 4,
            "authors": {"Alice Smith": 3, "Bob Jones": 1},
            "hash": "def456",
            "stamp": 1680000000,
        },
    }

    # Timezone
    data.commits_by_timezone = {"+0800": 30, "-0500": 15, "+0000": 5}

    # New contributors
    data.new_contributors_by_month = {
        "2023-01": 1,
        "2023-02": 1,
        "2023-03": 1,
    }

    # AI summaries (disabled by default)
    data.ai_summaries = {}

    return data


@pytest.fixture
def mock_data_collector_with_ai(mock_data_collector):
    """Mock DataCollector with AI summaries enabled."""
    data = mock_data_collector
    data.ai_summaries = {
        "index": {"summary": "<p>This project is healthy and active.</p>"},
        "activity": {"summary": "<p>Most activity happens on weekdays.</p>"},
        "lines": {"summary": "<p>Codebase is growing steadily.</p>"},
    }
    return data


@pytest.fixture
def mock_data_collector_with_ai_error(mock_data_collector):
    """Mock DataCollector with AI summaries that had errors."""
    data = mock_data_collector
    data.ai_summaries = {
        "index": {"error": "API rate limit exceeded"},
        "activity": {"summary": "<p>Activity patterns normal.</p>"},
    }
    return data


@pytest.fixture(autouse=True)
def reset_config():
    """Reset the cached config before each test to avoid cross-test pollution."""
    import gitstats
    import gitstats.main
    import gitstats.report_creator
    import gitstats.utils

    cfg = gitstats.DEFAULT_CONFIG.copy()
    gitstats._config = cfg
    gitstats.utils.conf = cfg
    gitstats.main.conf = cfg
    gitstats.report_creator.conf = cfg
    yield
    gitstats._config = None
    gitstats.utils.conf = gitstats.DEFAULT_CONFIG.copy()
    gitstats.main.conf = gitstats.DEFAULT_CONFIG.copy()
    gitstats.report_creator.conf = gitstats.DEFAULT_CONFIG.copy()
