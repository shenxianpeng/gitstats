"""Tests for gitstats.report_creator – HTML generation, helpers, chart rendering."""

import os
from io import StringIO

import pytest

from gitstats.report_creator import (
    HTMLReportCreator,
    ReportCreator,
    get_keys_sorted_by_value_key,
    get_keys_sorted_by_values,
    html_header,
    html_linkify,
)

# ── html_linkify ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Hello World", "hello_world"),
        ("Hello  World", "hello__world"),
        ("AB C", "ab_c"),
        ("single", "single"),
        ("", ""),
        ("Project Overview", "project_overview"),
    ],
)
def test_html_linkify(text, expected):
    assert html_linkify(text) == expected


# ── html_header ──────────────────────────────────────────────────────────


def test_html_header_basic():
    result = html_header(2, "Hello World")
    assert '<h2 id="hello_world">' in result
    assert 'href="#hello_world"' in result
    assert ">Hello World</a></h2>" in result
    assert result.startswith("\n")
    assert result.endswith("\n\n")


def test_html_header_level_3():
    result = html_header(3, "Foo Bar")
    assert '<h3 id="foo_bar">' in result


# ── get_keys_sorted_by_values ────────────────────────────────────────────


def test_get_keys_sorted_by_values_basic():
    d = {"a": 3, "b": 1, "c": 2}
    result = get_keys_sorted_by_values(d)
    assert result == ["b", "c", "a"]


def test_get_keys_sorted_by_values_empty():
    assert get_keys_sorted_by_values({}) == []


def test_get_keys_sorted_by_values_single():
    assert get_keys_sorted_by_values({"x": 5}) == ["x"]


def test_get_keys_sorted_by_values_same_value():
    d = {"a": 1, "b": 1, "c": 1}
    result = get_keys_sorted_by_values(d)
    assert set(result) == {"a", "b", "c"}
    assert len(result) == 3


# ── get_keys_sorted_by_value_key ─────────────────────────────────────────


def test_get_keys_sorted_by_value_key_basic():
    d = {
        "alice": {"commits": 10, "lines": 100},
        "bob": {"commits": 5, "lines": 200},
        "carol": {"commits": 20, "lines": 50},
    }
    result = get_keys_sorted_by_value_key(d, "commits")
    assert result == ["bob", "alice", "carol"]


def test_get_keys_sorted_by_value_key_empty():
    assert get_keys_sorted_by_value_key({}, "commits") == []


# ── HTMLReportCreator._heat_level ────────────────────────────────────────


@pytest.mark.parametrize(
    "value,max_value,expected",
    [
        (0, 100, 0),
        (10, 100, 1),
        (30, 100, 2),
        (60, 100, 3),
        (80, 100, 4),
        (100, 100, 4),
        (0, 0, 0),
        (-1, 100, 0),
    ],
)
def test_heat_level(value, max_value, expected):
    assert HTMLReportCreator._heat_level(value, max_value) == expected


def test_heat_level_boundary():
    """Test exact boundary values."""
    assert HTMLReportCreator._heat_level(25, 100) == 1
    assert HTMLReportCreator._heat_level(26, 100) == 2
    assert HTMLReportCreator._heat_level(50, 100) == 2
    assert HTMLReportCreator._heat_level(51, 100) == 3
    assert HTMLReportCreator._heat_level(75, 100) == 3
    assert HTMLReportCreator._heat_level(76, 100) == 4


# ── HTMLReportCreator._heat_td_class ─────────────────────────────────────


def test_heat_td_class():
    assert HTMLReportCreator._heat_td_class(30, 100) == "heat heat2"
    assert HTMLReportCreator._heat_td_class(0, 0) == "heat heat0"


# ── HTMLReportCreator._render_chartjs ────────────────────────────────────


def test_render_chartjs_single_dataset():
    creator = HTMLReportCreator()
    result = creator._render_chartjs(
        "chart-test",
        "bar",
        ["A", "B", "C"],
        [{"label": "Commits", "data": [1, 2, 3]}],
    )
    assert '<canvas id="chart-test">' in result
    assert "type: 'bar'" in result
    # Labels should be JSON-encoded
    assert '"A"' in result
    assert '"B"' in result
    # CSS var placeholder replaced with JS call
    assert "__CSS_BAR_COLOR__" not in result
    assert "getCSSVar('--bar-color')" in result
    # Single dataset: no legend, no borderColor in JS
    assert "legend: { display: false }" in result
    # Y-axis title
    assert "'Commits'" in result


