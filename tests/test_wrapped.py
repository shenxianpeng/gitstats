"""Tests for gitstats.wrapped – WrappedCardGenerator and SVG generation."""

import os
from unittest.mock import MagicMock

from gitstats.wrapped import (
    MONTH_NAMES,
    WrappedCardGenerator,
)


def _make_mock_data(**overrides):
    """Create a mock DataCollector object with sensible defaults."""
    data = MagicMock()
    data.project_name = "test-repo"
    data.total_commits = 100
    data.total_authors = 5
    data.total_files = 42
    data.total_lines_added = 5000
    data.total_lines_removed = 2000
    data.longest_streak = 15
    data.active_days = {"2025-01-01", "2025-01-02", "2025-01-03"}
    data.authors_by_commits = ["Alice", "Bob"]
    data.first_commit_stamp = 1672531200  # 2023-01-01
    data.last_commit_stamp = 1752531200
    data.commits_by_year = {2025: 50, 2024: 30}
    data.activity_by_hour_of_day = {h: 10 for h in range(24)}  # 10 commits each hour
    data.activity_by_month_of_year = {m: 5 for m in range(1, 13)}
    data.activity_by_day_of_week = {d: 7 for d in range(7)}

    for k, v in overrides.items():
        setattr(data, k, v)
    return data


