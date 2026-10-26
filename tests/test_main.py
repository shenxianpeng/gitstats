"""Tests for gitstats.main – DataCollector, parameter parsing, and integration with real git repos."""

import datetime
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from gitstats.main import (
    DataCollector,
    GitDataCollector,
    _apply_ai_args,
    _dump_json_within,
    _make_server,
    _prepare_output_dir,
    _run_multi_repo,
    _run_single_repo,
    _serve_report,
    _server_urls,
    configure_logging,
    get_parser,
    main,
    normalize_site_url,
    parallel_map_with_fallback,
    run,
)
from gitstats.utils import get_log_range
from gitstats.wrapped import THEMES

# ── DataCollector base class ─────────────────────────────────────────────


class TestDataCollector:
    def test_init(self):
        dc = DataCollector()
        assert dc.total_authors == 0
        assert dc.total_commits == 0
        assert dc.total_files == 0
        assert dc.authors == {}
        assert dc.tags == {}
        assert dc.active_days == set()

    def test_collect_sets_dir_and_project_name(self, temp_dir):
        dc = DataCollector()
        dc.collect(temp_dir)
        assert dc.dir == temp_dir
        assert dc.project_name == os.path.basename(os.path.abspath(temp_dir))

    def test_collect_with_config_project_name(self, temp_dir):
        import gitstats
        import gitstats.main

        cfg = dict(gitstats.DEFAULT_CONFIG, project_name="my-custom-project")
        gitstats._config = cfg
        gitstats.main.conf = cfg
        dc = DataCollector()
        dc.collect(temp_dir)
        assert dc.project_name == "my-custom-project"

    def test_save_and_load_cache(self, temp_dir):
        dc = DataCollector()
        dc.cache = {"files_in_tree": {"abc": 100}, "lines_in_blob": {"def": 50}}

        cachefile = os.path.join(temp_dir, "test.cache")
        dc.save_cache(cachefile)
        assert os.path.exists(cachefile)

        # Load into a new instance
        dc2 = DataCollector()
        dc2.load_cache(cachefile)
        assert dc2.cache == dc.cache

    def test_load_cache_nonexistent_file(self):
        dc = DataCollector()
        dc.load_cache("/nonexistent/path/to/cache")
        assert dc.cache == {}

    def test_load_cache_empty(self, temp_dir):
        cachefile = os.path.join(temp_dir, "empty.cache")
        with open(cachefile, "w") as f:
            f.write("not valid json")

        dc = DataCollector()
        # JSON cache gracefully handles corrupted files
        dc.load_cache(cachefile)
        assert dc.cache == {}

    def test_get_stamp_created(self):
        dc = DataCollector()
        assert dc.get_stamp_created() > 0

    # ── Accessors (on GitDataCollector) ──────────────────────────────────────────────────────

    def test_get_authors_empty(self):
        dc = GitDataCollector()
        assert dc.get_authors() == []

    def test_get_total_methods(self):
        dc = GitDataCollector()
        assert dc.get_total_authors() == 0
        assert dc.get_total_commits() == 0
        assert dc.get_total_files() == 0
        assert dc.get_total_loc() == 0
        assert dc.get_total_size() == 0

    def test_get_commit_delta_days(self):
        dc = GitDataCollector()
        dc.first_commit_stamp = 86400
        dc.last_commit_stamp = 86400 * 2
        assert dc.get_commit_delta_days() >= 1


# ── parallel_map_with_fallback ───────────────────────────────────────────


def _square(x):
    """Test helper function defined at module level for pickling."""
    return x * x


def test_parallel_map_with_fallback_basic():
    """parallel_map_with_fallback should correctly apply a function to items."""
    results = parallel_map_with_fallback(_square, [1, 2, 3, 4])
    assert results == [1, 4, 9, 16]


def test_parallel_map_with_fallback_empty():
    results = parallel_map_with_fallback(lambda x: x, [])
    assert results == []


# ── GitDataCollector integration tests ───────────────────────────────────


