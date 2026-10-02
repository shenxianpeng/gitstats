"""Tests for the multi-repository aggregation module."""

import json
import os
from unittest.mock import patch

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

    def test_load_skips_entry_that_commonpath_cannot_compare(self, temp_dir, monkeypatch):
        # A symlinked entry whose realpath lands on a different drive (or any
        # path commonpath() cannot compare to base) must be skipped, not
        # crash the whole call: os.path.commonpath() raises ValueError for
        # that case, which is not an OSError.
        repo_dir = os.path.join(temp_dir, "good")
        os.makedirs(repo_dir)
        write_repo_summary({"schema_version": 1, "name": "good"}, repo_dir)
        os.makedirs(os.path.join(temp_dir, "outside_link"))

        real_realpath = os.path.realpath

        def fake_realpath(path):
            if "outside_link" in path and path.endswith("summary.json"):
                return r"D:\outside\summary.json"
            return real_realpath(path)

        monkeypatch.setattr(os.path, "realpath", fake_realpath)

        summaries = load_repo_summaries(temp_dir)
        assert [s["name"] for s in summaries] == ["good"]


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
        # Totals as stat tiles; distinct authors = union, not the naive per-repo sum
        assert (
            '<dt>Repositories</dt><dd class="stat-value">2</dd>'
            '<dd class="stat-note">2 active in the last 12 months</dd>'
        ) in html
        assert (
            '<dt>Commits</dt><dd class="stat-value">150</dd>'
            '<dd class="stat-note">20 in the last 12 months</dd>'
        ) in html
        assert '<dt>Authors</dt><dd class="stat-value">2</dd>' in html
        assert '<dt>Lines of Code</dt><dd class="stat-value">2,000</dd>' in html
        assert "<h2>Totals</h2>" not in html
        # Repo table: Since column (first-commit year) replaces Age (days)
        assert "<th>Since</th>" in html
        assert "Age (days)" not in html
        assert "<td>2020</td>" in html
        assert '<th class="num">Lines of Code</th>' in html
        # Sorted by commits: alpha row before beta row
        assert html.index('href="alpha/index.html"') < html.index('href="beta/index.html"')

    def test_shares_report_theme_and_nav(self, temp_dir):
        html = self._render(temp_dir, [_summary("alpha", 10, {"Alice": 10})])

        assert "prefers-color-scheme: dark" in html
        assert 'class="icon-sun"' in html
        assert "\U0001f319" not in html
        assert html.count('aria-current="page"') == 1

    def test_tables_scroll_in_their_own_box(self, temp_dir):
        html = self._render(
            temp_dir,
            [_summary("alpha", 10, {"Alice": 10})],
            failures=[{"name": "bad", "path": "/x", "error": "boom"}],
        )
        # the repository and failure tables (totals are stat tiles)
        assert html.count("<table") == 2
        assert html.count('<div class="table-scroll"><table') == 2
        assert html.count("</table></div>") == 2

    def test_thousands_separators(self, temp_dir):
        html = self._render(
            temp_dir,
            [
                _summary(
                    "mega",
                    1234567,
                    {"A": 1234567},
                    total_lines=44025623,
                    commits_last_12mo=78432,
                )
            ],
        )

        assert '<dt>Commits</dt><dd class="stat-value">1,234,567</dd>' in html
        assert '<dd class="stat-note">78,432 in the last 12 months</dd>' in html
        assert '<dt>Lines of Code</dt><dd class="stat-value">44,025,623</dd>' in html
        # Repository table: numeric columns are right-aligned
        assert '<td class="num">1,234,567</td>' in html
        assert '<td class="num">44,025,623</td>' in html

    def test_inactive_repo_counted(self, temp_dir):
        html = self._render(
            temp_dir,
            [
                _summary("alpha", 100, {"A": 100}),
                _summary("stale", 50, {"B": 50}, commits_last_12mo=0),
            ],
        )

        assert '<dd class="stat-note">1 active in the last 12 months</dd>' in html

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

        assert "Failed repositories" in html
        assert "&lt;script&gt;boom&lt;/script&gt;" in html
        assert "<script>boom</script>" not in html

    def test_no_failures_section_when_empty(self, temp_dir):
        html = self._render(temp_dir, [_summary("alpha", 1, {"A": 1})])
        assert "Failed repositories" not in html

    def test_repo_name_escaped(self, temp_dir):
        html = self._render(temp_dir, [_summary("a<b>", 1, {"A": 1})])
        assert "a&lt;b&gt;" in html


# ── reading summaries and writing the page, unusual paths ────────────────


def test_load_repo_summaries_from_a_missing_directory(tmp_path):
    assert load_repo_summaries(str(tmp_path / "missing")) == []


def test_load_repo_summaries_skips_entries_it_cannot_place(tmp_path):
    """A path that can't be compared with the root (another drive on Windows) is skipped."""
    (tmp_path / "repo").mkdir()
    (tmp_path / "repo" / "summary.json").write_text('{"name": "repo"}', encoding="utf-8")
    with patch("gitstats.aggregate.os.path.commonpath", side_effect=ValueError("different drives")):
        assert load_repo_summaries(str(tmp_path)) == []


def test_compute_repo_summary_without_yearly_commits():
    class Empty:
        project_name = "empty"

    summary = compute_repo_summary(Empty(), "index.html")
    assert summary["era"] == ""
    assert summary["commits_by_year"] == {}
    assert summary["total_commits"] == 0


def test_copy_assets_skips_a_missing_stylesheet(tmp_path):
    import gitstats

    gitstats._config = dict(gitstats.DEFAULT_CONFIG, style="missing.css")
    AggregateReportCreator._copy_assets(str(tmp_path))
    assert (tmp_path / "sortable.js").exists()
    assert not (tmp_path / "missing.css").exists()


def test_copy_assets_refuses_to_write_outside_the_output(tmp_path):
    with (
        patch("gitstats.aggregate.os.path.commonpath", return_value=str(tmp_path / "elsewhere")),
        pytest.raises(ValueError, match="Refusing to write outside report directory"),
    ):
        AggregateReportCreator._copy_assets(str(tmp_path))


def test_portfolio_file_refuses_to_open_outside_the_output(tmp_path):
    with (
        patch("gitstats.aggregate.os.path.commonpath", return_value=str(tmp_path / "elsewhere")),
        pytest.raises(ValueError, match="Refusing to write outside report directory"),
    ):
        AggregateReportCreator._open_portfolio_file(str(tmp_path))
    assert not (tmp_path / "index.html").exists()


def test_load_repo_summaries_skips_unreadable_files(tmp_path, caplog):
    (tmp_path / "good").mkdir()
    (tmp_path / "good" / "summary.json").write_text('{"name": "good"}', encoding="utf-8")
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "summary.json").write_text("{not json", encoding="utf-8")

    assert load_repo_summaries(str(tmp_path)) == [{"name": "good"}]
    assert "Skipping unreadable summary" in caplog.text


def test_write_repo_summary_refuses_to_write_outside_the_report(tmp_path):
    with (
        patch("gitstats.aggregate.os.path.commonpath", return_value=str(tmp_path / "elsewhere")),
        pytest.raises(ValueError, match="Refusing to write outside report directory"),
    ):
        write_repo_summary({"name": "x"}, str(tmp_path))
    assert not (tmp_path / "summary.json").exists()
