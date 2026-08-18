"""Tests for gitstats.main – DataCollector, parameter parsing, and integration with real git repos."""

import datetime
import os
from unittest.mock import patch

import pytest

from gitstats.main import (
    DataCollector,
    GitDataCollector,
    _make_server,
    _server_urls,
    get_parser,
    main,
    parallel_map_with_fallback,
    run,
)

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
        assert not any(e.is_dir() for e in os.scandir(output) if e.name != ".ai_cache")

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
        assert "Totals" in index
        # Per-repo pages must not leak into the output root
        assert not os.path.exists(f"{output}/activity.html")

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
        assert "Failed Repositories" in index
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