class TestGitDataCollectorIntegration:
    """Tests that require a real git repository (fixture: git_repo)."""

    def test_collect_basic(self, git_repo):
        """Full collect() on the test repo should not crash."""
        dc = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(git_repo)
            dc.collect(git_repo)
        finally:
            os.chdir(prevdir)

        assert dc.project_name == os.path.basename(os.path.abspath(git_repo))
        assert dc.total_commits > 0
        # every file at HEAD, for ownership and churn to skip deleted ones
        assert "utils.py" in dc.head_files
        assert len(dc.head_files) == dc.total_files

    def test_collect_authors(self, git_repo):
        dc = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(git_repo)
            dc.collect(git_repo)
        finally:
            os.chdir(prevdir)

        # Alice and Bob should both appear in authors dict
        assert "Alice Smith" in dc.authors
        assert "Bob Jones" in dc.authors
        assert dc.authors["Alice Smith"]["commits"] > 0

    def test_collect_without_matching_commits(self, git_repo):
        import gitstats

        gitstats._config["start_date"] = "2099-01-01"
        dc = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(git_repo)
            with pytest.raises(RuntimeError, match="No commits to analyze"):
                dc.collect(git_repo)
        finally:
            os.chdir(prevdir)

    def test_collect_tags(self, git_repo):
        dc = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(git_repo)
            dc.collect(git_repo)
        finally:
            os.chdir(prevdir)

        assert len(dc.tags) >= 2
        assert "v1.0.0" in dc.tags
        assert "v1.1.0" in dc.tags

        # Tags should have commits and authors
        t = dc.tags["v1.0.0"]
        assert t["commits"] > 0
        assert len(t["authors"]) > 0

    def test_collect_tags_counts_commits_since_previous_tag(self, git_repo):
        dc = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(git_repo)
            dc.collect(git_repo)
        finally:
            os.chdir(prevdir)

        # v1.0.0 tags the first two commits, v1.1.0 the next two; the fifth
        # commit is untagged and must not be counted in either
        assert dc.tags["v1.0.0"]["commits"] == 2
        assert dc.tags["v1.1.0"]["commits"] == 2

    def test_collect_warns_about_a_shallow_clone(self, git_repo, temp_dir, caplog):
        # CI checkouts are shallow by default; the report must say it covers
        # only the fetched history instead of silently under-counting.
        shallow = os.path.join(temp_dir, "shallow_clone")
        subprocess.run(
            ["git", "clone", "--depth", "1", Path(git_repo).resolve().as_uri(), shallow],
            check=True,
            capture_output=True,
        )
        dc = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(shallow)
            with caplog.at_level("WARNING", logger="gitstats"):
                dc.collect(shallow)
        finally:
            os.chdir(prevdir)

        assert dc.shallow is True
        assert "shallow clone" in caplog.text
        assert "git fetch --unshallow" in caplog.text

    def test_collect_full_clone_is_not_shallow(self, git_repo, caplog):
        dc = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(git_repo)
            with caplog.at_level("WARNING", logger="gitstats"):
                dc.collect(git_repo)
        finally:
            os.chdir(prevdir)

        assert dc.shallow is False
        assert "shallow clone" not in caplog.text

    def test_collect_tags_same_day_are_ordered_by_history(self, temp_dir):
        # Two tags whose commits carry the same timestamp: the ordering has to
        # come from the history. Sorting on the "%Y-%m-%d" date broke the tie by
        # tag name, so "b-later" sorted first and took "a-first"'s commit,
        # leaving the older tag with none.
        repo = os.path.join(temp_dir, "same_day_tags")
        os.makedirs(repo)
        env = {
            **os.environ,
            "LC_ALL": "C",
            "GIT_AUTHOR_NAME": "Tag Dev",
            "GIT_AUTHOR_EMAIL": "tag@example.com",
            "GIT_COMMITTER_NAME": "Tag Dev",
            "GIT_COMMITTER_EMAIL": "tag@example.com",
            "GIT_AUTHOR_DATE": "2024-01-01T00:00:00+0000",
            "GIT_COMMITTER_DATE": "2024-01-01T00:00:00+0000",
        }

        def run(*args):
            subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, env=env)

        run("init")
        with open(os.path.join(repo, "one.txt"), "w") as handle:
            handle.write("one")
        run("add", ".")
        run("commit", "-m", "first")
        run("tag", "b-later")
        with open(os.path.join(repo, "two.txt"), "w") as handle:
            handle.write("two")
        run("add", ".")
        run("commit", "-m", "second")
        run("tag", "a-first")

        dc = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(repo)
            dc.collect(repo)
        finally:
            os.chdir(prevdir)

        # one commit each: the tag on the older commit keeps its own
        assert dc.tags["b-later"]["commits"] == 1
        assert dc.tags["a-first"]["commits"] == 1

    def test_collect_tags_ordered_by_history_despite_clock_skew(self, temp_dir):
        # "new" is a child of "old" but committed with an earlier date, and a
        # merge also reaches "old" directly. Sorted on commit dates, rev-list
        # lists "old" first, so "new" took both commits and "old" none;
        # --topo-order keeps descendants before their ancestors.
        repo = os.path.join(temp_dir, "skewed_tags")
        os.makedirs(repo)
        base_env = {
            **os.environ,
            "LC_ALL": "C",
            "GIT_AUTHOR_NAME": "Tag Dev",
            "GIT_AUTHOR_EMAIL": "tag@example.com",
            "GIT_COMMITTER_NAME": "Tag Dev",
            "GIT_COMMITTER_EMAIL": "tag@example.com",
        }

        def run(date, *args):
            env = {**base_env, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
            return subprocess.run(
                ["git", *args], cwd=repo, check=True, capture_output=True, text=True, env=env
            ).stdout.strip()

        day = "2024-01-{:02d}T00:00:00+0000".format
        run(day(1), "init")
        with open(os.path.join(repo, "f.txt"), "w") as handle:
            handle.write("old")
        run(day(5), "add", ".")
        run(day(5), "commit", "-m", "old")
        run(day(5), "tag", "old")
        with open(os.path.join(repo, "f.txt"), "w") as handle:
            handle.write("new")
        run(day(1), "commit", "-am", "new")
        run(day(1), "tag", "new")
        tree = run(day(10), "write-tree")
        merge = run(day(10), "commit-tree", tree, "-p", "new", "-p", "old", "-m", "merge")
        run(day(10), "reset", "--hard", merge)

        dc = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(repo)
            dc.collect(repo)
        finally:
            os.chdir(prevdir)

        assert dc.tags["old"]["commits"] == 1
        assert dc.tags["new"]["commits"] == 1
        # The report orders tags from this position, so "new" being the
        # descendant must rank ahead of "old" despite its earlier date.
        assert dc.tags["new"]["order"] < dc.tags["old"]["order"]

    def test_collect_annotated_tags(self, git_repo):
        subprocess.run(
            ["git", "tag", "-a", "v2.0.0", "-m", "release 2.0.0"],
            cwd=git_repo,
            check=True,
            capture_output=True,
            env={
                **os.environ,
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "test@example.com",
            },
        )
        dc = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(git_repo)
            dc.collect(git_repo)
        finally:
            os.chdir(prevdir)

        assert "v2.0.0" in dc.tags
        assert dc.tags["v2.0.0"]["commits"] == 1

    def test_collect_activity_by_hour(self, git_repo):
        dc = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(git_repo)
            dc.collect(git_repo)
        finally:
            os.chdir(prevdir)

        assert dc.activity_by_hour_of_day  # not empty
        assert dc.activity_by_hour_of_day_busiest > 0

    def test_collect_activity_by_weekday(self, git_repo):
        dc = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(git_repo)
            dc.collect(git_repo)
        finally:
            os.chdir(prevdir)

        assert dc.activity_by_day_of_week  # not empty

    def test_collect_extensions(self, git_repo):
        dc = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(git_repo)
            dc.collect(git_repo)
        finally:
            os.chdir(prevdir)

        # .py and .md should be present
        assert "py" in dc.extensions
        assert "md" in dc.extensions
        # png is counted as an extension but with 0 lines (binary)
        assert dc.extensions.get("png", {}).get("lines", 0) == 0

    def test_collect_line_stats(self, git_repo):
        dc = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(git_repo)
            dc.collect(git_repo)
        finally:
            os.chdir(prevdir)

        assert dc.total_lines > 0
        assert dc.total_lines_added > 0

    def test_collect_file_churn(self, git_repo):
        dc = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(git_repo)
            dc.collect(git_repo)
        finally:
            os.chdir(prevdir)

        # File churn may be empty or non-empty depending on diff output
        assert isinstance(dc.file_churn, dict)

    def test_collect_author_files(self, git_repo):
        """The name-only pass records which files each author touched."""
        dc = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(git_repo)
            dc.collect(git_repo)
        finally:
            os.chdir(prevdir)

        # Alice: README.md + main.py (2 commits) + logo.png + .gitignore; Bob: utils.py
        assert dc.author_files["Alice Smith"] == {
            "README.md": 1,
            "main.py": 2,
            "logo.png": 1,
            ".gitignore": 1,
        }
        assert dc.author_files["Bob Jones"] == {"utils.py": 1}
        # file_churn comes from the same pass
        assert dc.file_churn["main.py"] == 2

    def test_collect_hotspot_files(self, git_repo):
        """Every counted file at HEAD gets its lines, its churn and a score."""
        dc = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(git_repo)
            dc.collect(git_repo)
        finally:
            os.chdir(prevdir)

        # sizes come with the extensions pass; churn and score wait for refine()
        assert dc.hotspot_files["main.py"] == {"lines": 3, "churn": 0, "score": 0.0}
        dc.refine()

        assert dc.hotspot_files["main.py"] == {"lines": 3, "churn": 2, "score": 2 * 3**0.5}
        assert dc.hotspot_files["utils.py"] == {"lines": 5, "churn": 1, "score": 5**0.5}
        assert dc.hotspot_files["README.md"]["lines"] == 3
        # a binary file has no lines, so it scores nothing however often it changes
        assert dc.hotspot_files["logo.png"] == {"lines": 0, "churn": 1, "score": 0.0}
        # files without an extension are not counted as lines of code, nor here
        assert ".gitignore" in dc.head_files
        assert ".gitignore" not in dc.hotspot_files

    def test_collect_changes_by_date(self, git_repo):
        dc = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(git_repo)
            dc.collect(git_repo)
        finally:
            os.chdir(prevdir)

        assert dc.changes_by_date  # not empty

    def test_collect_domains(self, git_repo):
        dc = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(git_repo)
            dc.collect(git_repo)
        finally:
            os.chdir(prevdir)

        # Domains should contain at least the email domains from our commits
        assert "example.com" in dc.domains

    def test_refine(self, git_repo):
        dc = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(git_repo)
            dc.collect(git_repo)
        finally:
            os.chdir(prevdir)
        dc.refine()

        # Authors should have refined data
        for author in dc.get_authors():
            info = dc.get_author_info(author)
            assert "place_by_commits" in info
            assert "commits_frac" in info
            assert "date_first" in info
            assert "date_last" in info
            assert "timedelta" in info

    def test_new_contributors(self, git_repo):
        dc = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(git_repo)
            dc.collect(git_repo)
        finally:
            os.chdir(prevdir)
        dc.refine()

        # Should have new contributors recorded per month
        assert dc.new_contributors_by_month

    def test_collect_preserves_commits_by_timezone(self, git_repo):
        dc = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(git_repo)
            dc.collect(git_repo)
        finally:
            os.chdir(prevdir)

        assert dc.commits_by_timezone

    def test_collect_author_of_month(self, git_repo):
        dc = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(git_repo)
            dc.collect(git_repo)
        finally:
            os.chdir(prevdir)

        assert dc.author_of_month
        assert dc.commits_by_month

    def test_collect_author_of_year(self, git_repo):
        dc = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(git_repo)
            dc.collect(git_repo)
        finally:
            os.chdir(prevdir)

        assert dc.author_of_year
        assert dc.commits_by_year

    def test_cache_roundtrip(self, git_repo, temp_dir):
        """Collect, save cache, collect again with cache."""
        dc1 = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(git_repo)
            dc1.collect(git_repo)
        finally:
            os.chdir(prevdir)

        cachefile = os.path.join(temp_dir, "gitstats.cache")
        dc1.save_cache(cachefile)

        # Second run with cache loaded
        dc2 = GitDataCollector()
        dc2.load_cache(cachefile)
        try:
            os.chdir(git_repo)
            dc2.collect(git_repo)
        finally:
            os.chdir(prevdir)

        # Should get same results
        assert dc2.total_commits == dc1.total_commits

    def test_collect_with_exclude_exts(self, git_repo):
        """With py excluded, .py files should not appear in extensions."""
        import gitstats
        import gitstats.main
        import gitstats.utils

        cfg = dict(gitstats.DEFAULT_CONFIG, exclude_exts="py")
        gitstats._config = cfg
        gitstats.main.conf = cfg
        gitstats.utils.conf = cfg

        dc = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(git_repo)
            dc.collect(git_repo)
        finally:
            os.chdir(prevdir)

        assert "py" not in dc.extensions

    def test_collect_merge_aliases(self, git_repo):
        """Authors sharing the same email should be merged."""
        dc = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(git_repo)
            dc.collect(git_repo)
        finally:
            os.chdir(prevdir)

        # Alice Smith always uses alice@example.com
        # Should be exactly one entry for Alice
        assert "Alice Smith" in dc.authors
        assert dc.authors["Alice Smith"]["commits"] > 0


# ── collect() phases (unit-testable without a repository) ────────────────


class TestCollectPhases:
    """Each collection phase is exercised on its own, no git required."""

    def test_record_activity_accumulates_histograms(self):
        dc = GitDataCollector()
        # Wed 2024-05-08 14:xx  (weekday 2), plus a second commit the same hour
        d1 = datetime.datetime(2024, 5, 8, 14, 30)
        d2 = datetime.datetime(2024, 5, 8, 14, 45)
        d3 = datetime.datetime(2024, 5, 9, 9, 0)  # Thu, different hour

        for d in (d1, d2, d3):
            dc._record_activity(d)

        assert dc.activity_by_hour_of_day == {14: 2, 9: 1}
        assert dc.activity_by_day_of_week == {2: 2, 3: 1}
        assert dc.activity_by_hour_of_week[2][14] == 2
        assert dc.activity_by_month_of_year == {5: 3}
        assert dc.activity_by_hour_of_day_busiest == 2
        assert dc.activity_by_hour_of_week_busiest == 2
        # all three fall in the same calendar week
        assert dc.activity_by_year_week == {d1.strftime("%Y-%W"): 3}
        assert dc.activity_by_year_week_peak == 3

    def test_record_activity_keeps_the_hour_of_week_grid_for_each_year(self):
        dc = GitDataCollector()
        for date in (
            datetime.datetime(2024, 5, 8, 14, 30),  # Wed
            datetime.datetime(2024, 5, 8, 14, 45),
            datetime.datetime(2024, 5, 9, 9, 0),  # Thu
            datetime.datetime(2025, 1, 1, 23, 10),  # Wed, the next year
        ):
            dc._record_activity(date)

        assert dc.activity_by_hour_of_week_by_year == {
            2024: {2: {14: 2}, 3: {9: 1}},
            2025: {2: {23: 1}},
        }
        # the all-time grid still counts every year together
        assert dc.activity_by_hour_of_week == {2: {14: 2, 23: 1}, 3: {9: 1}}

    def test_record_activity_takes_hour_and_weekday_from_the_commits_own_clock(self):
        dc = GitDataCollector()
        # one moment: Tue 2024-12-31 20:30 on this machine, Wed 2025-01-01 05:30
        # where the commit was made
        here = datetime.datetime(2024, 12, 31, 20, 30)
        there = datetime.datetime(2025, 1, 1, 5, 30)
        dc._record_activity(here, there)

        # the hour and the day of the week are the committer's
        assert dc.activity_by_hour_of_day == {5: 1}
        assert dc.activity_by_day_of_week == {2: 1}
        assert dc.activity_by_hour_of_week == {2: {5: 1}}
        # the month, week and year it is counted in are this machine's
        assert dc.activity_by_month_of_year == {12: 1}
        assert dc.activity_by_year_week == {here.strftime("%Y-%W"): 1}
        assert dc.activity_by_hour_of_week_by_year == {2024: {2: {5: 1}}}

    def test_record_author_commit_tracks_span_and_active_days(self):
        dc = GitDataCollector()
        early = datetime.datetime(2024, 1, 10, 9, 0)
        late = datetime.datetime(2024, 3, 20, 9, 0)

        # deliberately out of order: stamps may arrive in any order
        dc._record_author_commit("Ann", int(late.timestamp()), late)
        dc._record_author_commit("Ann", int(early.timestamp()), early)
        dc._record_author_commit("Bo", int(late.timestamp()), late)

        ann = dc.authors["Ann"]
        assert ann["first_commit_stamp"] == int(early.timestamp())
        assert ann["last_commit_stamp"] == int(late.timestamp())
        assert ann["active_days"] == {"2024-01-10", "2024-03-20"}
        assert dc.commits_by_month == {"2024-03": 2, "2024-01": 1}
        assert dc.commits_by_year == {2024: 3}
        assert dc.author_of_month["2024-03"] == {"Ann": 1, "Bo": 1}
        assert dc.active_days == {"2024-01-10", "2024-03-20"}

    def test_merge_author_aliases_folds_shared_email(self):
        """Two names on one email collapse into the most recent name."""
        dc = GitDataCollector()
        dc.authors = {
            "old name": {
                "commits": 2,
                "lines_added": 10,
                "lines_removed": 1,
                "first_commit_stamp": 100,
                "last_commit_stamp": 200,
                "active_days": {"2024-01-01"},
                "last_active_day": "2024-01-01",
            },
            "New Name": {
                "commits": 3,
                "lines_added": 5,
                "lines_removed": 2,
                "first_commit_stamp": 300,
                "last_commit_stamp": 400,
                "active_days": {"2024-02-02"},
                "last_active_day": "2024-02-02",
            },
        }
        dc.author_of_month = {"2024-01": {"old name": 2}, "2024-02": {"New Name": 3}}
        dc.author_of_year = {2024: {"old name": 2, "New Name": 3}}
        dc.tags = {"v1": {"authors": {"old name": 2, "New Name": 1}}}

        # both names share one email; the later stamp wins the canonical name
        mapping = dc._merge_author_aliases(
            {("old name", "a@x.com"): 200, ("New Name", "a@x.com"): 400}
        )

        assert mapping == {"old name": "New Name"}
        assert set(dc.authors) == {"New Name"}
        merged = dc.authors["New Name"]
        assert merged["commits"] == 5
        assert merged["lines_added"] == 15
        assert merged["first_commit_stamp"] == 100  # earliest wins
        assert merged["last_commit_stamp"] == 400  # latest wins
        assert merged["active_days"] == {"2024-01-01", "2024-02-02"}
        # period and tag dicts are re-keyed onto the canonical name
        assert dc.author_of_month["2024-01"] == {"New Name": 2}
        assert dc.author_of_year[2024] == {"New Name": 5}
        assert dc.tags["v1"]["authors"] == {"New Name": 3}
        assert dc.total_authors == 1

    def test_merge_author_aliases_noop_for_distinct_emails(self):
        dc = GitDataCollector()
        dc.authors = {"Ann": {"commits": 1}, "Bo": {"commits": 1}}

        mapping = dc._merge_author_aliases({("Ann", "a@x.com"): 1, ("Bo", "b@x.com"): 2})

        assert mapping == {}
        assert set(dc.authors) == {"Ann", "Bo"}
        assert dc.total_authors == 2

    def test_collect_calls_every_phase(self, git_repo):
        """collect() is an orchestrator: each phase runs exactly once."""
        dc = GitDataCollector()
        called = []

        def spy(name, result=None):
            def _f(*args, **kwargs):
                called.append(name)
                return result

            return _f

        dc._collect_tags = spy("tags")
        dc._collect_commit_stats = spy("commits", {})
        dc._merge_author_aliases = spy("aliases", {})
        dc._collect_files_by_stamp = spy("files")
        dc._collect_extensions = spy("extensions")
        dc._collect_line_stats = spy("lines")
        dc._collect_per_author_line_stats = spy("author_lines")
        dc._collect_file_churn_and_ownership = spy("churn")
        dc._collect_ai_assisted = spy("assisted")

        prevdir = os.getcwd()
        try:
            os.chdir(git_repo)
            dc.collect(git_repo)
        finally:
            os.chdir(prevdir)

        assert called == [
            "tags",
            "commits",
            "aliases",
            "extensions",
            "files",
            "lines",
            "author_lines",
            "churn",
            "assisted",
        ]

    @staticmethod
    def _collect_recording(git_repo, processes, cpus=8, shortstat_logs=None):
        """Run collect() on a machine of ``cpus`` processors; return the data,
        the git commands that ran through get_pipe_output() and what each of
        the phases that read the whole history was handed."""
        import gitstats.main as main_mod

        _use_config(processes=processes)
        real = main_mod.get_pipe_output
        ran = []

        def recording(cmds, quiet=False):
            ran.append(cmds[0])
            return real(cmds, quiet)

        dc = GitDataCollector()
        handed = {}
        for phase, position in (
            ("_collect_line_stats", 0),
            ("_collect_per_author_line_stats", 1),
            ("_collect_file_churn_and_ownership", 1),
            ("_collect_ai_assisted", 0),
        ):

            def spy(*args, _phase=phase, _position=position, _original=getattr(dc, phase)):
                handed[_phase] = args[_position]
                return _original(*args)

            setattr(dc, phase, spy)
        prevdir = os.getcwd()
        with (
            patch.object(main_mod, "get_pipe_output", recording),
            patch.object(main_mod.os, "cpu_count", return_value=cpus),
            patch.object(
                main_mod, "shortstat_logs", side_effect=shortstat_logs or main_mod.shortstat_logs
            ) as spread,
        ):
            try:
                os.chdir(git_repo)
                dc.collect(git_repo)
            finally:
                os.chdir(prevdir)
        data = {
            key: value
            for key, value in dc.__dict__.items()
            if key not in ("stamp_created", "cache") and not key.startswith("_collect")
        }
        return data, ran, handed, dc, spread

    @staticmethod
    def _text(output):
        """The lines of a `git log`, blank ones aside."""
        return [line for line in output.split("\n") if line]

    def test_collect_starts_the_history_passes_ahead(self, git_repo, monkeypatch):
        """collect() has git start on the three passes itself: the diffs of
        every commit, made once and spread over git processes, give the line
        counts of two phases and the file names of the third. None of the
        three commands runs, and each phase is handed the text of its own."""
        _, ran, handed, dc, spread = self._collect_recording(git_repo, processes=8)

        # eight processes: seven for the diffs, one left to the phases
        spread.assert_called_once()
        passes, log_range, workers, waiting, names, source, source_lines = spread.call_args.args
        assert (passes, log_range, workers, names) == (
            [("--first-parent", True), ("--date-order", False)],
            "HEAD",
            7,
            "COMMIT:%aN",
        )
        # the same diffs count the lines of the source, file by file
        from gitstats.sources import is_source

        assert source is is_source
        assert source_lines == [dc.source_lines_added]
        assert dc._source_lines_command() not in ran
        # and the phases said so when they had nothing left to do but wait
        assert waiting.is_set()
        assert dc._line_stats_command() not in ran
        assert dc._author_line_stats_command() not in ran
        assert dc._churn_command() not in ran

        # what the phases were handed is what their commands print
        from gitstats.utils import get_pipe_output

        monkeypatch.chdir(git_repo)
        for phase, command in (
            ("_collect_line_stats", dc._line_stats_command()),
            ("_collect_per_author_line_stats", dc._author_line_stats_command()),
            ("_collect_file_churn_and_ownership", dc._churn_command()),
        ):
            assert self._text(handed[phase]) == self._text(get_pipe_output([command])), phase
        assert "files changed" in handed["_collect_line_stats"]
        assert handed["_collect_file_churn_and_ownership"].startswith("COMMIT:")
        assert "\nutils.py\n" in handed["_collect_file_churn_and_ownership"]
        # the messages were read beside the rest: no commit of this history names an assistant
        assert handed["_collect_ai_assisted"] == []

    @pytest.mark.parametrize("processes, cpus, workers", [(8, 4, 3), (3, 16, 2), (2, 2, 1)])
    def test_collect_asks_for_no_more_processes_than_the_machine_has(
        self, git_repo, processes, cpus, workers
    ):
        _, _, _, _, spread = self._collect_recording(git_repo, processes, cpus)
        assert spread.call_args.args[2] == workers

    @pytest.mark.parametrize("processes, cpus", [(1, 8), (8, 1)])
    def test_collect_gathers_the_same_with_one_process(self, git_repo, processes, cpus):
        """`processes = 1`, or a machine with one processor, leaves each phase
        to run its own command, in its turn; the data does not change."""
        side_by_side, _, _, _, _ = self._collect_recording(git_repo, processes=8)
        in_turn, ran, handed, dc, spread = self._collect_recording(git_repo, processes, cpus)

        spread.assert_not_called()
        assert handed == {
            "_collect_line_stats": None,
            "_collect_per_author_line_stats": None,
            "_collect_file_churn_and_ownership": None,
            "_collect_ai_assisted": None,
        }
        assert side_by_side == in_turn
        # in turn, the passes are the last commands, in the order of their phases;
        # the lines of the source last, by a walk of their own
        assert ran[-4:] == [
            dc._line_stats_command(),
            dc._author_line_stats_command(),
            dc._churn_command(),
            dc._source_lines_command(),
        ]

    def test_collect_runs_the_commands_when_the_counts_cannot_be_spread(self, git_repo):
        """git failing in one of the processes is not the end of the run: the
        three phases run their commands, as they would in turn."""
        side_by_side, _, _, _, _ = self._collect_recording(git_repo, processes=8)

        def failing(passes, log_range, workers, waiting, names, source, source_lines):
            raise subprocess.CalledProcessError(128, ["git", "log"])

        fallen_back, ran, handed, dc, _ = self._collect_recording(
            git_repo, processes=8, shortstat_logs=failing
        )
        assert handed == {
            "_collect_line_stats": None,
            "_collect_per_author_line_stats": None,
            "_collect_file_churn_and_ownership": None,
            # read by one `git log` of its own, which did not fail
            "_collect_ai_assisted": [],
        }
        assert ran.count(dc._line_stats_command()) == 1
        assert ran.count(dc._author_line_stats_command()) == 1
        assert ran.count(dc._churn_command()) == 1
        assert ran.count(dc._source_lines_command()) == 1
        assert fallen_back == side_by_side

    # ── commits that name an AI coding assistant ────────────────────────

    @staticmethod
    def _commit_as(repo, name, email, date, *paragraphs):
        subprocess.run(
            [
                "git", "commit", "-q", "--allow-empty",
                *(arg for paragraph in paragraphs for arg in ("-m", paragraph)),
            ],
            cwd=repo,
            check=True,
            capture_output=True,
            env={
                **os.environ,
                "LC_ALL": "C",
                "GIT_AUTHOR_NAME": name,
                "GIT_AUTHOR_EMAIL": email,
                "GIT_COMMITTER_NAME": name,
                "GIT_COMMITTER_EMAIL": email,
                "GIT_AUTHOR_DATE": date,
                "GIT_COMMITTER_DATE": date,
            },
        )  # fmt: skip

    def test_ai_assisted_commits_by_month_and_by_assistant(self):
        from gitstats.assistants import AssistedCommit

        def stamp(month, day):
            return int(datetime.datetime(2025, month, day, 12).timestamp())

        dc = GitDataCollector()
        dc._collect_ai_assisted(
            [
                AssistedCommit(stamp(6, 10), ["GitHub Copilot"], False),
                # an assistant made it, and names another: counted under both, once in all
                AssistedCommit(stamp(3, 20), ["GitHub Copilot", "Claude"], True),
                AssistedCommit(stamp(3, 10), ["Claude"], False),
            ]
        )
        assert dc.ai_assisted_commits == 3
        assert dc.ai_assisted_authored == 1
        assert dc.ai_assisted_by_month == {"2025-06": 1, "2025-03": 2}
        assert dc.ai_assistants == {
            "GitHub Copilot": {
                "commits": 2,
                "authored": 1,
                "first_commit_stamp": stamp(3, 20),
                "last_commit_stamp": stamp(6, 10),
            },
            "Claude": {
                "commits": 2,
                # named by the commit Copilot made, which is Copilot's
                "authored": 0,
                "first_commit_stamp": stamp(3, 10),
                "last_commit_stamp": stamp(3, 20),
            },
        }

    @pytest.mark.parametrize("processes", [8, 1])
    def test_collect_counts_the_commits_that_name_an_assistant(self, git_repo, processes):
        self._commit_as(
            git_repo, "Alice Smith", "alice@example.com", "2023-06-01T10:00:00",
            "Parse the header",
            "Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>",
        )  # fmt: skip
        self._commit_as(
            git_repo, "copilot-swe-agent[bot]", "198982749+Copilot@users.noreply.github.com",
            "2023-07-01T10:00:00", "Initial plan",
        )  # fmt: skip
        import gitstats.assistants as assistants

        with patch.object(
            assistants, "get_pipe_output", side_effect=assistants.get_pipe_output
        ) as read:
            data, _, _, dc, _ = self._collect_recording(git_repo, processes)

        assert data["ai_assisted_commits"] == 2
        assert data["ai_assisted_authored"] == 1
        assert data["ai_assisted_by_month"] == {"2023-07": 1, "2023-06": 1}
        assert {name: info["commits"] for name, info in data["ai_assistants"].items()} == {
            "GitHub Copilot": 1,
            "Claude": 1,
        }
        # one reading of the messages, whether ahead of the phases or in its turn
        read.assert_called_once()
        assert "%B" in read.call_args.args[0][0]
        assert dc.get_total_commits() == 7

    def test_collect_of_a_history_that_names_no_assistant(self, git_repo):
        data, _, _, _, _ = self._collect_recording(git_repo, processes=8)
        assert data["ai_assisted_commits"] == 0
        assert data["ai_assisted_authored"] == 0
        assert data["ai_assisted_by_month"] == {}
        assert data["ai_assistants"] == {}

    def test_line_stat_passes_follow_linear_linestats(self):
        assert GitDataCollector._line_stat_passes() == [
            ("--first-parent", True),
            ("--date-order", False),
        ]
        assert GitDataCollector._line_stats_command() == (
            'git log --root --shortstat --first-parent -m --pretty=format:"%at %aN" HEAD'
        )
        assert GitDataCollector._author_line_stats_command() == (
            'git log --root --shortstat --date-order --pretty=format:"%at %aN" HEAD'
        )
        _use_config(linear_linestats=0)
        # every commit, and a merge is not compared with anything
        assert GitDataCollector._line_stat_passes() == [("", False), ("--date-order", False)]
        assert GitDataCollector._line_stats_command() == (
            'git log --root --shortstat  --pretty=format:"%at %aN" HEAD'
        )


# ── commit subject sampling (grounds the AI chronicle) ──────────────────


def test_sample_evenly():
    from gitstats.main import _sample_evenly

    assert _sample_evenly([], 10) == []
    assert _sample_evenly(["a", "b"], 10) == ["a", "b"]
    sampled = _sample_evenly([str(i) for i in range(100)], 10)
    assert len(sampled) == 10
    assert sampled[0] == "0"
    # evenly spread and order preserved
    assert sampled == sorted(sampled, key=int)
    assert int(sampled[-1]) >= 90


class TestCommitSubjects:
    def test_collected_when_ai_enabled(self, git_repo):
        import gitstats.main as main_mod

        dc = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(git_repo)
            with patch.dict(main_mod.conf, {"ai_enabled": True}):
                dc.collect(git_repo)
        finally:
            os.chdir(prevdir)

        subjects = dc.commit_subjects_by_year
        assert set(subjects) == {2023}
        assert "Initial commit" in subjects[2023]
        assert len(subjects[2023]) <= 10

    def test_skipped_when_ai_disabled(self, git_repo):
        dc = GitDataCollector()
        prevdir = os.getcwd()
        try:
            os.chdir(git_repo)
            dc.collect(git_repo)
        finally:
            os.chdir(prevdir)

        assert dc.commit_subjects_by_year == {}


# ── run() integration ────────────────────────────────────────────────────


class TestRunIntegration:
    """End-to-end tests for the run() function."""

    def test_run_basic(self, git_repo, temp_dir):
        """run() should produce HTML report files."""
        import gitstats
        import gitstats.main

        cfg = dict(gitstats.DEFAULT_CONFIG, ai_enabled=False)
        gitstats._config = cfg
        gitstats.main.conf = cfg
        gitstats.utils.conf = cfg
        gitstats.report_creator.conf = cfg

        output = os.path.join(temp_dir, "report")
        ret = run([git_repo], output)

        assert ret == 0
        assert os.path.isdir(output)
        for page in ("index", "activity", "authors", "files", "lines", "tags"):
            assert os.path.exists(f"{output}/{page}.html")
        # Single-repo mode keeps the flat layout and adds a summary.json
        assert os.path.exists(f"{output}/summary.json")
        assert not any(
            e.is_dir() for e in os.scandir(output) if e.name not in (".ai_cache", "badges")
        )

    def test_run_with_json(self, git_repo, temp_dir):
        """run() with extra_fmt='json' should produce a JSON file."""
        import gitstats
        import gitstats.main

        cfg = dict(gitstats.DEFAULT_CONFIG, ai_enabled=False)
        gitstats._config = cfg
        gitstats.main.conf = cfg
        gitstats.utils.conf = cfg
        gitstats.report_creator.conf = cfg

        output = os.path.join(temp_dir, "report")
        ret = run([git_repo], output, extra_fmt="json")

        assert ret == 0
        # JSON file: os.path.join(gitpath, f"{outputpath}.json") where outputpath is absolute,
        # so the join collapses to just f"{outputpath}.json"
        json_path = f"{output}.json"
        assert os.path.exists(json_path), f"Expected {json_path} to exist"

    def test_run_multi_repo_aggregate(self, git_repo, git_repo_minimal, temp_dir):
        """run() with multiple repos writes per-repo reports and a portfolio page."""
        import json

        import gitstats
        import gitstats.main

        cfg = dict(gitstats.DEFAULT_CONFIG, ai_enabled=False)
        gitstats._config = cfg
        gitstats.main.conf = cfg
        gitstats.utils.conf = cfg
        gitstats.report_creator.conf = cfg

        output = os.path.join(temp_dir, "report")
        ret = run([git_repo, git_repo_minimal], output)

        assert ret == 0
        # Each repository gets a full report in its own subdirectory
        for slug in ("git_repo", "git_repo_minimal"):
            for page in ("index", "activity", "authors", "files", "lines", "tags"):
                assert os.path.exists(f"{output}/{slug}/{page}.html")
            with open(f"{output}/{slug}/summary.json", encoding="utf-8") as f:
                summary = json.load(f)
            assert summary["schema_version"] == 1
            assert summary["name"] == slug
            assert summary["report_path"] == f"{slug}/index.html"
            assert summary["total_commits"] > 0

        # Aggregate portfolio page at the output root links both repos
        with open(f"{output}/index.html", encoding="utf-8") as f:
            index = f.read()
        assert 'href="git_repo/index.html"' in index
        assert 'href="git_repo_minimal/index.html"' in index
        assert '<dl class="stat-tiles"' in index
        # Per-repo pages must not leak into the output root
        assert not os.path.exists(f"{output}/activity.html")

    def test_multi_repo_portfolio_knows_its_address(self, git_repo, git_repo_minimal, temp_dir):
        from gitstats.main import _run_multi_repo

        output = os.path.join(temp_dir, "portfolio")
        with patch("gitstats.main.AggregateReportCreator") as creator:
            _run_multi_repo([git_repo, git_repo_minimal], output, site_url="https://example.com/p/")
        creator.return_value.create.assert_called_once()
        assert creator.return_value.create.call_args.kwargs["site_url"] == "https://example.com/p/"

    def test_run_with_site_url(self, git_repo, temp_dir, caplog):
        """site_url fills in the Badges page and prints the README badge."""
        import json
        import logging

        import gitstats.main

        gitstats.main.conf["site_url"] = "https://reports.example.com/repo"
        output = os.path.join(temp_dir, "report")
        with caplog.at_level(logging.INFO, logger="gitstats"):
            assert run([git_repo], output) == 0

        with open(f"{output}/badges.html", encoding="utf-8") as f:
            page = f.read()
        data = re.search(r'<script type="application/json" id="badge-data">(.*?)</script>', page)
        assert json.loads(data[1])["siteUrl"] == "https://reports.example.com/repo/"
        assert 'value="https://reports.example.com/repo/"' in page
        assert (
            "[![GitStats summary](https://reports.example.com/repo/badges/flat/summary.svg)]"
            "(https://reports.example.com/repo/)" in page
        )
        assert (
            "README badge: [![GitStats](https://reports.example.com/repo/badge.svg)]"
            "(https://reports.example.com/repo/)" in caplog.text
        )

    def test_run_multi_repo_site_url(self, git_repo, git_repo_minimal, temp_dir):
        """Each repository's Badges page points at its own subdirectory."""
        import gitstats.main

        gitstats.main.conf["site_url"] = "https://reports.example.com/"
        output = os.path.join(temp_dir, "report")
        assert run([git_repo, git_repo_minimal], output) == 0
        with open(f"{output}/git_repo_minimal/badges.html", encoding="utf-8") as f:
            assert '"siteUrl": "https://reports.example.com/git_repo_minimal/"' in f.read()

    def test_run_rejects_bad_site_url(self, git_repo, temp_dir, caplog):
        import gitstats.main

        gitstats.main.conf["site_url"] = "reports.example.com/repo"
        assert run([git_repo], os.path.join(temp_dir, "report")) == 1
        assert "site_url must be an http(s) address" in caplog.text

    def test_run_missing_repository_path(self, temp_dir, caplog):
        """A git path that does not exist is a FATAL error, not a traceback."""
        import gitstats
        import gitstats.main

        cfg = dict(gitstats.DEFAULT_CONFIG, ai_enabled=False)
        gitstats._config = cfg
        gitstats.main.conf = cfg

        missing = os.path.join(temp_dir, "missing")
        output = os.path.join(temp_dir, "report")
        ret = run([missing], output)

        assert ret == 1
        assert "Git path is not a directory" in caplog.text

    def test_run_multi_repo_tolerates_failure(self, git_repo, temp_dir):
        """One broken repo is reported on the portfolio page, not fatal."""
        import gitstats
        import gitstats.main

        cfg = dict(gitstats.DEFAULT_CONFIG, ai_enabled=False)
        gitstats._config = cfg
        gitstats.main.conf = cfg
        gitstats.utils.conf = cfg
        gitstats.report_creator.conf = cfg

        not_a_repo = os.path.join(temp_dir, "not_a_repo")
        os.makedirs(not_a_repo)
        output = os.path.join(temp_dir, "report")
        ret = run([git_repo, not_a_repo], output)

        assert ret == 0
        assert os.path.exists(f"{output}/git_repo/index.html")
        with open(f"{output}/index.html", encoding="utf-8") as f:
            index = f.read()
        assert "Failed repositories" in index
        assert "not_a_repo" in index

    def test_run_multi_repo_all_failed(self, temp_dir):
        """run() returns 1 when no repository could be analyzed."""
        import gitstats
        import gitstats.main

        cfg = dict(gitstats.DEFAULT_CONFIG, ai_enabled=False)
        gitstats._config = cfg
        gitstats.main.conf = cfg
        gitstats.utils.conf = cfg
        gitstats.report_creator.conf = cfg

        bad_one = os.path.join(temp_dir, "bad_one")
        bad_two = os.path.join(temp_dir, "bad_two")
        os.makedirs(bad_one)
        os.makedirs(bad_two)
        output = os.path.join(temp_dir, "report")
        ret = run([bad_one, bad_two], output)

        assert ret == 1


# ── get_parser / CLI ─────────────────────────────────────────────────────


class TestCLI:
    def test_parser_defaults(self):
        parser = get_parser()
        args = parser.parse_args(["some-repo", "out-dir"])
        # With nargs='+' + nargs='?', argparse greedily consumes all
        # positional args into gitpath. Resolution happens in main().
        assert args.gitpath == ["some-repo", "out-dir"]
        assert args.outputpath is None
        assert args.format is None
        assert args.verbose is False
        assert args.quiet is False
        assert args.ai is None
        assert args.refresh_ai is False
        assert args.serve is False
        assert args.host == "127.0.0.1"
        assert args.port == 8000

    def test_parser_serve_flags(self):
        parser = get_parser()
        args = parser.parse_args(["--serve", "--host", "0.0.0.0", "--port", "0", "repo"])
        assert args.serve is True
        assert args.host == "0.0.0.0"
        assert args.port == 0

    def test_parser_single_path(self):
        parser = get_parser()
        args = parser.parse_args(["some-repo"])
        assert args.gitpath == ["some-repo"]
        assert args.outputpath is None

    def test_parser_site_url(self):
        parser = get_parser()
        assert parser.parse_args(["repo"]).site_url is None
        args = parser.parse_args(["--site-url", "https://example.com/r/", "repo"])
        assert args.site_url == "https://example.com/r/"

    def test_parser_wrapped_flags(self, capsys):
        parser = get_parser()
        args = parser.parse_args(["repo"])
        assert args.wrapped is False
        assert args.wrapped_year is None
        assert args.wrapped_theme == "midnight"
        assert args.wrapped_output is None

        args = parser.parse_args(
            ["--wrapped", "--wrapped-year", "2025", "--wrapped-theme", "sunset"]
            + ["--wrapped-output", "card.svg", "repo"]
        )
        assert args.wrapped is True
        assert args.wrapped_year == 2025
        assert args.wrapped_theme == "sunset"
        assert args.wrapped_output == "card.svg"

        with pytest.raises(SystemExit):
            parser.parse_args(["--wrapped", "--wrapped-theme", "neon", "repo"])
        assert "invalid choice: 'neon'" in capsys.readouterr().err

    def test_normalize_site_url(self):
        assert normalize_site_url("") == ""
        assert normalize_site_url("  ") == ""
        assert normalize_site_url("https://example.com/r") == "https://example.com/r/"
        assert normalize_site_url("http://host:8000/a/b//") == "http://host:8000/a/b/"
        for bad in ("example.com/r", "ftp://example.com/", "https://example.com/?x=1", "https://"):
            with pytest.raises(ValueError):
                normalize_site_url(bad)

    def test_parser_format(self):
        parser = get_parser()
        args = parser.parse_args(["-f", "json", "repo", "out"])
        assert args.format == "json"

    def test_parser_ai_flags(self):
        parser = get_parser()
        args = parser.parse_args(["--ai", "--refresh-ai", "repo", "out"])
        assert args.ai is True
        assert args.refresh_ai is True

    def test_parser_no_ai(self):
        parser = get_parser()
        args = parser.parse_args(["--no-ai", "repo", "out"])
        assert args.ai is False

    def test_parser_ai_provider_model(self):
        parser = get_parser()
        args = parser.parse_args(
            [
                "--ai-provider",
                "ollama",
                "--ai-model",
                "llama3",
                "--ai-language",
                "zh",
                "repo",
                "out",
            ]
        )
        assert args.ai_provider == "ollama"
        assert args.ai_model == "llama3"
        assert args.ai_language == "zh"

    def test_parser_config_override(self):
        parser = get_parser()
        args = parser.parse_args(
            [
                "-c",
                "max_authors=5",
                "-c",
                "processes=2",
                "repo",
                "out",
            ]
        )
        assert args.config == ["max_authors=5", "processes=2"]

    def test_parser_verbose(self):
        parser = get_parser()
        args = parser.parse_args(["--verbose", "repo", "out"])
        assert args.verbose is True
        assert args.quiet is False

    def test_parser_quiet(self):
        parser = get_parser()
        args = parser.parse_args(["--quiet", "repo", "out"])
        assert args.quiet is True
        assert args.verbose is False

    def test_parser_verbose_quiet_are_mutually_exclusive(self):
        parser = get_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--verbose", "--quiet", "repo", "out"])

    def test_parser_version(self, capsys):
        parser = get_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["-v"])


