"""Tests for gitstats.main – DataCollector, parameter parsing, and integration with real git repos."""

import datetime
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
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
            email_to_latest={"a@x.com": (400, "New Name")},
            author_to_email={"old name": "a@x.com", "New Name": "a@x.com"},
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

        mapping = dc._merge_author_aliases(
            email_to_latest={"a@x.com": (1, "Ann"), "b@x.com": (2, "Bo")},
            author_to_email={"Ann": "a@x.com", "Bo": "b@x.com"},
        )

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
        dc._collect_commit_stats = spy("commits", ({}, {}))
        dc._merge_author_aliases = spy("aliases", {})
        dc._collect_files_by_stamp = spy("files")
        dc._collect_extensions = spy("extensions")
        dc._collect_line_stats = spy("lines")
        dc._collect_per_author_line_stats = spy("author_lines")
        dc._collect_file_churn_and_ownership = spy("churn")

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
            "files",
            "extensions",
            "lines",
            "author_lines",
            "churn",
        ]


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
                'git log "c2"': "",  # no output: the tag is left out
                'git log "c1"': "garbage Ann",  # unreadable stamp: counted as 0
                'git log --format="%H %aN" "v1"': "c1 Ann\n\nc0 Outside Range",
            }
        )
        monkeypatch.setattr("gitstats.main.get_pipe_output", fake)
        dc = GitDataCollector()
        dc._collect_tags()

        assert set(dc.tags) == {"v1"}
        assert dc.tags["v1"]["stamp"] == 0
        # c0 is not in the analyzed range, so only c1 counts
        assert dc.tags["v1"]["commits"] == 1
        assert dc.tags["v1"]["authors"] == {"Ann": 1}

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
        email_to_latest, author_to_email = dc._collect_commit_stats()

        assert set(dc.authors) == {"Ann", "Bo"}
        assert dc.authors["Bo"]["first_commit_stamp"] == 0
        # an address without "@" has no domain
        assert dc.domains == {"example.com": {"commits": 1}, "?": {"commits": 1}}
        assert dc.commits_by_timezone == {"+0000": 1, "+0100": 1}
        assert author_to_email == {"Ann": "ann@example.com", "Bo": "bo-at-nowhere"}
        assert email_to_latest["ann@example.com"] == (1700000000, "Ann")

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
            email_to_latest={"n@x.com": (90, "Nick"), "a@x.com": (50, "Ann")},
            author_to_email={"Old Nick": "n@x.com", "Ann": "a@x.com", "ann (laptop)": "a@x.com"},
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
        dc._merge_author_aliases(
            email_to_latest={"a@x.com": (300, "Ann")},
            author_to_email={"Ann": "a@x.com", "ann": "a@x.com"},
        )
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

        # forget one revision: only that one is read from git again
        second = GitDataCollector()
        second.cache = json.loads(json.dumps(first.cache))
        forgotten = sorted(second.cache["files_in_tree"])[0]
        del second.cache["files_in_tree"][forgotten]
        from gitstats.utils import get_num_of_files_from_rev

        with patch(
            "gitstats.main.get_num_of_files_from_rev", side_effect=get_num_of_files_from_rev
        ) as read:
            second._collect_files_by_stamp()

        assert [call.args[0][1] for call in read.call_args_list] == [forgotten]
        assert second.cache["files_in_tree"] == first.cache["files_in_tree"]
        assert second.files_by_stamp == first.files_by_stamp
        # files in the tree after each of the five commits
        assert sorted(second.files_by_stamp.values()) == [2, 3, 3, 4, 5]
        assert second.total_commits == 5

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
        # the five blobs with an extension were read and added to the cache
        assert len(dc.cache["lines_in_blob"]) == 6

    def test_line_stats_without_linear_history_and_with_stray_lines(self, monkeypatch, caplog):
        _use_config(linear_linestats=0)
        # git prints newest first; the collector reads the lines oldest first
        fake = _fake_git(
            {
                "git log --shortstat": (
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
        assert dc.total_lines == 5
        assert dc.total_lines_added == 5
        assert 'Unexpected line "stray"' in caplog.text
        assert 'Unexpected line "not-a-stamp Bo"' in caplog.text
        assert "Failed to handle line" in caplog.text

    def test_per_author_line_stats_add_unknown_authors(self, monkeypatch, caplog):
        fake = _fake_git(
            {
                "git log --shortstat --date-order": (
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
                'git log --format="COMMIT:%aN"': (
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
        assert "YOUR 2023 IN CODE" in card
        assert "git_repo_minimal" in card
        assert THEMES["clean"]["bg_start"] in card
        assert "Wrapped card saved: " in caplog.text
        # the report itself is unchanged by the card
        assert (out / "index.html").exists()

    def test_names_the_card_after_the_current_year_by_default(
        self, git_repo_minimal, tmp_path, sequential_map
    ):
        out = tmp_path / "report"
        _run_single_repo(git_repo_minimal, str(out), wrapped_config=self._config(year=None))
        assert (out / f"wrapped-{datetime.datetime.now().year}.svg").exists()

    def test_writes_the_card_where_asked(self, git_repo_minimal, tmp_path, sequential_map):
        out = tmp_path / "report"
        cards = tmp_path / "cards"
        cards.mkdir()
        _run_single_repo(
            git_repo_minimal,
            str(out),
            wrapped_config=self._config(output=str(cards / "2023.svg")),
        )
        assert "YOUR 2023 IN CODE" in (cards / "2023.svg").read_text(encoding="utf-8")
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