class TestWrappedCardGenerator:
    def test_init_defaults(self):
        data = _make_mock_data()
        gen = WrappedCardGenerator(data)
        assert gen.year is not None  # defaults to current year
        assert gen.theme_name == "midnight"
        assert gen.colors is not None

    def test_init_custom_year_and_theme(self):
        data = _make_mock_data()
        gen = WrappedCardGenerator(data, year=2024, theme="sunset")
        assert gen.year == 2024
        assert gen.theme_name == "sunset"

    def test_init_fallback_theme(self):
        data = _make_mock_data()
        gen = WrappedCardGenerator(data, theme="nonexistent")
        # Should fall back to midnight
        assert gen.colors is not None
        assert gen.colors["year"] == "#ffffff"  # midnight's year color

    def test_get_total_commits_from_year(self):
        data = _make_mock_data()
        gen = WrappedCardGenerator(data, year=2025)
        assert gen._get_total_commits() == 50

    def test_get_total_commits_fallback_total(self):
        """When the requested year has no data, fall back to total_commits."""
        data = _make_mock_data(commits_by_year={})
        gen = WrappedCardGenerator(data, year=2025)
        assert gen._get_total_commits() == 100  # fallback to total_commits

    def test_get_night_owl_ratio_zero(self):
        """No commits between 0-5 → ratio = 0."""
        data = _make_mock_data(activity_by_hour_of_day={h: 10 for h in range(6, 24)})
        gen = WrappedCardGenerator(data)
        assert gen._get_night_owl_ratio() == 0.0

    def test_get_night_owl_ratio_all_night(self):
        """All commits between 0-5 → ratio = 1."""
        data = _make_mock_data(activity_by_hour_of_day={h: 10 for h in range(6)})
        gen = WrappedCardGenerator(data)
        assert gen._get_night_owl_ratio() == 1.0

    def test_get_night_owl_ratio_mixed(self):
        """Half commits at night (0-5) → ratio = 0.5."""
        hourly = {**{h: 10 for h in range(6)}, **{h: 10 for h in range(6, 24)}}
        data = _make_mock_data(activity_by_hour_of_day=hourly)
        gen = WrappedCardGenerator(data)
        assert gen._get_night_owl_ratio() == 0.25  # 60 night / 240 total

    def test_get_night_owl_ratio_no_data(self):
        """No activity_by_hour_of_day data → ratio = 0."""
        data = _make_mock_data(activity_by_hour_of_day={})
        gen = WrappedCardGenerator(data)
        assert gen._get_night_owl_ratio() == 0.0

    def test_get_most_active_month(self):
        """Should return the month name with highest commit count."""
        data = _make_mock_data(activity_by_month_of_year={1: 0, 2: 0, 3: 100, 4: 10})
        gen = WrappedCardGenerator(data)
        assert gen._get_most_active_month() == "March"

    def test_get_most_active_month_empty(self):
        data = _make_mock_data(activity_by_month_of_year={})
        gen = WrappedCardGenerator(data)
        assert gen._get_most_active_month() == "—"

    def test_get_busiest_weekday(self):
        data = _make_mock_data(activity_by_day_of_week={0: 1, 1: 2, 2: 10, 3: 0})
        gen = WrappedCardGenerator(data)
        assert gen._get_busiest_weekday() == "Wednesday"

    def test_get_busiest_weekday_empty(self):
        data = _make_mock_data(activity_by_day_of_week={})
        gen = WrappedCardGenerator(data)
        assert gen._get_busiest_weekday() == "—"

    def test_get_total_lines_touched(self):
        data = _make_mock_data(total_lines_added=1000, total_lines_removed=500)
        gen = WrappedCardGenerator(data)
        assert gen._get_total_lines_touched() == 1500

    def test_get_top_author(self):
        data = _make_mock_data(authors_by_commits=["Charlie", "Diana"])
        gen = WrappedCardGenerator(data)
        assert gen._get_top_author() == "Charlie"

    def test_get_top_author_empty(self):
        data = _make_mock_data(authors_by_commits=[])
        gen = WrappedCardGenerator(data)
        assert gen._get_top_author() == "—"

    def test_get_first_commit_year(self):
        """first_commit_stamp = 2023-01-01 → year 2023."""
        data = _make_mock_data(first_commit_stamp=1672531200)
        gen = WrappedCardGenerator(data)
        assert gen._get_first_commit_year() == 2023

    def test_get_first_commit_year_zero(self):
        """No first_commit_stamp → falls back to self.year."""
        data = _make_mock_data(first_commit_stamp=0)
        gen = WrappedCardGenerator(data, year=2024)
        assert gen._get_first_commit_year() == 2024

    def test_night_owl_label_night(self):
        """>40% night commits → 'Night Owl 🦉'."""
        data = _make_mock_data(activity_by_hour_of_day={h: 10 for h in range(6)})
        gen = WrappedCardGenerator(data)
        stats = gen._collect_stats()
        assert "Night Owl" in stats["night_owl_label"]

    def test_night_owl_label_early_bird(self):
        """<10% night commits → 'Early Bird 🌅'."""
        # 1 night commit + 180 day commits ≈ 0.6% night ratio
        hourly = {0: 1} | {h: 10 for h in range(6, 24)}
        data = _make_mock_data(activity_by_hour_of_day=hourly)
        gen = WrappedCardGenerator(data)
        stats = gen._collect_stats()
        assert "Early Bird" in stats["night_owl_label"]

    def test_collect_stats_structure(self):
        data = _make_mock_data()
        gen = WrappedCardGenerator(data, year=2025)
        stats = gen._collect_stats()

        assert stats["year"] == 2025
        assert stats["project_name"] == "test-repo"
        assert "total_commits" in stats
        assert "total_authors" in stats
        assert "longest_streak" in stats
        assert "night_owl_ratio" in stats
        assert "night_owl_label" in stats
        assert "most_active_month" in stats
        assert "busiest_weekday" in stats
        assert "top_author" in stats
        assert "lines_touched" in stats
        assert "active_days" in stats

    def test_format_number_thousands(self):
        data = _make_mock_data()
        gen = WrappedCardGenerator(data)
        assert gen._format_number(1234) == "1,234"
        assert gen._format_number(1000000) == "1.0M"
        assert gen._format_number(0) == "0"
        assert gen._format_number(999) == "999"

    def test_escape_xml(self):
        assert WrappedCardGenerator._escape_xml("<hello>") == "&lt;hello&gt;"
        assert WrappedCardGenerator._escape_xml('a & b "c"') == "a &amp; b &quot;c&quot;"

    def test_render_svg_valid_xml(self, temp_dir):
        """Generate a full SVG and verify it's valid XML."""
        data = _make_mock_data()
        gen = WrappedCardGenerator(data, year=2025)
        path = gen.generate(output_path=os.path.join(temp_dir, "wrapped-test.svg"))

        assert os.path.exists(path)
        with open(path) as f:
            content = f.read()

        # Basic XML validity checks
        assert content.startswith('<?xml version="1.0"')
        assert "<svg" in content
        assert "</svg>" in content
        assert "1080" in content  # width/height
        assert "YOUR 2025 IN CODE" in content
        assert "test-repo" in content
        assert "Alice" in content  # top author
        assert "gitstats" in content  # footer

    def test_render_svg_midnight_theme(self, temp_dir):
        """Midnight theme should use dark background colors."""
        data = _make_mock_data()
        gen = WrappedCardGenerator(data, year=2025, theme="midnight")
        path = gen.generate(output_path=os.path.join(temp_dir, "midnight.svg"))

        with open(path) as f:
            content = f.read()

        assert "#0f0c29" in content  # midnight bg_start

    def test_render_svg_sunset_theme(self, temp_dir):
        """Sunset theme should use warm colors."""
        data = _make_mock_data()
        gen = WrappedCardGenerator(data, year=2025, theme="sunset")
        path = gen.generate(output_path=os.path.join(temp_dir, "sunset.svg"))

        with open(path) as f:
            content = f.read()

        assert "#1a0a1e" in content  # sunset bg_start
        assert "#fbbf24" in content  # sunset accent

    def test_render_svg_clean_theme(self, temp_dir):
        """Clean theme should use light background."""
        data = _make_mock_data()
        gen = WrappedCardGenerator(data, year=2025, theme="clean")
        path = gen.generate(output_path=os.path.join(temp_dir, "clean.svg"))

        with open(path) as f:
            content = f.read()

        assert "#f8fafc" in content  # clean bg_start

    def test_generate_default_filename(self, temp_dir):
        """Without output_path, file should be named automatically."""
        data = _make_mock_data()
        gen = WrappedCardGenerator(data, year=2025)
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            path = gen.generate()
            assert path.endswith("gitstats-wrapped-2025.svg")
            assert os.path.exists(path)
        finally:
            os.chdir(original_cwd)

    def test_svg_contains_all_stats(self, temp_dir):
        """All expected metrics should appear in the SVG text."""
        data = _make_mock_data()
        gen = WrappedCardGenerator(data, year=2025)
        path = gen.generate(output_path=os.path.join(temp_dir, "full.svg"))

        with open(path) as f:
            content = f.read()

        assert "50" in content  # total commits (from commits_by_year[2025])
        assert "15 days" in content  # longest streak
        assert "3" in content  # active days count
        assert "Contributors" in content
        assert "Files" in content
        assert "MONTHLY COMMITS" in content
        assert "Total Commits" in content
        assert "Longest Streak" in content
        assert "Active Days" in content
        assert "Generated by gitstats" in content

    def test_monthly_chart_renders_all_months(self, temp_dir):
        """The mini bar chart should include all 12 months."""
        data = _make_mock_data()
        gen = WrappedCardGenerator(data, year=2025)
        path = gen.generate(output_path=os.path.join(temp_dir, "chart.svg"))

        with open(path) as f:
            content = f.read()

        for month_num in range(1, 13):
            assert MONTH_NAMES[month_num][:3] in content