# ── main() ───────────────────────────────────────────────────────────────


def test_main_basic(git_repo_minimal, temp_dir):
    """Test main() with minimal args."""
    import gitstats
    import gitstats.main

    cfg = dict(gitstats.DEFAULT_CONFIG, ai_enabled=False)
    gitstats._config = cfg
    gitstats.main.conf = cfg

    import sys

    output = os.path.join(temp_dir, "report")

    with patch.object(sys, "argv", ["gitstats", git_repo_minimal, output]):
        ret = main()
    assert ret == 0


def test_main_default_outputpath(git_repo_minimal, temp_dir):
    """Test main() without explicit outputpath (uses default gitstats-report)."""
    import gitstats
    import gitstats.main

    cfg = dict(gitstats.DEFAULT_CONFIG, ai_enabled=False)
    gitstats._config = cfg
    gitstats.main.conf = cfg

    import sys

    with patch.object(sys, "argv", ["gitstats", git_repo_minimal]):
        ret = main()
    assert ret == 0
    # Default output dir should have been created
    assert os.path.isdir("gitstats-report")


@pytest.mark.skipif(
    sys.version_info < (3, 12),
    reason="argparse before 3.12 rejects a positional that follows an option",
)
def test_main_outputpath_after_an_option(git_repo_minimal, temp_dir):
    """`gitstats repo -f json out`: argparse itself hands the last path to
    outputpath, so main() has nothing to move out of gitpath."""
    import gitstats
    import gitstats.main

    cfg = dict(gitstats.DEFAULT_CONFIG, ai_enabled=False)
    gitstats._config = cfg
    gitstats.main.conf = cfg

    output = os.path.join(temp_dir, "report")

    with patch.object(sys, "argv", ["gitstats", git_repo_minimal, "-f", "json", output]):
        ret = main()
    assert ret == 0
    assert os.path.isfile(os.path.join(output, "index.html"))
    assert os.path.isfile(f"{output}.json")  # the JSON goes next to the report