def test_render_chartjs_multi_dataset():
    creator = HTMLReportCreator()
    result = creator._render_chartjs(
        "chart-multi",
        "line",
        ["X", "Y"],
        [
            {"label": "Alice", "data": [10, 20]},
            {"label": "Bob", "data": [5, 15]},
        ],
    )
    # Multiple datasets: legend displayed
    assert "legend: { display: true }" in result
    # Colors should be assigned
    assert "#5b8dee" in result
    assert "#1a7f37" in result
    # Line-specific properties
    assert "borderWidth" in result
    assert "pointRadius" in result


def test_render_chartjs_x_ticks_rotate():
    creator = HTMLReportCreator()
    result = creator._render_chartjs(
        "chart-rotate",
        "bar",
        ["looooooooong label"],
        [{"label": "C", "data": [1]}],
        x_ticks_rotate=True,
    )
    assert "maxRotation: 45" in result
    assert "minRotation: 45" in result


def test_render_chartjs_aspect_ratio():
    creator = HTMLReportCreator()
    result = creator._render_chartjs(
        "chart-ar",
        "bar",
        ["X"],
        [{"label": "C", "data": [1]}],
        aspect_ratio=5,
    )
    assert "aspectRatio: 5" in result


def test_render_chartjs_max_bar_thickness():
    creator = HTMLReportCreator()
    result = creator._render_chartjs(
        "chart-thick",
        "bar",
        ["X"],
        [{"label": "C", "data": [1]}],
        max_bar_thickness=40,
    )
    assert "maxBarThickness: 40" in result


def test_render_chartjs_no_max_bar_thickness():
    creator = HTMLReportCreator()
    result = creator._render_chartjs(
        "chart-nothick",
        "bar",
        ["X"],
        [{"label": "C", "data": [1]}],
    )
    assert "maxBarThickness" not in result


def test_render_chartjs_xss_protection():
    """Ensure </script> is escaped in labels/ datasets to prevent XSS."""
    creator = HTMLReportCreator()
    result = creator._render_chartjs(
        "chart-xss",
        "bar",
        ["</script><script>alert(1)"],
        [{"label": "</script>", "data": [1]}],
    )
    assert "</script>" not in result.replace("</script>", "")


def test_render_chartjs_y_label():
    creator = HTMLReportCreator()
    result = creator._render_chartjs(
        "chart-yl",
        "bar",
        ["X"],
        [{"label": "C", "data": [1]}],
        y_label="Lines of Code",
    )
    assert "title: { display: true, text: 'Lines of Code' }" in result


# ── HTMLReportCreator.print_header ───────────────────────────────────────


def test_print_header():
    creator = HTMLReportCreator()
    creator.title = "my-project"
    f = StringIO()
    creator.print_header(f)
    output = f.getvalue()

    assert "<!DOCTYPE html>" in output
    assert "my-project" in output
    assert "chart.umd.min.js" in output
    assert "sortable.js" in output
    assert "data-theme" in output
    assert "toggleTheme" in output
    assert "<body>" in output


# ── HTMLReportCreator.print_nav ──────────────────────────────────────────


def test_print_nav_without_ai():
    from unittest.mock import Mock

    creator = HTMLReportCreator()
    creator.data = Mock()
    creator.data.ai_summaries = {}

    f = StringIO()
    creator.print_nav(f)
    output = f.getvalue()

    assert '<a href="index.html">General</a>' in output
    assert '<a href="activity.html">Activity</a>' in output
    assert '<a href="authors.html">Authors</a>' in output
    assert '<a href="files.html">Files</a>' in output
    assert '<a href="lines.html">Lines</a>' in output
    assert '<a href="tags.html">Tags</a>' in output
    assert "AI Insights" not in output


def test_print_nav_with_ai():
    from unittest.mock import Mock

    creator = HTMLReportCreator()
    creator.data = Mock()
    creator.data.ai_summaries = {"index": {"summary": "test"}}

    f = StringIO()
    creator.print_nav(f)
    output = f.getvalue()

    assert "AI Insights" in output
    assert 'href="ai-insights.html"' in output


def test_print_nav_has_github_link():
    from unittest.mock import Mock

    creator = HTMLReportCreator()
    creator.data = Mock()
    creator.data.ai_summaries = {}

    f = StringIO()
    creator.print_nav(f)
    output = f.getvalue()

    assert "github.com" in output
    assert "theme-toggle" in output


# ── HTMLReportCreator.create_index_html ──────────────────────────────────


def test_create_index_html(mock_data_collector, temp_dir):
    creator = HTMLReportCreator()
    creator.title = mock_data_collector.project_name
    creator.data = mock_data_collector
    creator.create_index_html(mock_data_collector, temp_dir)

    with open(f"{temp_dir}/index.html", encoding="utf-8") as f:
        html = f.read()

    assert "<h1>General</h1>" in html
    assert "test-project" in html
    assert "Total Files" in html
    assert "Total Commits" in html
    assert "Authors" in html
    assert "</html>" in html


