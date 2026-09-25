"""Tests for gitstats.report_creator – HTML generation, helpers, chart rendering."""

import os
import re
from io import StringIO

import pytest

import gitstats.report_creator
from gitstats.report_creator import (
    FONT_FILES,
    HTMLReportCreator,
    ReportCreator,
    _classify_eras,
    compute_code_ownership,
    compute_project_history,
    get_keys_sorted_by_value_key,
    get_keys_sorted_by_values,
    html_header,
    html_linkify,
    month_range,
    parse_chronicle,
    stat_tiles_html,
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
    # The ratio sizes the CSS box; Chart.js fills it so the box's min-height
    # can keep charts readable on phones
    assert '<div class="chart-box" style="--chart-ratio: 5">' in result
    assert "maintainAspectRatio: false" in result
    assert "aspectRatio:" not in result


def test_render_chartjs_legend_box_class():
    creator = HTMLReportCreator()
    multi = creator._render_chartjs(
        "chart-legend",
        "line",
        ["X"],
        [{"label": "A", "data": [1]}, {"label": "B", "data": [2]}],
    )
    single = creator._render_chartjs("chart-single", "bar", ["X"], [{"label": "C", "data": [1]}])
    assert 'class="chart-box has-legend"' in multi
    assert "has-legend" not in single


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


def test_render_chartjs_category_axis_by_default():
    creator = HTMLReportCreator()
    result = creator._render_chartjs("chart-cat", "line", ["X"], [{"label": "C", "data": [1]}])
    assert "timeAxis(" not in result
    assert "stepped" not in result


def test_render_chartjs_time_axis():
    creator = HTMLReportCreator()
    result = creator._render_chartjs(
        "chart-time",
        "line",
        [1_000_000_000, 1_700_000_000],
        [{"label": "Lines", "data": [10, 20]}],
        time_axis=True,
    )
    # Unix seconds become JS milliseconds on a linear x-axis
    assert "var labels = [1000000000000, 1700000000000];" in result
    assert "x: timeAxis(labels)" in result
    assert "x: xs[i], y: y" in result
    # Cumulative series hold their value until the next point
    assert '"stepped": true' in result
    assert "formatChartDate(items[0].parsed.x)" in result


def test_render_chartjs_single_dataset_follows_theme():
    creator = HTMLReportCreator()
    result = creator._render_chartjs("chart-th", "bar", ["X"], [{"label": "C", "data": [1]}])
    assert '"themed": true' in result
    assert "applyChartTheme();" in result


# ── month_range ──────────────────────────────────────────────────────────


def test_month_range_fills_gaps():
    assert month_range(["2015-11", "2016-02"]) == ["2015-11", "2015-12", "2016-01", "2016-02"]


def test_month_range_unsorted_input():
    assert month_range({"2024-03": 1, "2024-01": 2}) == ["2024-01", "2024-02", "2024-03"]


def test_month_range_empty():
    assert month_range([]) == []


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


def test_print_header_theme_defaults_to_system_preference():
    creator = HTMLReportCreator()
    creator.title = "p"
    f = StringIO()
    creator.print_header(f)
    output = f.getvalue()

    assert "prefers-color-scheme: dark" in output
    # On narrow screens the nav scrolls sideways to the current page
    assert "revealCurrentNavItem();" in output
    # Switching themes notifies the charts so they can recolor
    assert "dispatchEvent(new Event('themechange'))" in output
    assert "addEventListener('themechange'" in output


def test_print_header_escapes_project_name():
    # The project name defaults to the repository directory name, which can
    # contain characters that are special in HTML.
    creator = HTMLReportCreator()
    creator.title = "R&D</title><script>alert(1)</script>"
    f = StringIO()
    creator.print_header(f)
    output = f.getvalue()

    assert "</title><script>" not in output
    assert (
        "<title>GitStats - R&amp;D&lt;/title&gt;&lt;script&gt;alert(1)&lt;/script&gt;</title>"
        in output
    )


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
    # SVG icons instead of emoji
    assert 'class="icon-moon"' in output
    assert 'class="icon-sun"' in output
    assert "🌙" not in output


def test_print_nav_marks_current_page():
    from unittest.mock import Mock

    creator = HTMLReportCreator()
    creator.data = Mock()
    creator.data.ai_summaries = {}

    f = StringIO()
    creator.print_nav(f, "authors.html")
    output = f.getvalue()

    assert '<a href="authors.html" class="active" aria-current="page">Authors</a>' in output
    assert '<a href="index.html">General</a>' in output
    assert output.count('aria-current="page"') == 1


@pytest.mark.parametrize(
    "page",
    [
        "index.html",
        "activity.html",
        "authors.html",
        "files.html",
        "lines.html",
        "tags.html",
        "ownership.html",
        "history.html",
    ],
)
def test_each_page_marks_itself_current(mock_data_collector, temp_dir, page):
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    with open(os.path.join(temp_dir, page), encoding="utf-8") as f:
        content = f.read()
    assert f'<a href="{page}" class="active" aria-current="page">' in content
    assert content.count('aria-current="page"') == 1


# ── HTMLReportCreator.create_index_html ──────────────────────────────────


def test_create_index_html(mock_data_collector, temp_dir):
    creator = HTMLReportCreator()
    creator.title = mock_data_collector.project_name
    creator.data = mock_data_collector
    creator.create_index_html(mock_data_collector, temp_dir)

    with open(f"{temp_dir}/index.html", encoding="utf-8") as f:
        html = f.read()

    # The repository's name heads the page, with report metadata under it
    assert "<h1>test-project</h1>" in html
    assert '<p class="page-meta">2022-12-01 &rarr; 2023-04-01 &middot; generated ' in html
    assert "</html>" in html

    # Headline numbers are stat tiles, with the old table's averages as notes
    assert '<dl class="stat-tiles" style="--cols: 6; --cols-md: 3; --cols-sm: 2">' in html
    assert html.count('<div class="stat-tile">') == 6
    assert '<dt>Commits</dt><dd class="stat-value">50</dd>' in html
    assert "12.5 per active day &middot; 0.4 per day" in html
    assert "16.7 commits per author" in html
    # Large counts use thousands separators (total_lines=2000, added=3000, removed=1000)
    assert '<dt>Lines of Code</dt><dd class="stat-value">2,000</dd>' in html
    assert '<span class="stat-added">+3,000</span> added' in html
    assert '<span class="stat-removed">−1,000</span> removed' in html
    assert "3 extensions" in html
    assert "of 120 days &middot; 3.33%" in html
    assert '<dt>Longest Streak</dt><dd class="stat-value">4 days</dd>' in html

    # The old key/value table is gone: its rows live in the tiles and the meta line
    assert "Report Details" not in html
    assert "Total Commits" not in html
    assert "Project Age" not in html

    # Commits per year across the whole history
    assert '<canvas id="chart-overview-yearly">' in html
    assert 'href="activity.html">Activity in detail &rarr;</a>' in html

    # Top contributors: commits, share, and a bar relative to the top author
    assert (
        '<tr><td>Alice Smith</td><td class="num">30</td><td class="num">60.0%</td>'
        '<td class="share-cell"><span class="share-bar" aria-hidden="true">'
        '<span style="width: 100.0%"></span></span></td></tr>'
    ) in html
    assert '<span style="width: 50.0%">' in html  # Bob: 15 of Alice's 30
    assert "All 3 authors &rarr;" in html

    # Latest releases, newest first, next to the contributors
    assert '<div class="overview-columns">' in html
    assert html.index(">v1.1.0<") < html.index(">v1.0.0<")
    assert "<td>Alice Smith, Bob Jones</td>" in html
    assert "All 2 tags &rarr;" in html


def _render_index(data, temp_dir):
    creator = HTMLReportCreator()
    creator.title = data.project_name
    creator.data = data
    creator.create_index_html(data, temp_dir)
    with open(f"{temp_dir}/index.html", encoding="utf-8") as f:
        return f.read()


def test_index_notes_longest_quiet_stretch(mock_data_collector, temp_dir):
    mock_data_collector.commits_by_year = {2010: 3, 2011: 0, 2014: 2, 2016: 1}
    html = _render_index(mock_data_collector, temp_dir)
    # 2012-2013 are missing and 2011 is empty: the longest run is 2011-2013
    assert '<p class="chart-note">No commits from 2011 to 2013.</p>' in html


def test_index_single_empty_year_is_not_noted(mock_data_collector, temp_dir):
    mock_data_collector.commits_by_year = {2020: 1, 2022: 1}
    assert "chart-note" not in _render_index(mock_data_collector, temp_dir)


def test_index_without_tags_has_no_releases(mock_data_collector, temp_dir):
    mock_data_collector.tags = {}
    html = _render_index(mock_data_collector, temp_dir)
    assert "Latest Releases" not in html
    assert "overview-columns" not in html
    assert "Top Contributors" in html


def test_index_release_authors_are_capped_and_escaped(mock_data_collector, temp_dir):
    mock_data_collector.project_name = "R&D <app>"
    mock_data_collector.tags = {
        "v2.0.0": {
            "date": "2023-05-01",
            "commits": 6,
            "authors": {"<Eve>": 3, "Bob Jones": 2, "Carol": 1},
        }
    }
    html = _render_index(mock_data_collector, temp_dir)
    assert "<h1>R&amp;D &lt;app&gt;</h1>" in html
    assert "<td>&lt;Eve&gt;, Bob Jones +1</td>" in html


def test_stat_tiles_html():
    result = stat_tiles_html([("Streak", "1 day", "consecutive"), ("Files", "25", "3 extensions")])
    assert result == (
        '<dl class="stat-tiles" style="--cols: 2; --cols-md: 2; --cols-sm: 2">'
        '<div class="stat-tile"><dt>Streak</dt><dd class="stat-value">1 day</dd>'
        '<dd class="stat-note">consecutive</dd></div>'
        '<div class="stat-tile"><dt>Files</dt><dd class="stat-value">25</dd>'
        '<dd class="stat-note">3 extensions</dd></div>'
        "</dl>"
    )


@pytest.mark.parametrize(
    "count,columns",
    [
        (6, "--cols: 6; --cols-md: 3; --cols-sm: 2"),
        (3, "--cols: 3; --cols-md: 3; --cols-sm: 1"),
        (2, "--cols: 2; --cols-md: 2; --cols-sm: 2"),
        (1, "--cols: 1; --cols-md: 1; --cols-sm: 1"),
    ],
)
def test_stat_tiles_rows_are_always_full(count, columns):
    result = stat_tiles_html([("L", "1", "n")] * count)
    assert f'style="{columns}"' in result


def test_stat_tiles_empty_note_is_omitted():
    result = stat_tiles_html([("Tags", "0", "")])
    assert 'class="stat-note"' not in result


def test_page_summaries_use_stat_tiles(mock_data_collector, temp_dir):
    """Files, Lines, Tags, Ownership and History open with stat tiles, not a bare <dl>."""
    HTMLReportCreator().create(mock_data_collector, temp_dir)

    def page(name):
        with open(os.path.join(temp_dir, name), encoding="utf-8") as f:
            return f.read()

    for name in ("files.html", "lines.html", "tags.html", "ownership.html", "history.html"):
        content = page(name)
        assert '<dl class="stat-tiles"' in content, name
        assert "<dl>" not in content, name

    # Files: 25 files, 3 extensions, 2000 lines -> 80 per file, 50000 bytes in total
    files = page("files.html")
    assert "3 extensions" in files
    assert "80 per file" in files
    assert "48.8 KB in total" in files

    # Lines: +3000 / -1000 over 50 commits
    lines = page("lines.html")
    assert '<dd class="stat-value"><span class="stat-added">+3,000</span></dd>' in lines
    assert "60 per commit" in lines
    assert "20 per commit" in lines

    # Tags: v1.1.0 (2023-04-05) is the latest of two; 50 commits / 2 tags
    tags = page("tags.html")
    assert "latest v1.1.0 &middot; 2023-04-05" in tags
    assert '<dt>Commits per Tag</dt><dd class="stat-value">25.0</dd>' in tags

    # Ownership and History keep their intro paragraph above the tiles
    ownership = page("ownership.html")
    assert ownership.index("bus-factor risk") < ownership.index('<dl class="stat-tiles"')
    assert "<dt>Single-Owner Files</dt>" in ownership
    history = page("history.html")
    assert "<dt>Peak Year</dt>" in history
    assert "latest in 2023" in history


# ── HTMLReportCreator.create_activity_html ───────────────────────────────


def test_create_activity_html(mock_data_collector, temp_dir):
    creator = HTMLReportCreator()
    creator.title = mock_data_collector.project_name
    creator.data = mock_data_collector
    creator.create_activity_html(mock_data_collector, temp_dir)

    with open(f"{temp_dir}/activity.html", encoding="utf-8") as f:
        html = f.read()

    assert "<h1>Activity</h1>" in html
    assert "Month of Year" in html
    assert "Commits by year/month" in html

    # Coarse to fine: year, month, week, then the daily rhythm
    order = ["Commits by Year", "Commits by year/month", "Weekly activity", "Punch Card"]
    positions = [html.index(f">{title}</a></h2>") for title in order]
    assert positions == sorted(positions)

    # Yearly activity duplicated Commits by Year; Hour of Day, Day of Week and
    # Hour of Week are merged into the punch card
    for gone in ("Yearly activity", "Hour of Day", "Day of Week", "Hour of Week"):
        assert f">{gone}</a></h2>" not in html
    for chart in ("chart-yearly-activity", "chart-hour-of-day", "chart-day-of-week"):
        assert f'<canvas id="{chart}">' not in html
    # ...but their anchors still exist, next to the sections that replaced them
    for anchor in ("yearly_activity", "hour_of_day", "day_of_week", "hour_of_week"):
        assert f'<span id="{anchor}"></span>' in html
    assert html.index('id="yearly_activity"') < html.index('id="commits_by_year"')
    assert html.index('id="hour_of_week"') < html.index('id="punch_card"')


def test_activity_punch_card(mock_data_collector, temp_dir):
    creator = HTMLReportCreator()
    creator.title = mock_data_collector.project_name
    creator.data = mock_data_collector
    creator.create_activity_html(mock_data_collector, temp_dir)
    with open(f"{temp_dir}/activity.html", encoding="utf-8") as f:
        html = f.read()

    # Mon-Fri 9:00-16:00 have one commit each; the busiest cell has 2
    assert '<tr><th>Mon</th><td class="heat heat0"></td>' in html
    assert '<td class="heat heat2">1</td>' in html
    # Day totals with their share (Mon: 8 of 50)
    assert '<td class="num punch-total">8 (16.0%)</td>' in html
    # Hour totals, colored against the busiest hour (14:00, 15 of 50 commits)
    assert '<td class="heat heat4" title="30.0% of commits">15</td>' in html
    assert '<td class="num punch-total">50</td>' in html
    assert '<p class="heat-legend">Fewer' in html


def test_activity_monthly_table_is_folded(mock_data_collector, temp_dir):
    creator = HTMLReportCreator()
    creator.title = mock_data_collector.project_name
    creator.data = mock_data_collector
    creator.create_activity_html(mock_data_collector, temp_dir)
    with open(f"{temp_dir}/activity.html", encoding="utf-8") as f:
        html = f.read()

    months = len(mock_data_collector.commits_by_month)
    summary = (
        '<details class="table-details"><summary>Table: commits and lines per month '
        f"({months} months with commits)</summary>"
    )
    assert summary in html
    # The chart comes first, outside the folded table
    assert html.index('<canvas id="chart-commits-by-year-month">') < html.index(summary)


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


def test_render_chartjs_highlight_top_series():
    creator = HTMLReportCreator()
    datasets = [{"label": f"A{i}", "data": [i]} for i in range(7)]
    result = creator._render_chartjs("chart-hl", "line", ["X"], datasets, highlight=5)
    # The first 5 keep distinct colors; the rest are grey and drawn behind
    assert result.count(HTMLReportCreator.OTHER_SERIES_COLOR) == 4  # border + background x 2
    assert '"label": "A4", "data": [4], "borderColor": "#e16f24"' in result
    assert '"label": "A5", "data": [5], "borderColor": "rgba(128, 128, 128, 0.45)"' in result
    # Only the highlighted series are listed in the legend
    assert "filter: function(item) { return item.datasetIndex < 5; }" in result


def test_authors_contributor_timeline(mock_data_collector, temp_dir):
    creator = HTMLReportCreator()
    creator.title = mock_data_collector.project_name
    creator.data = mock_data_collector
    creator.create_authors_html(mock_data_collector, temp_dir)
    with open(f"{temp_dir}/authors.html", encoding="utf-8") as f:
        html = f.read()

    # Replaces the cumulative commits line chart; the old anchor still lands here
    assert '<canvas id="chart-commits-by-author">' not in html
    assert ">Commits per Author</a></h2>" not in html
    assert html.index('<span id="commits_per_author"></span>') < html.index(
        'id="contributor_timeline"'
    )

    # One row per author, summarised for screen readers
    assert html.count('<div class="timeline-row') == 3
    assert 'aria-label="Alice Smith: 30 commits, 2023-01 to 2023-06"' in html
    # Mock history spans 2023-01..2023-06: six months, no year boundary,
    # so the axis shows the first and last month
    assert '<span class="timeline-mark" style="left: 41.667%; --size: 10.2px" ' in html
    assert 'title="2023-03: 8 commits"' in html
    assert (
        '<div class="timeline-axis" aria-hidden="true"><span>2023-01</span><span>2023-06</span>'
        in html
    )

    # The lines chart keeps five colors and greys the rest
    assert "The top 5 authors are in color, the others in grey." in html


def test_contributor_timeline_years_and_bots(mock_data_collector):
    mock_data_collector.author_of_month = {
        "2019-11": {"Alice Smith": 1},
        "2021-02": {"dependabot[bot]": 3},
    }
    mock_data_collector.get_author_info.side_effect = lambda a: {"commits": 4}
    html = HTMLReportCreator()._contributor_timeline_html(
        mock_data_collector, ["Alice Smith", "dependabot[bot]"]
    )
    # Year boundaries become gridlines with labels; no month labels needed then
    assert '<span class="timeline-year" style="left: 12.500%">2020</span>' in html
    assert '<span class="timeline-year" style="left: 87.500%">2021</span>' in html
    assert '<div class="timeline-axis" aria-hidden="true"></div>' in html
    # Bots are marked so CSS can grey them out
    assert (
        '<div class="timeline-row bot" role="img" aria-label="dependabot[bot]: 4 commits, 2021-02 to 2021-02">'
        in html
    )
    # A single month still gets a mark; the span has zero width
    assert "width: 0.000%" in html


# ── HTMLReportCreator.create_files_html ──────────────────────────────────


def test_create_files_html(mock_data_collector, temp_dir):
    creator = HTMLReportCreator()
    creator.title = mock_data_collector.project_name
    creator.data = mock_data_collector
    creator.create_files_html(mock_data_collector, temp_dir)

    with open(f"{temp_dir}/files.html", encoding="utf-8") as f:
        html = f.read()

    assert "<h1>Files</h1>" in html
    assert '<dt>Files</dt><dd class="stat-value">25</dd>' in html
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
    assert '<dt>Lines of Code</dt><dd class="stat-value">2,000</dd>' in html


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


def test_create_tags_html_escapes_tag_names(mock_data_collector, temp_dir):
    # "<svg/onload=alert(1)>" is a valid git ref name.
    mock_data_collector.tags = {
        "<svg/onload=alert(1)>": {
            "date": "2023-02-20",
            "commits": 1,
            "authors": {"A&B": 1},
            "hash": "abc123",
            "stamp": 1677000000,
        },
    }
    creator = HTMLReportCreator()
    creator.title = mock_data_collector.project_name
    creator.data = mock_data_collector
    creator.create_tags_html(mock_data_collector, temp_dir)

    with open(f"{temp_dir}/tags.html", encoding="utf-8") as f:
        html = f.read()

    assert "<svg/onload" not in html
    assert "&lt;svg/onload=alert(1)&gt;" in html
    assert "A&amp;B (1)" in html


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
    labels, loc_ds = creator._build_author_time_series(mock_data_collector)
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

    labels, loc_ds = creator._build_author_time_series(mock_data_collector)

    assert len(labels) == 2
    assert any("Alice Smith" in str(ds) for ds in loc_ds)
    # Each author dataset should have 2 data points
    for ds in loc_ds:
        assert len(ds["data"]) == 2


def test_build_author_time_series_downsample(mock_data_collector):
    """When total_points > MAX_POINTS (500), downsampling kicks in."""
    creator = HTMLReportCreator()
    creator.data = mock_data_collector

    # Build 1000 timestamps (one per hour for ~42 days) to trigger downsampling
    base_stamp = 1670000000  # 2022-12-02
    authors = mock_data_collector.get_authors(20)  # Alice, Bob, Charlie
    changes = {}
    for i in range(1000):
        stamp = base_stamp + i * 3600  # one data point per hour
        author = authors[i % len(authors)]
        changes[stamp] = {
            author: {
                "lines_added": (i + 1) * 10,
                "commits": i + 1,
            }
        }
    mock_data_collector.changes_by_date_by_author = changes

    labels, loc_ds = creator._build_author_time_series(mock_data_collector)

    # Should be downsampled to ~500 + 1 (last point ensured)
    assert len(labels) <= 502, f"Expected ≤502 labels, got {len(labels)}"
    assert len(labels) >= 498, f"Expected ≥498 labels, got {len(labels)}"

    # All authors should be present
    assert len(loc_ds) == len(authors)

    # Each author dataset should have the same number of data points as labels
    for ds in loc_ds:
        assert len(ds["data"]) == len(labels), (
            f"Author {ds['label']} has {len(ds['data'])} points, expected {len(labels)}"
        )

    # The last timestamp should always be included
    last_expected = sorted(changes.keys())[-1]
    assert labels[-1] == last_expected, f"Last label should be {last_expected}, got {labels[-1]}"

    # Data values should be monotonically non-decreasing (cumulative)
    for ds in loc_ds:
        values = ds["data"]
        for j in range(1, len(values)):
            assert values[j] >= values[j - 1], (
                f"{ds['label']} LOC not monotonic at index {j}: {values[j - 1]} -> {values[j]}"
            )


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
        "ownership.html",
        "history.html",
    ]
    for fname in expected_files:
        path = f"{temp_dir}/{fname}"
        assert os.path.exists(path), f"Missing: {fname}"
        with open(path, encoding="utf-8") as f:
            content = f.read()
            assert "</html>" in content

    # AI insights page should NOT be created when ai_summaries is empty
    assert not os.path.exists(f"{temp_dir}/ai-insights.html")