def test_main_keeps_an_outputpath_argparse_filled(git_repo_minimal, temp_dir, monkeypatch):
    """Same contract on every Python: when the parser already filled outputpath,
    main() leaves gitpath alone instead of moving its last entry."""
    import gitstats
    import gitstats.main

    cfg = dict(gitstats.DEFAULT_CONFIG, ai_enabled=False)
    gitstats._config = cfg
    gitstats.main.conf = cfg

    output = os.path.join(temp_dir, "report")
    args = gitstats.main.get_parser().parse_args([git_repo_minimal, "-f", "json"])
    args.outputpath = output
    monkeypatch.setattr(
        gitstats.main, "get_parser", lambda: SimpleNamespace(parse_args=lambda: args)
    )

    ret = main()
    assert ret == 0
    assert args.gitpath == [git_repo_minimal]
    assert os.path.isfile(os.path.join(output, "index.html"))
    assert os.path.isfile(f"{output}.json")


def test_main_with_config_override(git_repo_minimal, temp_dir):
    """Test main() with -c overrides."""
    import gitstats
    import gitstats.main

    cfg = dict(gitstats.DEFAULT_CONFIG, ai_enabled=False)
    gitstats._config = cfg
    gitstats.main.conf = cfg

    import sys

    output = os.path.join(temp_dir, "report")

    with patch.object(sys, "argv", ["gitstats", "-c", "max_authors=10", git_repo_minimal, output]):
        ret = main()
    assert ret == 0
    # After run, main.conf should have the override
    assert gitstats.main.conf["max_authors"] == 10


def test_main_with_negative_config_override(git_repo_minimal, temp_dir):
    """-c max_tags_authors=-1 (no limit) must reach the report as an integer."""
    import gitstats
    import gitstats.main
    import gitstats.report_creator

    cfg = dict(gitstats.DEFAULT_CONFIG, ai_enabled=False)
    gitstats._config = cfg
    gitstats.main.conf = cfg
    gitstats.report_creator.conf = cfg

    import sys

    output = os.path.join(temp_dir, "report")

    with patch.object(
        sys, "argv", ["gitstats", "-c", "max_tags_authors=-1", git_repo_minimal, output]
    ):
        ret = main()
    assert ret == 0
    assert gitstats.main.conf["max_tags_authors"] == -1


# ── --serve preview server ───────────────────────────────────────────────


