"""Tests for the multi-repository aggregation module."""

import json
import os

import pytest

from gitstats.aggregate import (
    AggregateReportCreator,
    _slugify_repo,
    compute_repo_summary,
    load_repo_summaries,
    write_repo_summary,
)

# ── _slugify_repo ────────────────────────────────────────────────────────


class TestSlugifyRepo:
    def test_basename(self):
        assert _slugify_repo("/home/user/projects/myrepo") == "myrepo"

    def test_trailing_separator(self):
        assert _slugify_repo("/home/user/projects/myrepo/") == "myrepo"

    def test_trailing_dot_git(self):
        assert _slugify_repo("/srv/git/myrepo.git") == "myrepo"

    def test_unsafe_characters_replaced(self):
        assert _slugify_repo("/tmp/my repo!") == "my-repo-"

    def test_relative_path(self):
        assert _slugify_repo("some-repo") == "some-repo"

    def test_root_rejected(self):
        with pytest.raises(ValueError):
            _slugify_repo("/")


# ── compute_repo_summary ─────────────────────────────────────────────────


class TestComputeRepoSummary:
    def test_basic_fields(self, mock_data_collector):
        summary = compute_repo_summary(mock_data_collector, "repo/index.html")

        assert summary["schema_version"] == 1
        assert summary["report_path"] == "repo/index.html"
        assert summary["name"] == mock_data_collector.project_name
        assert summary["total_commits"] == mock_data_collector.total_commits
        assert summary["total_files"] == mock_data_collector.total_files
        assert summary["total_lines"] == mock_data_collector.total_lines
        assert summary["total_tags"] == len(mock_data_collector.tags)
        assert summary["first_commit"]
        assert summary["last_commit"]
        assert summary["age_days"] >= 1

    def test_bots_excluded(self, mock_data_collector):
        mock_data_collector.authors = {
            "Alice": {"commits": 30, "last_commit_stamp": 1700000000},
            "dependabot[bot]": {"commits": 99, "last_commit_stamp": 1700000000},
        }
        summary = compute_repo_summary(mock_data_collector, "repo/index.html")

        assert summary["total_authors"] == 1
        assert "dependabot[bot]" not in summary["author_commits"]
        assert [a["name"] for a in summary["top_authors"]] == ["Alice"]

    def test_active_authors_window(self, mock_data_collector):
        import time

        now = time.time()
        mock_data_collector.authors = {
            "Fresh": {"commits": 5, "last_commit_stamp": now - 86400},
            "Stale": {"commits": 5, "last_commit_stamp": now - 400 * 86400},
        }
        summary = compute_repo_summary(mock_data_collector, "repo/index.html")

        assert summary["active_authors_12mo"] == 1

    def test_era_label_present(self, mock_data_collector):
        mock_data_collector.commits_by_year = {2021: 10, 2022: 40, 2023: 50}
        summary = compute_repo_summary(mock_data_collector, "repo/index.html")

        assert summary["era"] != ""
        assert list(summary["commits_by_year"]) == ["2021", "2022", "2023"]

    def test_top_authors_sorted_and_capped(self, mock_data_collector):
        mock_data_collector.authors = {
            f"author{i}": {"commits": i, "last_commit_stamp": 0} for i in range(1, 8)
        }
        summary = compute_repo_summary(mock_data_collector, "repo/index.html")

        assert len(summary["top_authors"]) == 5
        assert summary["top_authors"][0] == {"name": "author7", "commits": 7}


# ── write_repo_summary / load_repo_summaries ─────────────────────────────


class TestSummaryIO:
    def test_roundtrip(self, temp_dir):
        repo_dir = os.path.join(temp_dir, "repo")
        os.makedirs(repo_dir)
        write_repo_summary({"schema_version": 1, "name": "repo"}, repo_dir)

        with open(os.path.join(repo_dir, "summary.json"), encoding="utf-8") as f:
            assert json.load(f)["name"] == "repo"

        summaries = load_repo_summaries(temp_dir)
        assert len(summaries) == 1
        assert summaries[0]["name"] == "repo"

    def test_load_skips_dirs_without_summary(self, temp_dir):
        os.makedirs(os.path.join(temp_dir, "empty"))
        assert load_repo_summaries(temp_dir) == []

    def test_load_missing_root(self, temp_dir):
        assert load_repo_summaries(os.path.join(temp_dir, "nope")) == []


# ── AggregateReportCreator ───────────────────────────────────────────────


def _summary(name, commits, authors_map, **overrides):
    base = {
        "schema_version": 1,
        "name": name,
        "report_path": f"{name}/index.html",
        "first_commit": "2020-01-01 00:00:00",
        "last_commit": "2023-06-01 00:00:00",
        "age_days": 1200,
        "active_days": 300,
        "total_commits": commits,
        "total_authors": len(authors_map),
        "active_authors_12mo": 1,
        "commits_last_12mo": 10,
        "total_files": 10,
        "total_lines": 1000,
        "lines_added": 1500,
        "lines_removed": 500,
        "total_tags": 2,
        "era": "steady",
        "top_authors": [],
        "author_commits": authors_map,
        "commits_by_year": {},
    }
    base.update(overrides)
    return base


class TestAggregateReportCreator:
    def _render(self, temp_dir, summaries, failures=()):
        AggregateReportCreator().create(summaries, list(failures), temp_dir)
        with open(os.path.join(temp_dir, "index.html"), encoding="utf-8") as f:
            return f.read()

    def test_page_structure(self, temp_dir):
        html = self._render(
            temp_dir,
            [
                _summary("alpha", 100, {"Alice": 60, "Bob": 40}),
                _summary("beta", 50, {"Alice": 50}, era="dormant"),
            ],
        )

        assert '<table class="sortable" id="portfolio">' in html
        assert 'href="alpha/index.html"' in html
        assert 'href="beta/index.html"' in html
        assert "history-era-steady" in html
        assert "history-era-dormant" in html
        # Distinct authors = union, not the naive per-repo sum
        assert "<tr><td>Distinct Authors</td><td>2</td></tr>" in html
        assert "<tr><td>Total Commits</td><td>150</td></tr>" in html
        # Sorted by commits: alpha row before beta row
        assert html.index('href="alpha/index.html"') < html.index('href="beta/index.html"')

    def test_assets_copied(self, temp_dir):
        self._render(temp_dir, [_summary("alpha", 1, {"A": 1})])
        assert os.path.exists(os.path.join(temp_dir, "sortable.js"))
        assert os.path.exists(os.path.join(temp_dir, "gitstats.css"))
        assert not os.path.exists(os.path.join(temp_dir, "chart.umd.min.js"))

    def test_failures_section_escaped(self, temp_dir):
        html = self._render(
            temp_dir,
            [_summary("alpha", 1, {"A": 1})],
            failures=[{"name": "bad", "path": "/x", "error": "<script>boom</script>"}],
        )

        assert "Failed Repositories" in html
        assert "&lt;script&gt;boom&lt;/script&gt;" in html
        assert "<script>boom</script>" not in html

    def test_no_failures_section_when_empty(self, temp_dir):
        html = self._render(temp_dir, [_summary("alpha", 1, {"A": 1})])
        assert "Failed Repositories" not in html

    def test_repo_name_escaped(self, temp_dir):
        html = self._render(temp_dir, [_summary("a<b>", 1, {"A": 1})])
        assert "a&lt;b&gt;" in html
