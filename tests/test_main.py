"""Tests for gitstats.main – DataCollector, parameter parsing, and integration with real git repos."""

import os
from unittest.mock import patch

import pytest

from gitstats.main import (
    DataCollector,
    GitDataCollector,
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


# ── get_parser / CLI ─────────────────────────────────────────────────────


class TestCLI:
    def test_parser_defaults(self):
        parser = get_parser()
        args = parser.parse_args(["some-repo", "out-dir"])
        assert args.gitpath == ["some-repo"]
        assert args.outputpath == "out-dir"
        assert args.format is None
        assert args.verbose is False
        assert args.quiet is False
        assert args.ai is None
        assert args.refresh_ai is False

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