def test_every_table_scrolls_in_its_own_box(mock_data_collector, temp_dir):
    """Wide tables must not widen the page on phones."""
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    for fname in os.listdir(temp_dir):
        if not fname.endswith(".html"):
            continue
        with open(os.path.join(temp_dir, fname), encoding="utf-8") as f:
            content = f.read()
        assert content.count("<table") == content.count('<div class="table-scroll"><table'), fname
        assert content.count("</table>") == content.count("</table></div>"), fname


def test_table_with_chart_layout_uses_css_class(mock_data_collector, temp_dir):
    # A class (not inline flex styles) so the chart can wrap below the table on phones
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    with open(os.path.join(temp_dir, "activity.html"), encoding="utf-8") as f:
        content = f.read()
    assert '<div class="table-with-chart">' in content
    assert '<div class="chart-pane">' in content
    assert "display:flex" not in content


def test_create_all_pages_with_ai(mock_data_collector_with_ai, temp_dir):
    creator = HTMLReportCreator()
    creator.create(mock_data_collector_with_ai, temp_dir)

    assert os.path.exists(f"{temp_dir}/ai-insights.html")


def test_create_copies_static_files(mock_data_collector, temp_dir):
    creator = HTMLReportCreator()
    creator.create(mock_data_collector, temp_dir)

    for fname in ("sortable.js", "chart.umd.min.js", "gitstats.css"):
        assert os.path.exists(f"{temp_dir}/{fname}"), f"Missing static file: {fname}"
    # IBM Plex Mono and its OFL license travel with every report
    for fname in FONT_FILES:
        assert os.path.exists(f"{temp_dir}/{fname}"), f"Missing font file: {fname}"
    # Sort arrows are drawn by CSS now; the old GIFs are no longer shipped
    assert not any(name.endswith(".gif") for name in os.listdir(temp_dir))
    with open(f"{temp_dir}/sortable.js", "rb") as f:
        sortable = f.read()
    assert b"<img" not in sortable
    assert b'data-sort="none"' in sortable