# ── HTMLReportCreator.create_activity_html ───────────────────────────────


def test_create_activity_html(mock_data_collector, temp_dir):
    creator = HTMLReportCreator()
    creator.title = mock_data_collector.project_name
    creator.data = mock_data_collector
    creator.create_activity_html(mock_data_collector, temp_dir)

    with open(f"{temp_dir}/activity.html", encoding="utf-8") as f:
        html = f.read()

    assert "<h1>Activity</h1>" in html
    assert "Hour of Day" in html
    assert "Day of Week" in html
    assert "Hour of Week" in html
    assert "Month of Year" in html
    assert "Commits by year/month" in html
    # Should contain chart.js canvases
    assert '<canvas id="chart-hour-of-day">' in html
    assert '<canvas id="chart-day-of-week">' in html


# ── HTMLReportCreator.create_authors_html ────────────────────────────────


def test_create_authors_html(mock_data_collector, temp_dir):
    creator = HTMLReportCreator()
    creator.title = mock_data_collector.project_name
    creator.data = mock_data_collector
    creator.create_authors_html(mock_data_collector, temp_dir)

    with open(f"{temp_dir}/authors.html", encoding="utf-8") as f:
        html = f.read()

    assert "<h1>Authors</h1>" in html
    assert "Alice Smith" in html
    assert "Bob Jones" in html
    assert "Author of Month" in html
    assert "Author of Year" in html
    assert "Domains" in html
    assert "example.com" in html
    assert "Contributor Growth" in html


# ── HTMLReportCreator.create_files_html ──────────────────────────────────


def test_create_files_html(mock_data_collector, temp_dir):
    creator = HTMLReportCreator()
    creator.title = mock_data_collector.project_name
    creator.data = mock_data_collector
    creator.create_files_html(mock_data_collector, temp_dir)

    with open(f"{temp_dir}/files.html", encoding="utf-8") as f:
        html = f.read()

    assert "<h1>Files</h1>" in html
    assert "Total files" in html
    assert "Extensions" in html
    assert "py" in html
    assert "md" in html
    assert "Most Changed Files" in html
    assert "main.py" in html
    assert "utils.py" in html


# ── HTMLReportCreator.create_lines_html ──────────────────────────────────


def test_create_lines_html(mock_data_collector, temp_dir):
    creator = HTMLReportCreator()
    creator.title = mock_data_collector.project_name
    creator.data = mock_data_collector
    creator.create_lines_html(mock_data_collector, temp_dir)

    with open(f"{temp_dir}/lines.html", encoding="utf-8") as f:
        html = f.read()

    assert "<h1>Lines</h1>" in html
    assert "Total lines" in html


# ── HTMLReportCreator.create_tags_html ───────────────────────────────────


def test_create_tags_html(mock_data_collector, temp_dir):
    creator = HTMLReportCreator()
    creator.title = mock_data_collector.project_name
    creator.data = mock_data_collector
    creator.create_tags_html(mock_data_collector, temp_dir)

    with open(f"{temp_dir}/tags.html", encoding="utf-8") as f:
        html = f.read()

    assert "<h1>Tags</h1>" in html
    assert "v1.0.0" in html
    assert "v1.1.0" in html
    assert "Alice Smith" in html


# ── HTMLReportCreator.create_ai_insights_html ────────────────────────────


def test_create_ai_insights(mock_data_collector_with_ai, temp_dir):
    creator = HTMLReportCreator()
    creator.title = mock_data_collector_with_ai.project_name
    creator.data = mock_data_collector_with_ai
    creator.create_ai_insights_html(mock_data_collector_with_ai, temp_dir)

    with open(f"{temp_dir}/ai-insights.html", encoding="utf-8") as f:
        html = f.read()

    assert "AI-Powered Insights" in html
    assert "healthy and active" in html  # summary content
    assert "About AI Insights" in html
    assert "dependabot" in html  # bot note


def test_create_ai_insights_with_error(mock_data_collector_with_ai_error, temp_dir):
    creator = HTMLReportCreator()
    creator.title = mock_data_collector_with_ai_error.project_name
    creator.data = mock_data_collector_with_ai_error
    creator.create_ai_insights_html(mock_data_collector_with_ai_error, temp_dir)

    with open(f"{temp_dir}/ai-insights.html", encoding="utf-8") as f:
        html = f.read()

    assert "Analysis Unavailable" in html
    assert "API rate limit exceeded" in html