class TestServe:
    def test_server_urls_loopback(self):
        local, network = _server_urls("127.0.0.1", 8000)
        assert local == "http://127.0.0.1:8000/"
        assert network is None

    def test_server_urls_all_interfaces(self):
        local, network = _server_urls("0.0.0.0", 8123)
        assert local == "http://127.0.0.1:8123/"
        assert network is not None
        assert network.startswith("http://")
        assert ":8123/" in network

    def test_server_urls_explicit_host(self):
        local, network = _server_urls("192.168.1.5", 8000)
        assert local == "http://192.168.1.5:8000/"
        assert network == "http://192.168.1.5:8000/"

    def test_serves_report_directory(self, temp_dir):
        import threading
        import urllib.request

        with open(os.path.join(temp_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write("<html><body>portfolio</body></html>")

        server = _make_server(temp_dir, "127.0.0.1", 0)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html") as resp:
                assert resp.status == 200
                assert b"portfolio" in resp.read()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


# ── helpers for the tests below ──────────────────────────────────────────


def _use_config(**overrides):
    """Install a config with ``overrides`` in every module that caches one."""
    import gitstats
    import gitstats.main
    import gitstats.report_creator
    import gitstats.utils

    cfg = dict(gitstats.DEFAULT_CONFIG, **overrides)
    gitstats._config = cfg
    gitstats.main.conf = cfg
    gitstats.utils.conf = cfg
    gitstats.report_creator.conf = cfg
    return cfg


@pytest.fixture
def sequential_map():
    """Do the per-revision and per-blob work in-process instead of in a pool."""
    with patch(
        "gitstats.main.parallel_map_with_fallback",
        side_effect=lambda func, items: [func(item) for item in items],
    ):
        yield


def _fake_git(outputs):
    """A get_pipe_output stand-in that answers by command prefix.

    Feeds the collector output that real git does not produce (bad stamps,
    stray lines) to check how each phase copes with it.
    """
    calls = []

    def fake(cmds, quiet=False):
        calls.append(cmds[0])
        for prefix, output in outputs.items():
            if cmds[0].startswith(prefix):
                return output
        raise AssertionError(f"unexpected command: {cmds[0]}")

    fake.calls = calls
    return fake


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


# ── logging and the worker pool ──────────────────────────────────────────


@pytest.mark.parametrize(
    "verbose,quiet,level",
    [(False, False, logging.INFO), (True, False, logging.DEBUG), (False, True, logging.WARNING)],
)
def test_configure_logging_levels(verbose, quiet, level):
    with patch("gitstats.main.logging.basicConfig") as basic_config:
        configure_logging(verbose=verbose, quiet=quiet)
    assert basic_config.call_args.kwargs["level"] == level
    assert basic_config.call_args.kwargs["stream"] is sys.stderr


def test_parallel_map_falls_back_to_sequential_without_a_pool(caplog):
    with (
        patch("gitstats.main.Pool", side_effect=OSError("no semaphores")),
        caplog.at_level(logging.WARNING, logger="gitstats"),
    ):
        assert parallel_map_with_fallback(_square, [1, 2, 3]) == [1, 4, 9]
    assert "falling back to sequential processing" in caplog.text


# ── collection phases on unusual input ───────────────────────────────────


class TestCollectEdgeCases:
    def test_tags_with_unreadable_dates_and_foreign_commits(self, monkeypatch):
        fake = _fake_git(
            {
                "git rev-list --topo-order": "c2\nc1",
                "git show-ref --tags --dereference": "c2 refs/tags/v2\nc1 refs/tags/v1\n",
                # the history that leads to the end of the range: c2 is not in
                # it, so its tag is left out; the stamp of c1 is unreadable,
                # and counted as 0
                "git log --topo-order": "c1\te1\tc0\tgarbage Ann\nc0\te0\t\t5 Outside Range",
            }
        )
        monkeypatch.setattr("gitstats.main.get_pipe_output", fake)
        monkeypatch.setattr("gitstats.utils.get_pipe_output", fake)
        dc = GitDataCollector()
        dc._collect_tags()

        assert set(dc.tags) == {"v1"}
        assert dc.tags["v1"]["stamp"] == 0
        # c0 is not in the analyzed range, so only c1 counts
        assert dc.tags["v1"]["commits"] == 1
        assert dc.tags["v1"]["authors"] == {"Ann": 1}
        # one command reads the history, whatever the number of tags
        assert fake.calls == [
            "git rev-list --topo-order HEAD",
            "git show-ref --tags --dereference",
            'git log --topo-order --format="%H%x09%T%x09%P%x09%at %aN" "HEAD"',
        ]

    def test_tags_outside_the_range_need_no_history(self, monkeypatch):
        fake = _fake_git(
            {
                "git rev-list --topo-order": "c2\nc1",
                "git show-ref --tags --dereference": "c9 refs/tags/elsewhere\n",
            }
        )
        monkeypatch.setattr("gitstats.main.get_pipe_output", fake)
        monkeypatch.setattr("gitstats.utils.get_pipe_output", fake)
        dc = GitDataCollector()
        dc._collect_tags()
        # no tag to date or to count for: the history is not read
        assert dc.tags == {}
        assert len(fake.calls) == 2

    def test_tags_are_counted_as_git_log_counts_them(self, temp_dir, monkeypatch):
        """On a history with tags on branches, on one commit and outside the
        history, each tag has the commits of `git log <tag> ^<the tag before>`."""
        repo = os.path.join(temp_dir, "tagged")
        os.makedirs(repo)
        _git(repo, "init", "-q", "-b", "main")
        _git(repo, "config", "user.name", "Merger")
        _git(repo, "config", "user.email", "merger@example.com")

        def commit(name, author, date):
            with open(os.path.join(repo, name), "w") as f:
                f.write(name)
            _git(repo, "add", "-A")
            env = {
                "GIT_AUTHOR_NAME": author,
                "GIT_AUTHOR_EMAIL": author.lower() + "@example.com",
                "GIT_COMMITTER_NAME": author,
                "GIT_COMMITTER_EMAIL": author.lower() + "@example.com",
                "GIT_AUTHOR_DATE": date,
                "GIT_COMMITTER_DATE": date,
            }
            subprocess.run(
                ["git", "commit", "-q", "-m", name],
                cwd=repo,
                check=True,
                capture_output=True,
                env={**os.environ, **env},
            )

        commit("a", "Ann", "2023-01-01T10:00:00")
        commit("b", "Ben", "2023-01-02T10:00:00")
        _git(repo, "tag", "v1.0")
        _git(repo, "tag", "-a", "-m", "the same commit", "first", "v1.0")
        _git(repo, "checkout", "-q", "-b", "fix")
        commit("c", "Cy", "2023-01-03T10:00:00")
        commit("d", "Ann", "2023-01-04T10:00:00")
        _git(repo, "tag", "v1.0.1")
        _git(repo, "checkout", "-q", "main")
        commit("e", "Ben", "2023-01-05T10:00:00")
        commit("f", "Ben", "2023-01-06T10:00:00")
        _git(repo, "tag", "v1.1-rc")
        _git(repo, "merge", "-q", "--no-ff", "-m", "merge fix", "fix")
        commit("g", "Di", "2023-01-07T10:00:00")
        _git(repo, "tag", "v1.1")
        commit("h", "Ann", "2023-01-08T10:00:00")
        # a tag the history of HEAD does not lead to
        _git(repo, "checkout", "-q", "-b", "elsewhere", "v1.0")
        commit("x", "Eve", "2023-01-09T10:00:00")
        _git(repo, "tag", "experiment")
        _git(repo, "checkout", "-q", "main")

        monkeypatch.chdir(repo)
        dc = GitDataCollector()
        dc._collect_tags()

        assert "experiment" not in dc.tags
        # what git says, a tag at a time, oldest first as the collector takes them
        from gitstats.utils import get_pipe_output

        in_range = set(get_pipe_output(["git rev-list HEAD"]).split())
        expected = {}
        prev = None
        for tag in sorted(dc.tags, key=lambda tag: (-dc.tags[tag]["order"], tag)):
            command = f'git log --format="%H %aN" "{tag}"' + (f' "^{prev}"' if prev else "")
            authors = {}
            for line in get_pipe_output([command]).split("\n"):
                if line and line.split(" ", 1)[0] in in_range:
                    author = line.split(" ", 1)[1]
                    authors[author] = authors.get(author, 0) + 1
            expected[tag] = authors
            if authors:
                prev = tag
        assert {tag: info["authors"] for tag, info in dc.tags.items()} == expected
        assert expected == {
            # the two first commits; the tag of the same commit that comes after has none
            "first": {"Ann": 1, "Ben": 1},
            "v1.0": {},
            # the main line since v1.0
            "v1.1-rc": {"Ben": 2},
            # the branch: the tag before it is v1.1-rc, which leads to neither c nor d
            "v1.0.1": {"Cy": 1, "Ann": 1},
            # the tag before it is v1.0.1, on the branch: e and f are counted
            # again, with the merge and g. A tag is compared with the one
            # before it, not with all of them.
            "v1.1": {"Ben": 2, "Di": 1, "Merger": 1},
        }
        for tag, info in dc.tags.items():
            assert info["commits"] == sum(expected[tag].values())
        assert dc.tags["v1.1"]["date"] == "2023-01-07"

    def test_second_tag_on_a_tagged_commit_gets_no_commits(self, git_repo, monkeypatch):
        _git(git_repo, "tag", "release-1.1", "v1.1.0")
        monkeypatch.chdir(git_repo)
        dc = GitDataCollector()
        dc._collect_tags()

        # tags on one commit are walked by name: the first takes the commits
        assert dc.tags["release-1.1"]["commits"] == 2
        assert dc.tags["v1.1.0"]["commits"] == 0
        assert dc.tags["v1.1.0"]["authors"] == {}
        assert dc.tags["v1.0.0"]["commits"] == 2

    def test_commit_stats_skip_malformed_lines(self, monkeypatch):
        fake = _fake_git(
            {
                "git rev-list --pretty": (
                    "1700000000 2023-11-14 22:13:20 +0000 Ann <ann@example.com>\n"
                    "short line\n"
                    "not-a-stamp 2023-11-14 22:13:20 +0100 Bo <bo-at-nowhere>\n"
                )
            }
        )
        monkeypatch.setattr("gitstats.main.get_pipe_output", fake)
        dc = GitDataCollector()
        identities = dc._collect_commit_stats()

        assert set(dc.authors) == {"Ann", "Bo"}
        assert dc.authors["Bo"]["first_commit_stamp"] == 0
        # an address without "@" has no domain
        assert dc.domains == {"example.com": {"commits": 1}, "?": {"commits": 1}}
        assert dc.commits_by_timezone == {"+0000": 1, "+0100": 1}
        assert identities == {("Ann", "ann@example.com"): 1700000000, ("Bo", "bo-at-nowhere"): 0}

    def test_commit_stats_sort_addresses_by_organization(self, monkeypatch):
        fake = _fake_git(
            {
                "git rev-list --pretty": (
                    "1700000000 2023-11-14 22:13:20 +0000 Ann <ann@corp.google.com>\n"
                    "1700000100 2023-11-14 22:15:00 +0000 Ann <Ann@google.com>\n"
                    "1690000000 2023-07-22 04:26:40 +0000 Bo <bo@google.com>\n"
                    "1700000200 2023-11-14 22:16:40 +0000 Cy <cy@gmail.com>\n"
                    "1700000300 2023-11-14 22:18:20 +0000 dependabot[bot] <1+dependabot[bot]@users.noreply.github.com>\n"
                )
            }
        )
        monkeypatch.setattr("gitstats.main.get_pipe_output", fake)
        dc = GitDataCollector()
        dc._collect_commit_stats()

        google = dc.organizations["google.com"]
        assert set(dc.organizations) == {"google.com"}
        assert google["commits"] == 3
        assert google["first_commit_stamp"] == 1690000000
        assert google["last_commit_stamp"] == 1700000100
        month = datetime.datetime.fromtimestamp(1700000000).strftime("%Y-%m")
        july = datetime.datetime.fromtimestamp(1690000000).strftime("%Y-%m")
        assert google["by_month"] == {month: 2, july: 1}
        # addresses are told apart without case, and only counted
        assert dc.organization_authors == {"google.com": 3}
        # and names, without case or extra spaces: Ann and Bo
        assert dc.organization_people == {"google.com": 2}
        # so the JSON output (the collector's attributes) holds no address
        kept = (dc.organizations, dc.organization_authors, dc.affiliation_by_month)
        assert "@" not in json.dumps(kept, default=str)
        assert dc.affiliation_by_month[month] == {"organization": 2, "personal": 1, "bot": 1}
        assert dc.affiliation_by_month[july] == {"organization": 1}
        # the bot is left out of the people's commits and days
        assert dc.human_commits_by_year == {2023: 4}
        assert dc.human_active_days == {
            datetime.datetime.fromtimestamp(stamp).strftime("%Y-%m-%d")
            for stamp in (1700000000, 1700000100, 1690000000, 1700000200)
        }

    def test_commit_stats_count_hours_on_each_commits_own_clock(self, monkeypatch):
        """Not on the clock of the machine the report is generated on."""
        fake = _fake_git(
            {
                "git rev-list --pretty": (
                    # one moment, 2023-11-14 22:13:20 UTC, committed in three places
                    "1700000000 2023-11-15 07:13:20 +0900 Ann <ann@example.com>\n"
                    "1700000000 2023-11-14 14:13:20 -0800 Bo <bo@example.com>\n"
                    "1700000000 2023-11-15 03:43:20 +0530 Cy <cy@example.com>\n"
                )
            }
        )
        monkeypatch.setattr("gitstats.main.get_pipe_output", fake)
        dc = GitDataCollector()
        dc._collect_commit_stats()

        assert dc.activity_by_hour_of_day == {7: 1, 14: 1, 3: 1}
        # already Wednesday in Tokyo and Kolkata, still Tuesday in California
        assert dc.activity_by_day_of_week == {2: 2, 1: 1}
        assert dc.activity_by_hour_of_week == {2: {7: 1, 3: 1}, 1: {14: 1}}

    def test_record_author_commit_moves_last_commit_forward(self):
        dc = GitDataCollector()
        early = datetime.datetime(2024, 1, 10, 9, 0)
        late = datetime.datetime(2024, 3, 20, 9, 0)
        dc._record_author_commit("Ann", int(early.timestamp()), early)
        dc._record_author_commit("Ann", int(late.timestamp()), late)
        assert dc.authors["Ann"]["first_commit_stamp"] == int(early.timestamp())
        assert dc.authors["Ann"]["last_commit_stamp"] == int(late.timestamp())

    def test_merge_author_aliases_renames_and_merges_partial_entries(self):
        dc = GitDataCollector()
        dc.authors = {
            "Old Nick": {"commits": 2},  # its canonical name has no entry yet
            "Ann": {"commits": 3, "first_commit_stamp": 10, "last_commit_stamp": 50},
            "ann (laptop)": {"commits": 1},  # no stamps or active days
            "Anonymous": {"commits": 1},  # no email at all
        }
        mapping = dc._merge_author_aliases(
            {
                ("Old Nick", "n@x.com"): 80,
                ("Nick", "n@x.com"): 90,
                ("Ann", "a@x.com"): 50,
                ("ann (laptop)", "a@x.com"): 40,
                ("Anonymous", ""): 5,
            }
        )

        assert mapping == {"Old Nick": "Nick", "ann (laptop)": "Ann"}
        assert set(dc.authors) == {"Nick", "Ann", "Anonymous"}
        assert dc.authors["Nick"] == {"commits": 2}
        assert dc.authors["Ann"] == {
            "commits": 4,
            "lines_added": 0,
            "lines_removed": 0,
            "first_commit_stamp": 10,
            "last_commit_stamp": 50,
        }
        assert dc.total_authors == 3

    def test_merge_author_aliases_keeps_the_latest_commit_of_an_alias(self):
        dc = GitDataCollector()
        dc.authors = {
            "Ann": {"commits": 1, "first_commit_stamp": 300, "last_commit_stamp": 300},
            "ann": {"commits": 1, "first_commit_stamp": 100, "last_commit_stamp": 900},
        }
        dc._merge_author_aliases({("Ann", "a@x.com"): 300, ("ann", "a@x.com"): 200})
        assert dc.authors == {
            "Ann": {
                "commits": 2,
                "lines_added": 0,
                "lines_removed": 0,
                "first_commit_stamp": 100,
                "last_commit_stamp": 900,
            }
        }

    def test_files_by_stamp_reuses_the_cache(self, git_repo, monkeypatch, sequential_map):
        monkeypatch.chdir(git_repo)
        first = GitDataCollector()
        first._collect_files_by_stamp()

        # forget one revision: only that one is counted again
        second = GitDataCollector()
        second.cache = json.loads(json.dumps(first.cache))
        forgotten = sorted(second.cache["files_in_tree"])[0]
        del second.cache["files_in_tree"][forgotten]
        from gitstats.utils import count_files_in_trees

        with (
            patch(
                "gitstats.main.count_files_in_trees", side_effect=count_files_in_trees
            ) as counted,
            patch("gitstats.main.get_num_of_files_from_rev") as listed,
        ):
            second._collect_files_by_stamp()

        history, wanted, _, added = counted.call_args.args
        assert wanted == {forgotten}
        # the history of HEAD, and nothing known of the files its commits add
        assert len(history.commits) == 5
        assert added is None
        # no tree had to be listed file by file
        listed.assert_not_called()
        assert second.cache["files_in_tree"] == first.cache["files_in_tree"]
        assert second.files_by_stamp == first.files_by_stamp
        # files in the tree after each of the five commits
        assert sorted(second.files_by_stamp.values()) == [2, 3, 3, 4, 5]
        assert second.total_commits == 5

        # with every revision in the cache, git is not asked to count anything
        third = GitDataCollector()
        third.cache = json.loads(json.dumps(first.cache))
        with patch("gitstats.main.count_files_in_trees") as counted:
            third._collect_files_by_stamp()
        counted.assert_not_called()
        assert third.files_by_stamp == first.files_by_stamp

    def test_files_by_stamp_lists_the_trees_that_could_not_be_counted(
        self, git_repo, monkeypatch, sequential_map
    ):
        monkeypatch.chdir(git_repo)
        reference = GitDataCollector()
        reference._collect_files_by_stamp()

        # the comparison of commits finds nothing (git failed, say): every
        # tree is listed, as it was before, and the numbers are the same
        from gitstats.utils import get_num_of_files_from_rev

        dc = GitDataCollector()
        with (
            patch("gitstats.main.count_files_in_trees", return_value={}),
            patch(
                "gitstats.main.get_num_of_files_from_rev", side_effect=get_num_of_files_from_rev
            ) as listed,
        ):
            dc._collect_files_by_stamp()
        assert listed.call_count == 5
        assert dc.files_by_stamp == reference.files_by_stamp
        assert dc.cache["files_in_tree"] == reference.cache["files_in_tree"]

    def test_files_by_stamp_use_what_the_line_counts_say(self, git_repo, monkeypatch):
        """Handed the files each commit adds, the phase has git compare only
        the commits that are left out, and lists one tree to make sure."""
        import gitstats.utils as utils
        from gitstats.utils import get_num_of_files_from_rev, history_graph, shortstat_logs

        monkeypatch.chdir(git_repo)
        reference = GitDataCollector()
        reference._collect_files_by_stamp()

        _, added, _ = shortstat_logs(GitDataCollector._line_stat_passes(), "HEAD", 2)
        # the four commits that have a parent: three add a file, one changes one
        assert sorted(added.values()) == [0, 1, 1, 1]
        compared = []
        real = utils._git_lines

        def spy(args, stdin=None):
            compared.extend(line for line in stdin.read().split("\n") if line)
            stdin.seek(0)
            return real(args, stdin)

        monkeypatch.setattr(utils, "_git_lines", spy)
        read = []

        def history():
            read.append(history_graph("HEAD"))
            return read[-1]

        dc = GitDataCollector()
        with patch(
            "gitstats.main.get_num_of_files_from_rev", side_effect=get_num_of_files_from_rev
        ) as listed:
            dc._collect_files_by_stamp(history, lambda: added)

        assert dc.files_by_stamp == reference.files_by_stamp
        assert dc.cache["files_in_tree"] == reference.cache["files_in_tree"]
        # the history it was handed, read once; git compared the first commit only
        assert len(read) == 1
        root = subprocess.run(
            ["git", "rev-list", "--max-parents=0", "HEAD"],
            cwd=git_repo, capture_output=True, text=True, check=True,
        ).stdout.split()  # fmt: skip
        assert compared == root
        # and the newest tree was listed, to check the sum
        assert listed.call_count == 1

    def test_files_by_stamp_do_not_trust_counts_that_do_not_add_up(
        self, git_repo, monkeypatch, caplog
    ):
        """If what the line counts say of the files does not lead to the number
        of files there are, git is asked about every commit, as without them."""
        from gitstats.utils import count_files_in_trees, shortstat_logs

        monkeypatch.chdir(git_repo)
        reference = GitDataCollector()
        reference._collect_files_by_stamp()

        _, added, _ = shortstat_logs(GitDataCollector._line_stat_passes(), "HEAD", 2)
        # as a git set up to show diffs another way might have it
        wrong = {commit: change + 1 for commit, change in added.items()}

        dc = GitDataCollector()
        with (
            patch(
                "gitstats.main.count_files_in_trees", side_effect=count_files_in_trees
            ) as counted,
            caplog.at_level(logging.DEBUG, logger="gitstats"),
        ):
            dc._collect_files_by_stamp(None, lambda: wrong)

        assert "do not add up" in caplog.text
        # counted twice: with what it was told, then without
        assert [len(call.args) for call in counted.call_args_list] == [4, 3]
        assert dc.files_by_stamp == reference.files_by_stamp
        assert dc.cache["files_in_tree"] == reference.cache["files_in_tree"]

    def test_files_by_stamp_without_line_counts(self, git_repo, monkeypatch):
        """The line counts failed, or `processes = 1`: nothing is known of the
        files the commits add, and nothing needs checking."""
        monkeypatch.chdir(git_repo)
        reference = GitDataCollector()
        reference._collect_files_by_stamp()

        dc = GitDataCollector()
        with patch("gitstats.main.get_num_of_files_from_rev") as listed:
            dc._collect_files_by_stamp(None, lambda: None)
        listed.assert_not_called()
        assert dc.files_by_stamp == reference.files_by_stamp

    def test_files_by_stamp_counts_up_to_the_configured_end(self, git_repo, monkeypatch):
        _use_config(commit_end="HEAD~2")
        monkeypatch.chdir(git_repo)
        from gitstats.utils import count_files_in_trees

        dc = GitDataCollector()
        with patch(
            "gitstats.main.count_files_in_trees", side_effect=count_files_in_trees
        ) as counted:
            dc._collect_files_by_stamp()
        assert len(counted.call_args.args[0].commits) == 3
        # the three first commits, and nothing of the two after them
        assert sorted(dc.files_by_stamp.values()) == [2, 3, 3]
        assert len(dc.cache["files_in_tree"]) == 3

    def test_extensions_skip_submodules_and_bucket_long_extensions(
        self, git_repo, monkeypatch, sequential_map
    ):
        with open(os.path.join(git_repo, "dump.verylongextension"), "w") as f:
            f.write("one\ntwo\n")
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=git_repo, capture_output=True, text=True, check=True
        ).stdout.strip()
        _git(git_repo, "add", "dump.verylongextension")
        _git(git_repo, "update-index", "--add", "--cacheinfo", f"160000,{head},vendor/lib")
        _git(git_repo, "commit", "-m", "Add a submodule and a data file")
        monkeypatch.chdir(git_repo)

        dc = GitDataCollector()
        # a cache that knows other blobs: these ones are still read from git
        dc.cache = {"lines_in_blob": {"0" * 40: 99}}
        dc._collect_extensions()

        assert "vendor/lib" not in dc.head_files
        assert dc.total_files == 6
        assert dc.extensions[""] == {"files": 1, "lines": 2}
        assert dc.extensions["py"] == {"files": 2, "lines": 8}
        # the six blobs of the files, .gitignore without an extension among
        # them, were read and added to the cache
        assert len(dc.cache["lines_in_blob"]) == 7
        # all of their lines are the lines of code: the binary logo has none
        assert dc.total_lines == 3 + 2 + 8 + 2

    def test_line_stats_without_linear_history_and_with_stray_lines(self, monkeypatch, caplog):
        _use_config(linear_linestats=0)
        # git prints newest first; the collector reads the lines oldest first
        fake = _fake_git(
            {
                "git log --root --shortstat": (
                    "1700000300 Ann\n"
                    " 1 file changed, 5 insertions(+)\n"
                    "stray\n"
                    "not-a-stamp Bo\n"
                    " 2 files changed, 3 insertions(+), 1 deletion(-), 9 surprises\n"
                    "1700000100 Ann\n"
                )
            }
        )
        monkeypatch.setattr("gitstats.main.get_pipe_output", fake)
        dc = GitDataCollector()
        with caplog.at_level(logging.WARNING, logger="gitstats"):
            dc._collect_line_stats()

        assert "--first-parent" not in fake.calls[0]
        assert dc.changes_by_date[1700000100] == {"files": 0, "ins": 0, "del": 0, "lines": 0}
        assert dc.changes_by_date[1700000300] == {"files": 1, "ins": 5, "del": 0, "lines": 5}
        # the lines of code are those of the files, not what the diffs add up to
        assert dc.total_lines == 0
        assert dc.total_lines_added == 5
        assert 'Unexpected line "stray"' in caplog.text
        assert 'Unexpected line "not-a-stamp Bo"' in caplog.text
        assert "Failed to handle line" in caplog.text

    def test_per_author_line_stats_add_unknown_authors(self, monkeypatch, caplog):
        fake = _fake_git(
            {
                "git log --root --shortstat --date-order": (
                    "1700000300 Newcomer\n"
                    " 1 file changed, 4 insertions(+), 2 deletions(-)\n"
                    "stray\n"
                    "not-a-stamp Bo\n"
                    " 1 file changed, 1 insertion(+), 1 deletion(-), 7 surprises\n"
                )
            }
        )
        monkeypatch.setattr("gitstats.main.get_pipe_output", fake)
        dc = GitDataCollector()
        with caplog.at_level(logging.WARNING, logger="gitstats"):
            dc._collect_per_author_line_stats({})

        assert dc.authors == {"Newcomer": {"lines_added": 4, "lines_removed": 2, "commits": 1}}
        assert dc.changes_by_date_by_author == {
            1700000300: {"Newcomer": {"lines_added": 4, "commits": 1}}
        }
        assert 'Unexpected line "stray"' in caplog.text
        assert 'Unexpected line "not-a-stamp Bo"' in caplog.text
        assert "Failed to handle line" in caplog.text

    def test_file_churn_ignores_files_before_the_first_commit_marker(self, monkeypatch):
        fake = _fake_git(
            {
                'git -c core.quotePath=false log --root --format="COMMIT:%aN"': (
                    "orphan.txt\nCOMMIT:Ann\na.py\n\nCOMMIT:Bob\na.py\nb.py\n"
                )
            }
        )
        monkeypatch.setattr("gitstats.main.get_pipe_output", fake)
        dc = GitDataCollector()
        dc._collect_file_churn_and_ownership({"Bob": "Robert"})

        assert dc.file_churn == {"orphan.txt": 1, "a.py": 2, "b.py": 1}
        assert dc.author_files == {"Ann": {"a.py": 1}, "Robert": {"a.py": 1, "b.py": 1}}

    def test_commit_subjects_skip_unreadable_lines(self, monkeypatch):
        fake = _fake_git(
            {
                "git log --reverse": (
                    "1700000000 First subject\n\nno-space\nnot-a-stamp Something\n"
                    "1700000200 Second subject\n"
                )
            }
        )
        monkeypatch.setattr("gitstats.main.get_pipe_output", fake)
        dc = GitDataCollector()
        dc._collect_commit_subjects()
        assert dc.commit_subjects_by_year == {2023: ["First subject", "Second subject"]}

    def test_refine_fills_in_missing_line_counts(self):
        dc = GitDataCollector()
        dc.total_commits = 4
        dc.authors = {
            "Ann": {
                "commits": 3,
                "first_commit_stamp": 1700000000,
                "last_commit_stamp": 1700172800,
            },
            "Bo": {"commits": 1, "first_commit_stamp": 1700000000, "last_commit_stamp": 1700000000},
        }
        dc.refine()

        assert dc.authors["Ann"]["lines_added"] == 0
        assert dc.authors["Ann"]["lines_removed"] == 0
        assert dc.authors["Ann"]["commits_frac"] == 75.0
        assert dc.authors["Ann"]["timedelta"] == datetime.timedelta(days=2)
        assert dc.authors_by_commits == ["Ann", "Bo"]
        assert sum(dc.new_contributors_by_month.values()) == 2


class TestAccessors:
    def test_get_domains(self):
        dc = GitDataCollector()
        dc.domains = {"example.com": {"commits": 2}, "test.org": {"commits": 1}}
        assert dc.get_domains() == ["example.com", "test.org"]
        assert dc.get_domain_info("test.org") == {"commits": 1}

    def test_get_tags_lists_tag_names(self):
        dc = GitDataCollector()
        with patch("gitstats.main.get_pipe_output", return_value="v1.0.0\nv1.1.0") as git:
            assert dc.get_tags() == ["v1.0.0", "v1.1.0"]
        git.assert_called_once_with(["git show-ref --tags", "cut -d/ -f3"])

    def test_tag_and_revision_dates(self, git_repo, monkeypatch):
        monkeypatch.chdir(git_repo)
        dc = GitDataCollector()
        assert dc.get_tag_date("v1.0.0") == "2023-02-20"
        assert dc.rev_to_date("HEAD") == "2023-05-01"


# ── output paths ─────────────────────────────────────────────────────────


def test_prepare_output_dir_refuses_a_target_outside_its_parent(tmp_path):
    with (
        patch("gitstats.main.os.path.commonpath", return_value=str(tmp_path / "elsewhere")),
        pytest.raises(ValueError, match="Refusing to create output directory"),
    ):
        _prepare_output_dir(str(tmp_path / "out"))
    assert not (tmp_path / "out").exists()


def test_dump_json_refuses_a_target_outside_the_directory(tmp_path):
    with (
        patch("gitstats.main.os.path.commonpath", return_value=str(tmp_path / "elsewhere")),
        pytest.raises(ValueError, match="Refusing to write outside output directory"),
    ):
        _dump_json_within(str(tmp_path), "data.json", DataCollector())
    assert not (tmp_path / "data.json").exists()


class TestRunSingleRepo:
    def test_rejects_a_file_as_output(self, git_repo_minimal, tmp_path):
        target = tmp_path / "report"
        target.write_text("not a directory")
        with pytest.raises(RuntimeError, match="Output path is not a directory"):
            _run_single_repo(git_repo_minimal, str(target))

    def test_writes_json_inside_the_output_directory(
        self, git_repo_minimal, tmp_path, sequential_map
    ):
        out = tmp_path / "report"
        _run_single_repo(git_repo_minimal, str(out), "json", json_sibling=False)
        dump = json.loads((out / "gitstats.json").read_text(encoding="utf-8"))
        assert dump["total_commits"] == 1
        assert not (tmp_path / "report.json").exists()

    def test_rejects_an_unknown_format(self, git_repo_minimal, tmp_path, sequential_map):
        with pytest.raises(RuntimeError, match="Unsupported format 'xml'"):
            _run_single_repo(git_repo_minimal, str(tmp_path / "report"), "xml")

    def test_adds_ai_summaries_when_enabled(self, git_repo_minimal, tmp_path, sequential_map):
        _use_config(ai_enabled=True, refresh_ai=True)
        summaries = {"index": {"summary": "<p>Quiet but steady.</p>", "error": None}}
        summarizer = MagicMock()
        summarizer.generate_all_summaries.return_value = summaries
        out = tmp_path / "report"
        with patch("gitstats.main.AISummarizer", return_value=summarizer) as summarizer_class:
            data = _run_single_repo(git_repo_minimal, str(out))

        assert data.ai_summaries == summaries
        assert summarizer_class.call_args.args[0]["ai_enabled"] is True
        summarizer.set_cache_dir.assert_called_once_with(os.path.join(str(out), ".ai_cache"))
        assert summarizer.generate_all_summaries.call_args.args[1] is True  # refresh_ai
        assert "Quiet but steady." in (out / "ai-insights.html").read_text(encoding="utf-8")

    def test_reports_without_ai_when_the_summaries_fail(
        self, git_repo_minimal, tmp_path, caplog, sequential_map
    ):
        _use_config(ai_enabled=True)
        with (
            patch("gitstats.main.AISummarizer", side_effect=RuntimeError("no API key")),
            caplog.at_level(logging.INFO, logger="gitstats"),
        ):
            data = _run_single_repo(git_repo_minimal, str(tmp_path / "report"))
        assert data.ai_summaries == {}
        assert "Failed to generate AI summaries: no API key" in caplog.text
        assert (tmp_path / "report" / "index.html").exists()


class TestWrappedCard:
    """--wrapped: a Repo Wrapped card next to each report."""

    @staticmethod
    def _config(**overrides):
        return {"enabled": True, "year": 2023, "theme": "midnight", "output": None, **overrides}

    def test_no_card_unless_asked(self, git_repo_minimal, tmp_path, sequential_map):
        out = tmp_path / "report"
        _run_single_repo(git_repo_minimal, str(out))
        assert not list(out.glob("wrapped-*.svg"))

    def test_writes_the_card_into_the_report_directory(
        self, git_repo_minimal, tmp_path, caplog, sequential_map
    ):
        out = tmp_path / "report"
        with caplog.at_level(logging.INFO, logger="gitstats"):
            _run_single_repo(git_repo_minimal, str(out), wrapped_config=self._config(theme="clean"))

        card = (out / "wrapped-2023.svg").read_text(encoding="utf-8")
        assert "REPO WRAPPED" in card
        assert ">2023</text>" in card
        assert "git_repo_minimal" in card
        assert THEMES["clean"]["bg_start"] in card
        assert "Wrapped card saved: " in caplog.text
        assert (out / "index.html").exists()

    def test_the_report_shows_the_card_and_links_it_from_its_year(
        self, git_repo_minimal, tmp_path, sequential_map
    ):
        out = tmp_path / "report"
        _run_single_repo(git_repo_minimal, str(out), wrapped_config=self._config(theme="sunset"))

        badges = (out / "badges.html").read_text(encoding="utf-8")
        assert 'data-kind="card" data-badge="wrapped-2023.svg"' in badges
        assert "1080 &times; 1080, sunset theme" in badges
        assert '<img src="wrapped-2023.svg" width="240" height="240"' in badges
        history = (out / "history.html").read_text(encoding="utf-8")
        assert '<a href="wrapped-2023.svg">Wrapped card &rarr;</a>' in history

    def test_the_report_has_no_card_to_show_when_none_is_next_to_it(
        self, git_repo_minimal, tmp_path, sequential_map
    ):
        def pages(out):
            return (
                (out / "badges.html").read_text(encoding="utf-8"),
                (out / "history.html").read_text(encoding="utf-8"),
            )

        # not asked for
        _run_single_repo(git_repo_minimal, str(tmp_path / "plain"))
        # written to another directory
        cards = tmp_path / "cards"
        cards.mkdir()
        _run_single_repo(
            git_repo_minimal,
            str(tmp_path / "elsewhere"),
            wrapped_config=self._config(output=str(cards / "2023.svg")),
        )
        # a year without commits: no card is written
        _run_single_repo(
            git_repo_minimal, str(tmp_path / "empty-year"), wrapped_config=self._config(year=2019)
        )
        for name in ("plain", "elsewhere", "empty-year"):
            badges, history = pages(tmp_path / name)
            assert "There is none next to this report" in badges, name
            assert 'data-kind="card"' not in badges, name
            assert "Wrapped card" not in history, name

    def test_the_card_holds_the_numbers_of_its_year(
        self, git_repo_minimal, tmp_path, sequential_map
    ):
        out = tmp_path / "report"
        _run_single_repo(git_repo_minimal, str(out), wrapped_config=self._config())
        card = (out / "wrapped-2023.svg").read_text(encoding="utf-8")
        # one commit on 2023-06-01 at noon, a Thursday
        for value, label in (("1", "Commits"), ("1", "Active Days"), ("1 day", "Longest Streak")):
            assert re.search(rf">{value}</text>\s*<text[^>]*>{label}</text>", card)
        assert "Afternoon Coder" in card
        assert "100% of commits between 12:00 and 18:00" in card
        assert ">June</tspan>" in card
        assert ">Thursday</tspan>" in card
        assert ">Test</tspan> · 1 commit</text>" in card

    def test_the_card_is_for_the_current_year_by_default(
        self, git_repo_minimal, tmp_path, caplog, sequential_map
    ):
        """The repository's commits are from 2023: the current year has none."""
        out = tmp_path / "report"
        with caplog.at_level(logging.INFO, logger="gitstats"):
            _run_single_repo(git_repo_minimal, str(out), wrapped_config=self._config(year=None))
        year = datetime.datetime.now().year
        assert (
            f"Failed to generate Wrapped card: no commits in {year}; "
            "the last year with commits is 2023"
        ) in caplog.text
        # no card of all-time numbers under a year they do not belong to
        assert not list(out.glob("wrapped-*.svg"))
        assert (out / "index.html").exists()

    def test_writes_the_card_where_asked(self, git_repo_minimal, tmp_path, sequential_map):
        out = tmp_path / "report"
        cards = tmp_path / "cards"
        cards.mkdir()
        _run_single_repo(
            git_repo_minimal,
            str(out),
            wrapped_config=self._config(output=str(cards / "2023.svg")),
        )
        assert ">2023</text>" in (cards / "2023.svg").read_text(encoding="utf-8")
        assert not list(out.glob("wrapped-*.svg"))

    def test_reports_without_the_card_when_it_cannot_be_written(
        self, git_repo_minimal, tmp_path, caplog, sequential_map
    ):
        out = tmp_path / "report"
        missing = tmp_path / "no-such-directory" / "card.svg"
        with caplog.at_level(logging.INFO, logger="gitstats"):
            data = _run_single_repo(
                git_repo_minimal, str(out), wrapped_config=self._config(output=str(missing))
            )
        assert "Failed to generate Wrapped card" in caplog.text
        assert not missing.exists()
        assert data.total_commits == 1
        assert (out / "index.html").exists()

    def test_run_passes_the_card_on_for_one_repository(self, tmp_path):
        config = self._config()
        with (
            patch("gitstats.main._run_single_repo", return_value=DataCollector()) as single,
            patch("gitstats.main.write_repo_summary"),
            patch("gitstats.main.compute_repo_summary"),
        ):
            assert run(["repo"], str(tmp_path / "report"), wrapped_config=config) == 0
        assert single.call_args.kwargs["wrapped_config"] is config

    def test_each_repository_of_a_portfolio_gets_its_card(
        self, git_repo, git_repo_minimal, tmp_path, sequential_map
    ):
        out = tmp_path / "portfolio"
        assert run([git_repo, git_repo_minimal], str(out), wrapped_config=self._config()) == 0
        for name in ("git_repo", "git_repo_minimal"):
            card = (out / name / "wrapped-2023.svg").read_text(encoding="utf-8")
            assert name in card
        assert not list(out.glob("wrapped-*.svg"))

    def test_main_builds_the_card_from_the_flags(self, git_repo_minimal, tmp_path, sequential_map):
        out = tmp_path / "report"
        argv = ["gitstats", "--wrapped", "--wrapped-year", "2023", "--wrapped-theme", "sunset"]
        with patch.object(sys, "argv", argv + [git_repo_minimal, str(out)]):
            assert main() == 0
        card = (out / "wrapped-2023.svg").read_text(encoding="utf-8")
        assert THEMES["sunset"]["bg_start"] in card

    def test_main_resolves_the_output_path_before_running(
        self, git_repo_minimal, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        argv = ["gitstats", "--wrapped", "--wrapped-output", "card.svg", git_repo_minimal, "out"]
        with patch.object(sys, "argv", argv), patch("gitstats.main.run", return_value=0) as run_:
            assert main() == 0
        assert run_.call_args.kwargs["wrapped_config"] == {
            "enabled": True,
            "year": None,
            "theme": "midnight",
            "output": os.path.abspath("card.svg"),
        }

    def test_main_rejects_one_output_file_for_several_repositories(self, tmp_path, capsys):
        argv = ["gitstats", "--wrapped", "--wrapped-output", "card.svg", "one", "two", "out"]
        with patch.object(sys, "argv", argv), pytest.raises(SystemExit) as exit_info:
            main()
        assert exit_info.value.code == 2
        assert "--wrapped-output names one file" in capsys.readouterr().err


class TestRunEdgeCases:
    def test_rejects_a_file_as_output(self, git_repo_minimal, tmp_path, caplog):
        target = tmp_path / "report"
        target.write_text("not a directory")
        assert run([git_repo_minimal], str(target)) == 1
        assert "Output path is not a directory" in caplog.text

    def test_suggests_serve_on_a_terminal(self, git_repo_minimal, tmp_path, caplog, sequential_map):
        with (
            patch("gitstats.main.sys.stdin") as stdin,
            caplog.at_level(logging.INFO, logger="gitstats"),
        ):
            stdin.isatty.return_value = True
            assert run([git_repo_minimal], str(tmp_path / "report")) == 0
        assert "re-run with --serve" in caplog.text

    def test_multi_repo_names_duplicates_and_skips_unnamed_paths(self, tmp_path):
        def fake_single_repo(path, outdir, extra_fmt=None, **kwargs):
            os.makedirs(outdir, exist_ok=True)
            data = DataCollector()
            data.project_name = kwargs["project_name"]
            return data

        paths = [tmp_path / "one" / "repo", tmp_path / "two" / "repo", tmp_path / "___"]
        out = tmp_path / "portfolio"
        out.mkdir()
        with patch("gitstats.main._run_single_repo", side_effect=fake_single_repo) as single:
            assert _run_multi_repo([str(p) for p in paths], str(out)) == 0

        assert [c.kwargs["project_name"] for c in single.call_args_list] == ["repo", "repo-2"]
        summary = json.loads((out / "repo-2" / "summary.json").read_text(encoding="utf-8"))
        assert summary["report_path"] == "repo-2/index.html"
        page = (out / "index.html").read_text(encoding="utf-8")
        assert "Failed repositories" in page
        assert "Cannot derive a repository name" in page


class TestServeEdgeCases:
    def test_server_urls_loopback_names(self):
        assert _server_urls("localhost", 8000) == ("http://localhost:8000/", None)
        assert _server_urls("::1", 8000) == ("http://[::1]:8000/", None)

    def test_server_urls_all_interfaces_without_a_route(self):
        with (
            patch("gitstats.main.socket.socket", side_effect=OSError("network is unreachable")),
            patch("gitstats.main.socket.gethostname", return_value="buildbox"),
        ):
            assert _server_urls("0.0.0.0", 8000) == (
                "http://127.0.0.1:8000/",
                "http://buildbox:8000/",
            )

    def test_serve_report_runs_until_ctrl_c(self, tmp_path, capsys):
        server = MagicMock()
        server.server_address = ("127.0.0.1", 8123)
        server.serve_forever.side_effect = KeyboardInterrupt
        with patch("gitstats.main._make_server", return_value=server) as make_server:
            assert _serve_report(str(tmp_path), "127.0.0.1", 0) == 0

        make_server.assert_called_once_with(str(tmp_path), "127.0.0.1", 0)
        server.server_close.assert_called_once_with()
        out = capsys.readouterr().out
        assert "http://127.0.0.1:8123/" in out
        assert "use --host 0.0.0.0 to expose" in out
        assert "stopped" in out

    def test_serve_report_when_the_port_is_taken(self, tmp_path, caplog):
        with patch("gitstats.main._make_server", side_effect=OSError("Address already in use")):
            assert _serve_report(str(tmp_path), "127.0.0.1", 8000) == 1
        assert "Cannot serve on 127.0.0.1:8000: Address already in use" in caplog.text


class TestMainArguments:
    @pytest.mark.parametrize(
        "override,message",
        [("max_authors", "key=value"), ("no_such_key=1", 'No such key "no_such_key"')],
    )
    def test_rejects_bad_config_overrides(self, override, message, tmp_path, capsys):
        with (
            patch.object(sys, "argv", ["gitstats", "-c", override, str(tmp_path)]),
            pytest.raises(SystemExit) as exit_info,
        ):
            main()
        assert exit_info.value.code == 2
        assert message in capsys.readouterr().err

    def test_ai_flags_override_the_config(self):
        conf = {"ai_enabled": False, "ai_provider": "openai", "ai_model": "", "ai_language": "en"}
        args = get_parser().parse_args(
            ["--ai", "--ai-provider", "ollama", "--ai-model", "llama3", "--ai-language", "zh"]
            + ["--refresh-ai", "repo"]
        )
        _apply_ai_args(conf, args)
        assert conf == {
            "ai_enabled": True,
            "ai_provider": "ollama",
            "ai_model": "llama3",
            "ai_language": "zh",
            "refresh_ai": True,
        }

    def test_without_ai_flags_the_config_stays(self):
        conf = {"ai_enabled": True, "ai_provider": "claude", "ai_model": "m", "ai_language": "de"}
        _apply_ai_args(conf, get_parser().parse_args(["repo"]))
        assert conf == {
            "ai_enabled": True,
            "ai_provider": "claude",
            "ai_model": "m",
            "ai_language": "de",
            "refresh_ai": False,
        }

    def test_site_url_and_serve(self, git_repo_minimal, tmp_path, sequential_map):
        import gitstats.main

        out = tmp_path / "report"
        argv = ["gitstats", "--site-url", "https://example.com/stats", "--serve", "--port", "0"]
        with (
            patch.object(sys, "argv", argv + [git_repo_minimal, str(out)]),
            patch("gitstats.main._serve_report", return_value=0) as serve,
        ):
            assert main() == 0

        serve.assert_called_once_with(str(out), "127.0.0.1", 0)
        assert gitstats.main.conf["site_url"] == "https://example.com/stats"
        assert "https://example.com/stats/" in (out / "badges.html").read_text(encoding="utf-8")


def test_source_lines_when_git_fails(monkeypatch):
    def failing(cmds, quiet=False):
        raise subprocess.CalledProcessError(128, cmds)

    monkeypatch.setattr("gitstats.main.get_pipe_output", failing)
    assert GitDataCollector()._source_lines() is None


def test_source_lines_count_insertions(monkeypatch):
    printed = (
        "\x01" + "a" * 40 + "\n\n10\t3\tsrc/a.py\n2\t0\tvendor/b.go\n-\t-\tlogo.png\n"
        "\x01" + "b" * 40 + '\n\n1\t0\t"src/r\\303\\251sum\\303\\251.py"\n0\t4\tsrc/a.py\n'
    )
    seen = []
    monkeypatch.setattr(
        "gitstats.main.get_pipe_output", lambda cmds, quiet=False: seen.append(cmds) or printed
    )
    assert GitDataCollector()._source_lines() == 11
    assert seen == [["git -c core.quotePath=false log --root --numstat --format=%x01%H HEAD"]]


# ── what the numbers of a report are made of ─────────────────────────────


def _history(repo, commits, **config):
    """Make a repository at ``repo`` of ``commits``, each ``(name, email, date,
    {path: lines or text, or None to delete it})``; ``config`` is set in its
    .git/config."""
    repo.mkdir()
    _git(repo, "init", "-q")
    for key, value in config.items():
        _git(repo, "config", key, value)
    for name, email, date, files in commits:
        for path, content in files.items():
            target = repo / path
            if content is None:
                target.unlink()
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, int):
                content = "".join(f"line {n}\n" for n in range(content))
            target.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-q", "--allow-empty", "-m", "commit"],
            cwd=repo,
            check=True,
            capture_output=True,
            env={
                **os.environ,
                "GIT_AUTHOR_NAME": name,
                "GIT_AUTHOR_EMAIL": email,
                "GIT_AUTHOR_DATE": date,
                "GIT_COMMITTER_NAME": "Committer",
                "GIT_COMMITTER_EMAIL": "committer@example.com",
                "GIT_COMMITTER_DATE": date,
            },
        )
    return repo