def test_numeric_columns_are_marked(mock_data_collector, temp_dir):
    """Counts, percentages and spans carry class="num" so CSS right-aligns them."""
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    with open(os.path.join(temp_dir, "authors.html"), encoding="utf-8") as f:
        authors = f.read()
    # Alice Smith: 30 commits (60%), +2000 / -500, 12 active days, rank 1
    assert (
        '<tr><td>Alice Smith</td><td class="num">30 (60.00%)</td>'
        '<td class="num">2000</td><td class="num">500</td>'
    ) in authors
    assert '<th class="num">Commits (%)</th>' in authors
    assert '<th class="unsortable num">Age</th>' in authors
    # Text columns stay left-aligned
    assert "<th>First commit</th>" in authors

    with open(os.path.join(temp_dir, "files.html"), encoding="utf-8") as f:
        files = f.read()
    assert '<th class="num">Files (%)</th>' in files
    assert '<td class="num">10 (40.00%)</td>' in files  # py: 10 of 25 files


def test_bundled_fonts_match_stylesheet():
    """Every font the stylesheet loads is a real WOFF2 file in the package."""
    package_dir = os.path.dirname(gitstats.report_creator.__file__)
    with open(os.path.join(package_dir, "gitstats.css"), encoding="utf-8") as f:
        css = f.read()
    referenced = set(re.findall(r'url\("([^"]+\.woff2)"\)', css))
    bundled = {name for name in FONT_FILES if name.endswith(".woff2")}
    assert referenced == bundled
    for name in bundled:
        with open(os.path.join(package_dir, name), "rb") as f:
            assert f.read(4) == b"wOF2", name
    # One @font-face per weight used by the stylesheet
    assert sorted(re.findall(r"font-weight: (\d+);\n\tfont-display: swap", css)) == [
        "400",
        "500",
        "600",
        "700",
    ]
    with open(os.path.join(package_dir, "IBMPlexMono-LICENSE.txt"), encoding="utf-8") as f:
        assert "SIL Open Font License, Version 1.1" in f.read()