def test_create_ai_insights_no_ai_data(mock_data_collector, temp_dir):
    creator = HTMLReportCreator()
    creator.title = mock_data_collector.project_name
    creator.data = mock_data_collector

    # Should not crash even with empty ai_summaries
    creator.create_ai_insights_html(mock_data_collector, temp_dir)
    # File should exist but have limited content
    with open(f"{temp_dir}/ai-insights.html", encoding="utf-8") as f:
        html = f.read()
    assert "No analysis" in html or "AI-Powered Insights" in html


# ── HTMLReportCreator.get_ai_summary_html ────────────────────────────────


def test_get_ai_summary_html_with_data(mock_data_collector_with_ai):
    creator = HTMLReportCreator()
    creator.data = mock_data_collector_with_ai
    result = creator.get_ai_summary_html("index")
    assert "healthy and active" in result
    assert "AI-Powered Insights" in result


def test_get_ai_summary_html_no_data(mock_data_collector):
    creator = HTMLReportCreator()
    creator.data = mock_data_collector
    result = creator.get_ai_summary_html("index")
    assert result == ""


def test_get_ai_summary_html_error(mock_data_collector_with_ai_error):
    creator = HTMLReportCreator()
    creator.data = mock_data_collector_with_ai_error
    result = creator.get_ai_summary_html("index")
    assert "API rate limit exceeded" in result
    assert "unavailable" in result.lower()


def test_get_ai_summary_html_missing_key(mock_data_collector_with_ai):
    creator = HTMLReportCreator()
    creator.data = mock_data_collector_with_ai
    result = creator.get_ai_summary_html("nonexistent")
    assert result == ""


# ── HTMLReportCreator._build_author_time_series ──────────────────────────


def test_build_author_time_series_empty(mock_data_collector):
    creator = HTMLReportCreator()
    creator.data = mock_data_collector
    # With empty changes_by_date_by_author, should return empty
    mock_data_collector.changes_by_date_by_author = {}
    labels, loc_ds, _ = creator._build_author_time_series(mock_data_collector)
    assert labels == []
    # Even with no time-series data, datasets have entries per author with empty data
    assert len(loc_ds) == len(mock_data_collector.get_authors(20))
    for ds in loc_ds:
        assert ds["data"] == []


def test_build_author_time_series_basic(mock_data_collector):
    creator = HTMLReportCreator()
    creator.data = mock_data_collector

    stamp = 1670000000
    mock_data_collector.changes_by_date_by_author = {
        stamp: {
            "Alice Smith": {"lines_added": 100, "commits": 5},
        },
        stamp + 86400: {
            "Alice Smith": {"lines_added": 200, "commits": 12},
            "Bob Jones": {"lines_added": 50, "commits": 3},
        },
    }

    labels, loc_ds, _ = creator._build_author_time_series(mock_data_collector)

    assert len(labels) == 2
    assert any("Alice Smith" in str(ds) for ds in loc_ds)
    # Each author dataset should have 2 data points
    for ds in loc_ds:
        assert len(ds["data"]) == 2


# ── ReportCreator base class ─────────────────────────────────────────────


def test_report_creator_base():
    rc = ReportCreator()
    assert rc.data is None
    assert rc.path is None

    class MockData:
        pass

    rc.create(MockData(), "/tmp")
    assert rc.data is not None
    assert rc.path == "/tmp"


# ── HTMLReportCreator.create (integration of all pages) ──────────────────


def test_create_all_pages(mock_data_collector, temp_dir):
    creator = HTMLReportCreator()
    creator.create(mock_data_collector, temp_dir)

    expected_files = [
        "index.html",
        "activity.html",
        "authors.html",
        "files.html",
        "lines.html",
        "tags.html",
        "collaboration.html",
    ]
    for fname in expected_files:
        path = f"{temp_dir}/{fname}"
        assert os.path.exists(path), f"Missing: {fname}"
        with open(path, encoding="utf-8") as f:
            content = f.read()
            assert "</html>" in content

    # AI insights page should NOT be created when ai_summaries is empty
    assert not os.path.exists(f"{temp_dir}/ai-insights.html")


def test_create_all_pages_with_ai(mock_data_collector_with_ai, temp_dir):
    creator = HTMLReportCreator()
    creator.create(mock_data_collector_with_ai, temp_dir)

    assert os.path.exists(f"{temp_dir}/ai-insights.html")


def test_create_copies_static_files(mock_data_collector, temp_dir):
    creator = HTMLReportCreator()
    creator.create(mock_data_collector, temp_dir)

    for fname in ("sortable.js", "chart.umd.min.js", "gitstats.css", "collaboration.js"):
        assert os.path.exists(f"{temp_dir}/{fname}"), f"Missing static file: {fname}"