def _collected(repo, monkeypatch, processes=8, **config):
    """Collect and refine ``repo`` the way a run does, on a machine of eight
    processors: with ``processes`` 1 each phase runs its own `git log`."""
    _use_config(processes=processes, **config)
    monkeypatch.chdir(repo)
    dc = GitDataCollector()
    with (
        patch("gitstats.main.os.cpu_count", return_value=8),
        patch(
            "gitstats.main.parallel_map_with_fallback",
            side_effect=lambda func, items: [func(item) for item in items],
        ),
    ):
        dc.collect(str(repo))
    dc.refine()
    return dc


ANN = ("Ann", "ann@example.com")


@pytest.mark.parametrize("processes", [8, 1])
def test_lines_of_code_leave_out_the_excluded_extensions(tmp_path, monkeypatch, processes):
    """The lines of code are those of the files at the end of the range:
    an excluded data file is not in them (it was, as diffs add up)."""
    repo = _history(
        tmp_path / "repo", [(*ANN, "2021-01-01T00:00:00", {"a.py": 10, "data.json": 5000})]
    )
    dc = _collected(repo, monkeypatch, processes, exclude_exts="json")
    assert dc.get_total_loc() == 10
    # what the diffs add stays what the history added
    assert dc.total_lines_added == 5010