def test_small_formatting_fixes(mock_data_collector, temp_dir):
    HTMLReportCreator().create(mock_data_collector, temp_dir)

    def page(name):
        with open(os.path.join(temp_dir, name), encoding="utf-8") as f:
            return f.read()

    # Author span is compact, with the exact day count on hover (Alice: 150 days)
    assert '<td class="nowrap num" title="150 days">5 mo</td>' in page("authors.html")
    # Average file size in readable units (50000 bytes / 25 files)
    assert '<dt>Average File Size</dt><dd class="stat-value">2.0 KB</dd>' in page("files.html")
    # Timezone cells carry one "heat" class, not "heat heat heatN"
    activity = page("activity.html")
    assert "heat heat heat" not in activity
    assert '<td class="heat heat4">30</td>' in activity
    # Tag names and dates don't wrap
    assert '<td class="nowrap">v1.0.0</td>' in page("tags.html")


# ── Code ownership ───────────────────────────────────────────────────────


def test_compute_code_ownership_stats():
    author_files = {
        "Alice": {"a.py": 3, "shared.py": 2},
        "Bob": {"shared.py": 5, "b.py": 1},
        "release[bot]": {"shared.py": 99},  # bots excluded
    }
    result = compute_code_ownership(author_files)

    files = {fs["path"]: fs for fs in result["files"]}
    # a.py: only Alice -> single owner
    assert files["a.py"]["contributors"] == 1
    assert files["a.py"]["owner"] == "Alice"
    # shared.py: Alice 2 + Bob 5 -> Bob owns, bot ignored, 2 contributors
    assert files["shared.py"]["contributors"] == 2
    assert files["shared.py"]["owner"] == "Bob"
    assert files["shared.py"]["edits"] == 7
    assert files["shared.py"]["ownership_pct"] == round(100.0 * 5 / 7, 1)

    assert result["total_files"] == 3
    assert result["single_owner_files"] == 2  # a.py and b.py

    authors = {a["author"]: a for a in result["authors"]}
    assert "release[bot]" not in authors
    assert authors["Alice"]["files_owned"] == 1  # a.py
    assert authors["Alice"]["files_solely_owned"] == 1
    assert authors["Bob"]["files_owned"] == 2  # shared.py + b.py
    assert authors["Bob"]["files_touched"] == 2


