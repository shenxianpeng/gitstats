"""Unit tests for health dashboard metrics."""

from gitstats.main import _classify_commit_type, _get_hot_file_threshold


class TestCommitTypeDetection:
    def test_fix_conventional(self):
        assert _classify_commit_type("fix: resolve crash") == "fix"

    def test_fix_case_insensitive(self):
        assert _classify_commit_type("Fix a bug in parser") == "fix"

    def test_feat_conventional(self):
        assert _classify_commit_type("feat: add new chart") == "feat"

    def test_fix_chinese_keyword(self):
        assert _classify_commit_type("修复登录问题") == "fix"

    def test_feat_chinese_keyword(self):
        assert _classify_commit_type("新增用户功能") == "feat"

    def test_revert_highest_priority(self):
        assert _classify_commit_type("Revert 'feat: add login'") == "revert"

    def test_fix_beats_refactor(self):
        assert _classify_commit_type("fix: refactor auth loop") == "fix"

    def test_other_fallback(self):
        assert _classify_commit_type("random message") == "other"


class TestHotFileThreshold:
    def test_small_repo_min_floor(self):
        # 3 files < min(5), threshold = 3
        assert _get_hot_file_threshold(3) == 3

    def test_small_repo_20_percent(self):
        # 20 files → max(5, int(20*0.20)) = max(5, 4) = 5
        assert _get_hot_file_threshold(20) == 5

    def test_medium_repo_10_percent(self):
        # 100 files → max(5, int(100*0.10)) = max(5, 10) = 10
        assert _get_hot_file_threshold(100) == 10

    def test_large_repo_5_percent(self):
        # 600 files → max(5, int(600*0.05)) = max(5, 30) = 30
        assert _get_hot_file_threshold(600) == 30

    def test_threshold_never_exceeds_total(self):
        # For any count, threshold <= count
        for n in [1, 3, 5, 10, 50, 100, 500, 1000]:
            assert _get_hot_file_threshold(n) <= n


class TestHealthScoreCalculation:
    """Test health score via DataCollector.refine() with synthetic data."""

    def _make_data(self, **overrides):
        """Build a minimal DataCollector-like object for testing."""
        from gitstats.main import GitDataCollector

        data = object.__new__(GitDataCollector)
        # Minimal attributes needed by _calculate_health_score
        tc = overrides.get("total_commits", 100)
        data.total_commits = tc
        data.get_total_commits = lambda: tc
        data.commit_type_counts = overrides.get(
            "commit_type_counts",
            {"fix": 5, "feat": 30, "chore": 10, "docs": 5, "other": 50},
        )
        data.file_churn = overrides.get(
            "file_churn",
            {
                "a.py": (1000, 100),
                "b.py": (500, 50),
            },
        )
        data.file_authors = overrides.get(
            "file_authors",
            {
                "a.py": {"alice", "bob", "carol", "dave", "eve"},
                "b.py": {"alice", "bob"},
            },
        )
        data.file_commit_count = overrides.get(
            "file_commit_count",
            {
                "a.py": 40,
                "b.py": 20,
            },
        )
        data.health_score = 0
        return data

    def test_zero_commits_returns_50(self):
        data = self._make_data(total_commits=0)
        data.get_total_commits = lambda: 0
        data._calculate_health_score()
        assert data.health_score == 50

    def test_score_within_bounds(self):
        data = self._make_data()
        data._calculate_health_score()
        assert 0 <= data.health_score <= 100

    def test_high_bug_ratio_lowers_score(self):
        # 50% fix commits → bug_score = 0
        data_low = self._make_data(commit_type_counts={"fix": 50, "other": 50})
        data_low._calculate_health_score()
        data_ok = self._make_data(commit_type_counts={"fix": 5, "other": 95})
        data_ok._calculate_health_score()
        assert data_low.health_score < data_ok.health_score

    def test_zero_churn_no_division_error(self):
        data = self._make_data(file_churn={})
        data._calculate_health_score()  # should not raise
        assert 0 <= data.health_score <= 100