@pytest.mark.parametrize(
    "config",
    [
        {"start_date": "2021-01-01"},
        {"authors": "Bo"},
        {"end_date": "2020-06-01"},
        {"commit_begin": "1"},
    ],
)
def test_lines_of_code_are_those_of_the_last_commit_whatever_the_filters(
    tmp_path, monkeypatch, config
):
    """Filters pick the commits, not the files: no negative lines of code."""
    repo = _history(
        tmp_path / "repo",
        [
            (*ANN, "2020-01-01T00:00:00", {"big.txt": 1000}),
            ("Bo", "bo@example.com", "2022-01-01T00:00:00", {"big.txt": 100}),
        ],
    )
    dc = _collected(repo, monkeypatch, **config)
    assert dc.get_total_loc() == 100


AWKWARD = ["café.py", 'say"hi".py', "tab\there.py", "plain.py"]


@pytest.mark.parametrize("processes", [8, 1])
def test_churn_and_ownership_of_files_whose_names_git_quotes(tmp_path, monkeypatch, processes):
    """A path git quotes is counted under the name the files at HEAD have."""
    awkward = [name for name in AWKWARD if os.name != "nt" or not set(name) & set('"\t')]
    repo = _history(
        tmp_path / "repo",
        [
            (*ANN, f"2021-01-0{day}T00:00:00", {name: f"{day}\n" * day for name in awkward})
            for day in (1, 2, 3)
        ],
    )
    dc = _collected(repo, monkeypatch, processes)
    assert dc.file_churn == dict.fromkeys(awkward, 3)
    assert dc.author_files == {"Ann": dict.fromkeys(awkward, 3)}
    assert {path: info["churn"] for path, info in dc.hotspot_files.items()} == dict.fromkeys(
        awkward, 3
    )