def test_compute_code_ownership_empty():
    assert compute_code_ownership({}) == {
        "files": [],
        "authors": [],
        "total_files": 0,
        "single_owner_files": 0,
    }


def test_ownership_page_renders(mock_data_collector, temp_dir):
    creator = HTMLReportCreator()
    creator.create(mock_data_collector, temp_dir)

    with open(f"{temp_dir}/ownership.html", encoding="utf-8") as f:
        content = f.read()

    assert "Code Ownership" in content
    assert "Bus Factor Risk" in content
    # solo_alice.py is only touched by Alice -> appears as a single-owner file
    assert "solo_alice.py" in content
    assert "Alice Smith" in content
    assert "</html>" in content


def test_ownership_page_empty_state(mock_data_collector, temp_dir):
    mock_data_collector.author_files = {}
    creator = HTMLReportCreator()
    creator.create(mock_data_collector, temp_dir)

    with open(f"{temp_dir}/ownership.html", encoding="utf-8") as f:
        content = f.read()

    assert "No ownership data available" in content
    assert "</html>" in content


def test_ownership_page_escapes_names(mock_data_collector, temp_dir):
    mock_data_collector.author_files = {"Al<ice>": {"we<i>rd.py": 3}}
    creator = HTMLReportCreator()
    creator.create(mock_data_collector, temp_dir)

    with open(f"{temp_dir}/ownership.html", encoding="utf-8") as f:
        content = f.read()

    assert "Al&lt;ice&gt;" in content
    assert "we&lt;i&gt;rd.py" in content


def test_open_report_file_confined_to_report_dir(temp_dir):
    creator = HTMLReportCreator()
    f = creator._open_report_file(temp_dir, "ownership.html")
    f.close()
    assert os.path.exists(f"{temp_dir}/ownership.html")
    with pytest.raises(ValueError):
        creator._open_report_file(temp_dir, "../escape.html")


# ── Project history ──────────────────────────────────────────────────────


def test_classify_eras_full_arc():
    """A long life: birth, surge, silence, revival, peak — all detected."""
    eras = _classify_eras({2019: 55, 2020: 20, 2021: 2, 2023: 30, 2024: 120, 2025: 60, 2026: 25})
    # median of non-zero years (2,20,25,30,55,60,120) = 30
    assert eras[2019] == "birth"
    assert eras[2021] == "quiet"  # 2 <= 0.35 * 30
    assert eras[2022] == "dormant"  # gap year, no commits at all
    assert eras[2023] == "revival"  # back at the baseline after silence
    assert eras[2024] == "peak"  # the maximum year
    assert eras[2025] == "surge"  # 60 >= 1.6 * 30
    assert eras[2026] == "steady"


def test_classify_eras_tiny_history():
    """With under three active years only structural labels apply."""
    assert _classify_eras({2024: 10}) == {2024: "birth"}
    assert _classify_eras({2024: 10, 2025: 100}) == {2024: "birth", 2025: "steady"}
    assert _classify_eras({}) == {}