@pytest.mark.parametrize("processes", [8, 1])
def test_source_lines_of_a_vendored_file_whose_name_git_quotes(tmp_path, monkeypatch, processes):
    repo = _history(
        tmp_path / "repo", [(*ANN, "2021-01-01T00:00:00", {"vendor/ü.py": 50, "a.py": 10})]
    )
    assert _collected(repo, monkeypatch, processes).source_lines_added == 10


@pytest.mark.parametrize("space", [" ", " ", " "])
@pytest.mark.parametrize("processes", [8, 1])
def test_an_author_name_that_ends_in_unicode_whitespace(tmp_path, monkeypatch, space, processes):
    """No KeyError: the name is the same name in every phase."""
    repo = _history(
        tmp_path / "repo",
        [
            (f"Bob{space}", "bob@example.com", "2021-01-01T00:00:00", {"a.py": 3}),
            ("Bob", "bob@example.com", "2021-01-02T00:00:00", {"b.py": 2}),
        ],
    )
    dc = _collected(repo, monkeypatch, processes)
    assert list(dc.authors) == ["Bob"]
    assert dc.authors["Bob"]["commits"] == 2
    assert dc.authors["Bob"]["lines_added"] == 5
    assert dc.author_files == {"Bob": {"a.py": 1, "b.py": 1}}


def test_a_name_written_composed_and_decomposed_is_one_author(tmp_path, monkeypatch):
    repo = _history(
        tmp_path / "repo",
        [
            ("Daniel Neuhäuser", "d1@example.com", "2021-01-01T00:00:00", {"a": 1}),
            ("Daniel Neuhäuser", "d2@example.com", "2021-01-02T00:00:00", {"b": 1}),
        ],
    )
    dc = _collected(repo, monkeypatch)
    assert list(dc.authors) == ["Daniel Neuhäuser"]
    assert dc.authors["Daniel Neuhäuser"]["commits"] == 2
    assert dc.total_authors == 1


JOHN = [
    ("jdoe", "john@work.example"),
    ("John Doe", "john@work.example"),
    ("John Doe", "john@home.example"),
    ("John D.", "john@home.example"),
]


@pytest.mark.parametrize("identities", [JOHN, JOHN[::-1]])
def test_aliases_are_merged_through_a_chain_of_names_and_emails(tmp_path, monkeypatch, identities):
    """jdoe and "John Doe" share a work address, "John Doe" and "John D." a
    home one: one person, named as in the most recent commit, in any order."""
    repo = _history(
        tmp_path / "repo",
        [
            (name, email, f"2021-01-0{day}T00:00:00", {f"f{day}": 1})
            for day, (name, email) in enumerate(identities, 1)
        ],
    )
    dc = _collected(repo, monkeypatch)
    latest = identities[-1][0]
    assert dc.total_authors == 1
    assert {name: info["commits"] for name, info in dc.authors.items()} == {latest: 4}
    assert dc.author_files == {latest: {f"f{day}": 1 for day in (1, 2, 3, 4)}}


def test_merge_author_aliases_names_a_group_by_its_latest_commit():
    dc = GitDataCollector()
    dc.authors = {name: {"commits": 1} for name in ("a", "b", "c", "d", "Solo")}
    mapping = dc._merge_author_aliases(
        {
            ("a", "x@example.com"): 10,
            ("b", "x@example.com"): 40,
            ("b", "y@example.com"): 20,
            ("c", "y@example.com"): 30,
            # two names of one address tied on the stamp: the larger name
            ("c", "z@example.com"): 40,
            ("Solo", "solo@example.com"): 50,
            ("d", ""): 60,  # without an address, a name is only itself
        }
    )
    assert mapping == {"a": "c", "b": "c"}
    assert set(dc.authors) == {"c", "d", "Solo"}


def test_commit_end_that_is_all_digits_from_the_command_line():
    """-c commit_end=<a short hash of digits> stays a revision, not an int
    that get_commit_range() cannot take the length of."""
    import gitstats.main

    args = get_parser().parse_args(["-c", "commit_end=1103142", "-c", "commit_begin=10", "x"])
    gitstats.main._apply_config_from_args(gitstats.main.conf, args)
    assert gitstats.main.conf["commit_end"] == "1103142"
    assert gitstats.main.conf["commit_begin"] == "10"
    gitstats.main.conf["commit_begin"] = ""
    assert get_log_range("HEAD", False) == "1103142"


@pytest.mark.parametrize("count, commits", [("2", 2), ("9", 4)])
def test_commit_begin_is_the_last_commits(tmp_path, monkeypatch, count, commits):
    """commit_begin = N: the last N commits, all of them when there are fewer."""
    repo = _history(
        tmp_path / "repo",
        [(*ANN, f"2021-01-0{day}T00:00:00", {"a": day}) for day in (1, 2, 3, 4)],
    )
    dc = _collected(repo, monkeypatch, commit_begin=count)
    assert dc.get_total_commits() == commits


def test_commit_begin_after_a_merge(tmp_path, monkeypatch):
    """The last 2 commits are 2, not the merged branch as well."""
    repo = _history(
        tmp_path / "repo",
        [(*ANN, f"2021-01-0{day}T00:00:00", {"a": day}) for day in (1, 2)],
    )
    _git(repo, "checkout", "-q", "-b", "side", "HEAD~1")
    for day in (3, 4, 5):
        (repo / f"s{day}").write_text("s\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", f"s{day}")
    _git(repo, "checkout", "-q", "-")
    _git(repo, "merge", "-q", "--no-ff", "-m", "merge", "side")
    dc = _collected(repo, monkeypatch, commit_begin="2")
    assert dc.get_total_commits() == 2


SOURCE_MOVES = [
    # what the project has: its own code, data, a vendored library
    (*ANN, "2021-01-01T00:00:00", {"a.py": 10, "data.json": 5000, "vendor/lib.py": 100}),
    # the library moved into the project: its lines are the project's now
    (*ANN, "2021-01-02T00:00:00", {"vendor/lib.py": None, "lib.py": 100}),
    # a file of the project moved, and changed: 3 lines added
    (*ANN, "2021-01-03T00:00:00", {"a.py": None, "src/a.py": "".join(
        f"line {n}\n" for n in range(13)
    )}),
    # and one moved out of it: nothing added to the project
    (*ANN, "2021-01-04T00:00:00", {"lib.py": None, "third_party/lib.py": 100}),
    # a file moved into the project with a change: 101 lines
    (*ANN, "2021-01-05T00:00:00", {"third_party/lib.py": None, "lib2.py": "".join(
        f"line {n}\n" for n in range(101)
    )}),
]  # fmt: skip


def test_source_lines_are_counted_the_same_with_one_process_or_more(tmp_path, monkeypatch):
    repo = _history(tmp_path / "repo", SOURCE_MOVES)
    counts = {
        processes: _collected(repo, monkeypatch, processes).source_lines_added
        for processes in (4, 1)
    }
    assert counts == {4: 5000 + 10 + 100 + 3 + 101, 1: 5000 + 10 + 100 + 3 + 101}


def test_a_commit_after_the_year_9999(tmp_path, monkeypatch):
    """git takes it; it is counted at the end of the year 9999."""
    repo = _history(
        tmp_path / "repo",
        [
            (*ANN, "2021-01-01T00:00:00", {"a": 1}),
            (*ANN, "@253402300800 +0000", {"b": 1}),
        ],
    )
    for processes in (8, 1):
        dc = _collected(repo, monkeypatch, processes)
        assert dc.commits_by_year == {2021: 1, 9999: 1}
        assert dc.get_last_commit_date().year == 9999
        assert max(dc.files_by_stamp) == max(dc.changes_by_date) <= 253402300799


def test_a_commit_at_the_epoch_is_the_first(tmp_path, monkeypatch):
    """A stamp of 0 is a commit, not "no commit yet", whatever order it comes in."""
    repo = _history(
        tmp_path / "repo",
        [
            (*ANN, "2021-01-01T00:00:00 +0000", {"a": 1}),
            (*ANN, "@0 +0000", {"b": 1}),
        ],
    )
    dc = _collected(repo, monkeypatch)
    assert dc.first_commit_stamp == 0
    assert dc.authors["Ann"]["first_commit_stamp"] == 0


@pytest.mark.parametrize("processes", [8, 1])
def test_the_root_commit_counts_whatever_log_show_root_says(tmp_path, monkeypatch, processes):
    repo = _history(
        tmp_path / "repo",
        [
            (*ANN, "2021-01-01T00:00:00", {"a.py": 100}),
            (*ANN, "2021-01-02T00:00:00", {"b.py": 5}),
        ],
        **{"log.showRoot": "false"},
    )
    dc = _collected(repo, monkeypatch, processes)
    assert dc.total_lines_added == 105
    assert dc.authors["Ann"]["lines_added"] == 105
    assert dc.file_churn == {"a.py": 1, "b.py": 1}
    assert dc.source_lines_added == 105


def test_run_reports_the_time_spent_in_git(git_repo, tmp_path, caplog, sequential_map):
    with caplog.at_level(logging.INFO, logger="gitstats"):
        assert run([git_repo], str(tmp_path / "report")) == 0
    spent = re.search(r"secs, ([\d.]+) secs \(", caplog.text)
    assert spent and float(spent[1]) > 0


@pytest.mark.parametrize("port", ["0", "1", "8000", "65535"])
def test_port_takes_a_port(port):
    assert get_parser().parse_args(["--port", port, "repo"]).port == int(port)


@pytest.mark.parametrize("port", ["70000", "-1", "65536", "http"])
def test_port_refuses_what_is_not_a_port(port, capsys):
    with pytest.raises(SystemExit) as stopped:
        get_parser().parse_args(["--port", port, "repo"])
    assert stopped.value.code == 2
    assert "is not a port: give 1 to 65535, or 0 for a free one" in capsys.readouterr().err


@pytest.mark.parametrize(
    "setting, message",
    [
        ("processes=abc", "processes must be a whole number, not 'abc'"),
        ("ai_enabled=maybe", "ai_enabled must be true or false, not 'maybe'"),
    ],
)
def test_a_setting_of_the_wrong_type_on_the_command_line(setting, message, capsys):
    with (
        patch.object(sys, "argv", ["gitstats", "-c", setting, "repo"]),
        pytest.raises(SystemExit) as stopped,
    ):
        main()
    assert stopped.value.code == 2
    assert message in capsys.readouterr().err


def test_what_gitstats_conf_could_not_say_stops_the_run(capsys):
    import gitstats

    gitstats.config_errors.append("gitstats.conf: processes must be a whole number, not 'abc'")
    with (
        patch.object(sys, "argv", ["gitstats", "repo"]),
        patch("gitstats.main.run") as ran,
        pytest.raises(SystemExit) as stopped,
    ):
        main()
    assert stopped.value.code == 2
    assert "gitstats.conf: processes must be a whole number" in capsys.readouterr().err
    ran.assert_not_called()


def test_help_with_a_percent_sign_in_a_setting(capsys):
    _use_config(badge_label="100% done")
    import gitstats.main

    with patch.object(gitstats.main, "conf", {**gitstats.main.conf, "badge_label": "100% done"}):
        with pytest.raises(SystemExit):
            get_parser().parse_args(["--help"])
    assert "100% done" in capsys.readouterr().out