def test_compute_project_history_fields(mock_data_collector):
    history = compute_project_history(mock_data_collector)

    assert history["first_year"] == 2023
    assert history["last_year"] == 2023
    assert history["peak_year"] == 2023
    assert history["total_releases"] == 2  # v1.0.0 + v1.1.0

    (y,) = history["years"]
    assert y["year"] == 2023
    assert y["era"] == "birth"
    assert y["commits"] == 50
    assert y["commits_pct"] == 100.0
    assert y["top_author"] == "Alice Smith"
    assert y["top_author_commits"] == 30
    # all three authors first appeared in 2023, ranked by that year's commits
    assert y["newcomers"] == ["Alice Smith", "Bob Jones", "Charlie Brown"]
    assert y["releases"] == ["v1.0.0", "v1.1.0"]


def test_compute_project_history_excludes_bots():
    class Data:
        commits_by_year = {2024: 10}
        author_of_year = {2024: {"dependabot[bot]": 8, "Ann": 2}}
        lines_added_by_year = {}
        lines_removed_by_year = {}
        authors = {
            "Ann": {"first_commit_stamp": 1704067200},  # 2024-01-01
            "dependabot[bot]": {"first_commit_stamp": 1704067200},
        }
        tags = {}

    (y,) = compute_project_history(Data())["years"]
    assert y["top_author"] == "Ann"  # the bot outnumbers her but is skipped
    assert y["newcomers"] == ["Ann"]
    assert y["active_authors"] == 2  # raw count still includes everyone


def test_compute_project_history_empty():
    class Data:
        commits_by_year = {}

    history = compute_project_history(Data())
    assert history["years"] == []
    assert history["first_year"] is None


def test_history_page_renders(mock_data_collector, temp_dir):
    creator = HTMLReportCreator()
    creator.create(mock_data_collector, temp_dir)

    with open(f"{temp_dir}/history.html", encoding="utf-8") as f:
        content = f.read()

    assert "History" in content
    assert "BIRTH" in content
    assert "Alice Smith" in content
    assert "v1.0.0" in content
    assert "</html>" in content


def test_history_page_empty_state(mock_data_collector, temp_dir):
    mock_data_collector.commits_by_year = {}
    creator = HTMLReportCreator()
    creator.data = mock_data_collector
    creator.title = "t"
    creator.create_history_html(mock_data_collector, temp_dir)

    with open(f"{temp_dir}/history.html", encoding="utf-8") as f:
        content = f.read()

    assert "No history to tell yet" in content
    assert "</html>" in content


def test_history_page_escapes_names(mock_data_collector, temp_dir):
    mock_data_collector.author_of_year = {2023: {"Al<ice>": 50}}
    mock_data_collector.authors = {"Al<ice>": {"first_commit_stamp": 1673776800}}
    creator = HTMLReportCreator()
    creator.data = mock_data_collector
    creator.title = "t"
    creator.create_history_html(mock_data_collector, temp_dir)

    with open(f"{temp_dir}/history.html", encoding="utf-8") as f:
        content = f.read()

    assert "Al&lt;ice&gt;" in content


# ── AI chronicle parsing and rendering ───────────────────────────────────


def test_parse_chronicle_full():
    text = """[PROLOGUE]
A small tool grew into a project.
Told entirely from its commits.
[YEAR 2007] The first year
One author laid the groundwork.
It compiled on the second try.
[YEAR 2008] Growing pains
New contributors arrived."""
    parsed = parse_chronicle(text)

    assert parsed["prologue"] == "A small tool grew into a project. Told entirely from its commits."
    assert parsed["chapters"][2007]["title"] == "The first year"
    assert (
        parsed["chapters"][2007]["story"]
        == "One author laid the groundwork. It compiled on the second try."
    )
    assert parsed["chapters"][2008]["title"] == "Growing pains"


def test_parse_chronicle_without_prologue_or_title():
    parsed = parse_chronicle("[YEAR 2020]\nJust a story line.")
    assert parsed["prologue"] == ""
    assert parsed["chapters"][2020] == {"title": "", "story": "Just a story line."}


def test_parse_chronicle_unstructured_text():
    parsed = parse_chronicle("The model ignored the format entirely.")
    assert parsed["chapters"] == {}
    assert parsed["prologue"] == ""


def test_history_page_renders_chronicle(mock_data_collector, temp_dir):
    mock_data_collector.ai_summaries = {
        "chronicle": {
            "summary": (
                "[PROLOGUE]\nHow test-project came to be.\n"
                "[YEAR 2023] The <first> year\nAlice & Bob built it."
            ),
            "error": None,
        }
    }
    creator = HTMLReportCreator()
    creator.data = mock_data_collector
    creator.title = "t"
    creator.create_history_html(mock_data_collector, temp_dir)

    with open(f"{temp_dir}/history.html", encoding="utf-8") as f:
        content = f.read()

    assert "How test-project came to be." in content
    assert "AI narration, generated from the facts below." in content
    # chapter title and story are HTML-escaped and attached to the year block
    assert "The &lt;first&gt; year" in content
    assert "Alice &amp; Bob built it." in content
    # the deterministic facts remain visible alongside the story
    assert "50 commits (100.0%)" in content


def test_history_page_chronicle_fallback_when_unparseable(mock_data_collector, temp_dir):
    mock_data_collector.ai_summaries = {
        "chronicle": {"summary": "A free-form narrative without markers.", "error": None}
    }
    creator = HTMLReportCreator()
    creator.data = mock_data_collector
    creator.title = "t"
    creator.create_history_html(mock_data_collector, temp_dir)

    with open(f"{temp_dir}/history.html", encoding="utf-8") as f:
        content = f.read()

    # shown whole rather than dropped
    assert "A free-form narrative without markers." in content
