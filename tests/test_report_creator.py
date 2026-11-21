"""Tests for gitstats.report_creator – HTML generation, helpers, chart rendering."""

import datetime
import json
import os
import re
from io import StringIO
from types import SimpleNamespace

import pytest

from gitstats import load_config
from gitstats.main import GitDataCollector
from gitstats.report_creator import (
    BADGES_PLACEHOLDER_URL,
    CHART_NOTE,
    CHART_SCRIPT,
    INSIGHTS_END,
    NAV_GROUPS,
    NAV_PAGES,
    NAV_START,
    SHARE_SCALE_HEADER,
    SKIP_LINK,
    HTMLReportCreator,
    ReportCreator,
    _classify_eras,
    author_html,
    collapse_gap_categories,
    collapse_gap_time,
    collapsed_slots,
    collapsed_width,
    compute_code_ownership,
    compute_hotspots,
    compute_project_history,
    first_tag_year,
    gap_annotations,
    get_keys_sorted_by_value_key,
    get_keys_sorted_by_values,
    html_header,
    html_linkify,
    last_year_commits,
    longest_zero_run,
    month_range,
    months_back,
    overview_signals,
    page_title,
    parse_chronicle,
    quiet_months,
    release_cadence,
    release_gaps,
    report_share_card_html,
    report_share_description,
    share_meta_html,
    share_text,
    signals_html,
    span_text,
    sparkline_svg,
    stat_tiles_html,
    sum_since,
    tag_year,
    tags_newest_first,
    year_span,
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
    # a canvas is an image to a screen reader, said in words
    assert '<canvas id="chart-test" role="img" aria-label="Bar chart, A to C">' in result
    assert "type: 'bar'" in result
    # Labels should be JSON-encoded
    assert '"A"' in result
    assert '"B"' in result
    # CSS var placeholder replaced with JS call
    assert "__CSS_BAR_COLOR__" not in result
    assert "getCSSVar('--bar-color')" in result
    # Single dataset: no legend, no borderColor in JS
    assert "legend: { display: false }" in result
    # No y-axis title: the section heading names the unit
    assert "title: { display: true" not in result


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
    assert "legend: { display: true, labels: {" in result
    # Series colors come from CSS variables, so they follow the theme
    assert (
        "\"borderColor\": getCSSVar('--series-1'), \"backgroundColor\": getCSSVar('--series-1') + '33'"
        in result
    )
    assert "getCSSVar('--series-2')" in result
    assert '"series": 2' in result
    # Line charts show a line sample in the legend
    assert "usePointStyle: true, pointStyle: 'line'" in result
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


def test_render_chartjs_default_max_bar_thickness():
    """A bar chart without its own bar width caps it: a single bar would
    otherwise fill the whole chart as a slab. A line chart has no bars."""
    creator = HTMLReportCreator()
    result = creator._render_chartjs(
        "chart-nothick",
        "bar",
        ["X"],
        [{"label": "C", "data": [1]}],
    )
    assert "datasets: { bar: { maxBarThickness: 64 } }" in result
    line = creator._render_chartjs(
        "chart-line", "line", ["X", "Y"], [{"label": "C", "data": [1, 2]}]
    )
    assert "maxBarThickness" not in line


def test_render_chartjs_xss_protection():
    """Ensure </script> is escaped in labels/ datasets to prevent XSS."""
    creator = HTMLReportCreator()
    result = creator._render_chartjs(
        "chart-xss",
        "bar",
        ["</script><script>alert(1)"],
        [{"label": "</script>", "data": [1]}],
    )
    assert result.count("</script>") == 1


def test_render_chartjs_no_y_axis_title():
    """Section headings name what a chart counts, so the y-axis carries no title."""
    creator = HTMLReportCreator()
    result = creator._render_chartjs("chart-yl", "bar", ["X"], [{"label": "C", "data": [1]}])
    assert "y: { beginAtZero: true, ticks: { precision: 0 } }" in result
    assert "title: { display: true" not in result


def test_chart_fonts_are_monospace():
    creator = HTMLReportCreator()
    creator.title = "p"
    f = StringIO()
    creator.print_header(f)
    assert "Chart.defaults.font.family = getCSSVar('--font-mono');" in f.getvalue()


@pytest.mark.parametrize(
    "values,expected",
    [
        ([1, 0, 0, 2, 0, 3], (1, 2)),
        ([0, 0, 0], (0, 2)),
        ([1, 2, 3], None),
        ([], None),
    ],
)
def test_longest_zero_run(values, expected):
    assert longest_zero_run(values) == expected


def test_gap_annotations_band_and_peaks():
    years = list(range(2007, 2027))
    values = [107, 29, 45, 36, 28, 17, 11, 19, 2] + [0] * 8 + [68, 90, 95]
    ann = gap_annotations(years, values, min_gap=2)
    assert ann["bands"] == [
        {"from": 9, "to": 16, "text": "No commits 2016 – 2023", "short": "no commits"}
    ]
    # The busiest year on each side of the gap
    assert ann["peaks"] == [
        {"index": 0, "text": "2007 · 107"},
        {"index": 19, "text": "2026 · 95"},
    ]


def test_gap_annotations_ignores_short_gaps():
    assert gap_annotations(["2020", "2021", "2022"], [5, 0, 3], min_gap=2) == {}


def test_render_chartjs_annotations():
    creator = HTMLReportCreator()
    ann = {"bands": [{"from": 1, "to": 1, "text": "gap", "short": ""}], "peaks": []}
    result = creator._render_chartjs(
        "c-ann", "bar", ["A", "B", "C"], [{"label": "C", "data": [1, 0, 2]}], annotations=ann
    )
    assert "plugins: [chartAnnotations]," in result
    assert (
        'gsAnnotations: {"bands": [{"from": 1, "to": 1, "text": "gap", "short": ""}], "peaks": []}'
        in result
    )
    # a band alone needs no headroom; labels above the bars do
    assert "grace" not in result
    peaks = {**ann, "peaks": [{"index": 2, "text": "C · 2"}]}
    labelled = creator._render_chartjs(
        "c-peaks", "bar", ["A", "B", "C"], [{"label": "C", "data": [1, 0, 2]}], annotations=peaks
    )
    assert "grace: '10%'" in labelled
    plain = creator._render_chartjs("c-plain", "bar", ["A"], [{"label": "C", "data": [1]}])
    assert "chartAnnotations" not in plain
    assert "grace" not in plain


def test_render_chartjs_month_axis():
    creator = HTMLReportCreator()
    months = month_range(["2020-01", "2023-12"])
    result = creator._render_chartjs(
        "c-months", "bar", months, [{"label": "C", "data": [1] * len(months)}], month_axis=True
    )
    # Years at each January, horizontal, thinned by monthAxisTick instead of rotated
    assert "ticks: { autoSkip: false, maxRotation: 0, callback: monthAxisTick }" in result
    # gridlines only at the labelled years, not at every month
    assert "grid: { color: monthAxisGrid }" in result
    assert "minRotation: 45" not in result


def test_monthly_charts_use_the_month_axis(mock_data_collector, temp_dir):
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    for page, chart in (
        ("activity.html", "chart-commits-by-year-month"),
        ("authors.html", "chart-contributor-growth"),
    ):
        with open(os.path.join(temp_dir, page), encoding="utf-8") as f:
            html = f.read()
        script = html[html.index(f'<canvas id="{chart}" role="img"') :]
        script = script[: script.index("</script>")]
        assert "callback: monthAxisTick" in script, chart


def test_render_chartjs_lines_have_no_point_markers():
    creator = HTMLReportCreator()
    single = creator._render_chartjs(
        "c1", "line", ["X", "Y", "Z"], [{"label": "L", "data": [1, 2, 3]}]
    )
    multi = creator._render_chartjs(
        "c2",
        "line",
        ["X", "Y", "Z"],
        [{"label": "A", "data": [1, 2, 3]}, {"label": "B", "data": [2, 3, 4]}],
    )
    for result in (single, multi):
        assert '"pointRadius": 0' in result
        assert '"pointRadius": 2' not in result
        assert '"pointHoverRadius": 3' in result
        # Without markers, tooltips pick the nearest point
        assert "interaction: { mode: 'nearest', intersect: false }" in result
    bar = creator._render_chartjs("c3", "bar", ["X"], [{"label": "B", "data": [1]}])
    assert "interaction:" not in bar


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
    # no stretch is cut out of the axis, so the helpers leave every value alone
    assert "var gap = null;" in result
    assert "x: timeAxis(labels, gap)" in result
    assert "x: squeezeTime(gap, xs[i]), y: y" in result
    # Cumulative series hold their value until the next point
    assert '"stepped": true' in result
    assert "formatChartDate(stretchTime(gap, items[0].parsed.x))" in result


def test_render_chartjs_single_dataset_follows_theme():
    creator = HTMLReportCreator()
    result = creator._render_chartjs("chart-th", "bar", ["X"], [{"label": "C", "data": [1]}])
    assert '"themed": true' in result
    assert "applyChartTheme();" in result


def test_a_chart_box_says_that_its_chart_is_not_shown():
    # where scripts are blocked (as on Jenkins by default) the note is all that
    # is left of a chart, so it comes with every chart, ahead of the canvas
    result = HTMLReportCreator()._render_chartjs(
        "chart-note", "bar", ["X"], [{"label": "C", "data": [1]}]
    )
    assert f'">{CHART_NOTE}<canvas id="chart-note"' in result
    assert "Chart not shown" in CHART_NOTE
    assert "integration.html#blank-charts" in CHART_NOTE
    # such a page cannot open a new tab either
    assert "target=" not in CHART_NOTE
    # the chart that is built takes the note away
    assert "note.remove();" in CHART_SCRIPT


def test_the_hotspots_plot_says_that_it_is_not_shown(mock_data_collector, temp_dir):
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    content = _read_page(temp_dir, "hotspots.html")
    assert f'{CHART_NOTE}<canvas id="chart-hotspots"' in content


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

    # every page in one row, group by group, a divider before each group after the first
    row = re.search(r'<ul class="nav-pages">(.*?)</ul>', output)[1]
    assert re.findall(r'<li( class="nav-group-start")?><a href="([^"]+)">', row) == [
        ("", "index.html"),
        ("", "badges.html"),
        (' class="nav-group-start"', "authors.html"),
        ("", "ownership.html"),
        (' class="nav-group-start"', "hotspots.html"),
        ("", "files.html"),
        ("", "lines.html"),
        (' class="nav-group-start"', "activity.html"),
        ("", "history.html"),
        ("", "tags.html"),
    ]
    assert '<a href="index.html">General</a>' in row
    assert "AI Insights" not in output


def test_print_nav_with_ai():
    from unittest.mock import Mock

    creator = HTMLReportCreator()
    creator.data = Mock()
    creator.data.ai_summaries = {"index": {"summary": "test"}}

    f = StringIO()
    creator.print_nav(f)
    output = f.getvalue()

    # after the summary, in the overview's group
    row = re.search(r'<ul class="nav-pages">(.*?)</ul>', output)[1]
    assert re.findall(r'href="([^"]+)"', row)[:3] == [
        "index.html",
        "ai-insights.html",
        "badges.html",
    ]


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

    assert (
        '<li class="nav-group-start"><a href="authors.html" class="active" aria-current="page">'
        "Authors</a></li>"
    ) in output
    assert '<a href="index.html">General</a>' in output
    # once in the row of links and once in the menu a phone shows in its place
    assert output.count('aria-current="page"') == 2
    assert (
        '<details class="nav-menu"><summary><span class="nav-menu-label">Page</span> '
        "Authors</summary><ul>"
    ) in output
    # the menu has each group's name over its pages, every page once
    menu = output[output.index('<details class="nav-menu">') : output.index("</details>")]
    assert re.findall(r'<li class="nav-menu-heading" aria-hidden="true">([^<]+)</li>', menu) == [
        "Overview",
        "People",
        "Code",
        "Timeline",
    ]
    assert re.findall(r"<a [^>]*>([^<>]+)</a>", menu) == [label for _, label in NAV_PAGES]
    assert "nav-group-start" not in menu


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
        "hotspots.html",
        "history.html",
        "badges.html",
    ],
)
def test_each_page_marks_itself_current(mock_data_collector, temp_dir, page):
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    with open(os.path.join(temp_dir, page), encoding="utf-8") as f:
        content = f.read()
    assert f'<a href="{page}" class="active" aria-current="page">' in content
    # the row of links, and the menu that replaces it on a phone
    assert content.count('aria-current="page"') == 2


# ── HTMLReportCreator.create_index_html ──────────────────────────────────


def test_create_index_html(mock_data_collector, temp_dir):
    creator = HTMLReportCreator()
    creator.title = mock_data_collector.project_name
    creator.data = mock_data_collector
    creator.create_index_html(mock_data_collector, temp_dir)

    with open(f"{temp_dir}/index.html", encoding="utf-8") as f:
        html = f.read()

    # The repository's name heads the page, with the span of its history under
    # it; how the report was made is in the footer
    assert (
        '<div class="page-head"><h1>test-project</h1>'
        '<a href="badges.html">Badge for your README</a></div>'
        '<p class="page-meta">2022-12-01 &rarr; 2023-04-01 &middot; 3 months</p>'
    ) in html
    assert re.search(
        r"gitstats</a> \S+ &middot; \d{4}-\d\d-\d\d \d\d:\d\d:\d\d in \d+ s &middot; ", html
    )
    assert "</html>" in html

    # Headline numbers are stat tiles, with the old table's averages as notes
    assert '<dl class="stat-tiles" style="--cols: 6; --cols-md: 3; --cols-sm: 2">' in html
    assert html.count('<div class="stat-tile">') == 6
    assert '<dt>Commits</dt><dd class="stat-value">50</dd>' in html
    assert (
        '<span class="nowrap">12.5 per active day</span>&nbsp;&middot; '
        '<span class="nowrap">0.4 per day</span>'
    ) in html
    assert "16.7 commits per author" in html
    # Large counts use thousands separators (total_lines=2000, added=3000, removed=1000)
    assert '<dt>Lines of Code</dt><dd class="stat-value">2,000</dd>' in html
    assert '<span class="stat-added">+3,000</span> added' in html
    assert '<span class="stat-removed">−1,000</span> removed' in html
    assert "3 extensions" in html
    assert (
        '<span class="nowrap">of 120 days</span>&nbsp;&middot; <span class="nowrap">3.3%</span>'
        in html
    )
    # the newest tag dates the project; without tags the tile is the longest streak
    assert (
        '<dt>Latest Release</dt><dd class="stat-value">v1.1.0</dd>'
        '<dd class="stat-note"><span class="nowrap">2023-04-05</span>&nbsp;&middot; '
        '<span class="nowrap">2 tags</span></dd>'
    ) in html
    assert "Longest Streak" not in html

    # The old key/value table is gone: its rows live in the tiles and the meta line
    assert "Report Details" not in html
    assert "Total Commits" not in html
    assert "Project Age" not in html

    # Commits per year across the whole history
    assert (
        '<canvas id="chart-overview-yearly" role="img" aria-label="Bar chart of commits per '
        'year, 2023">'
    ) in html
    assert 'href="activity.html">Activity in detail &rarr;</a>' in html

    # Top contributors: rank, commits, share, and the share as a bar from 0 to
    # 100%, so the top author's bar is as long as their share
    assert (
        '<tr><td class="num rank">1</td><td>Alice Smith</td><td class="num">30</td>'
        '<td class="num">60.0%</td>'
        '<td class="share-cell"><span class="share-bar" aria-hidden="true">'
        '<span style="width: 60.0%"></span></span></td></tr>'
    ) in html
    assert '<span style="width: 30.0%">' in html  # Bob: 15 of all 50
    assert SHARE_SCALE_HEADER in html
    assert ">0</span><span>50%</span><span>100%</span>" in SHARE_SCALE_HEADER
    # all three authors are listed: there are no others to add up
    assert "share-rest" not in html
    assert "All 3 authors &rarr;" in html

    # Latest releases, newest first, next to the contributors
    assert '<div class="two-columns">' in html
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
    # drawn on the chart; the canvas is invisible to screen readers, so also in words
    assert (
        '<p class="section-note">6 commits in 3 years with commits; none from 2011 to 2013.</p>'
    ) in html


def test_index_single_empty_year_is_not_noted(mock_data_collector, temp_dir):
    mock_data_collector.commits_by_year = {2020: 1, 2022: 1}
    html = _render_index(mock_data_collector, temp_dir)
    assert "; none from" not in html
    assert '<p class="section-note">2 commits in 2 years with commits.</p>' in html


def test_index_without_tags_has_no_releases(mock_data_collector, temp_dir):
    mock_data_collector.tags = {}
    html = _render_index(mock_data_collector, temp_dir)
    assert "Latest releases" not in html
    assert "two-columns" not in html
    assert "Top contributors" in html


def test_author_html_marks_bots():
    assert author_html("Alice Smith") == "Alice Smith"
    # the badge replaces the "[bot]" suffix instead of repeating it
    assert author_html("dependabot[bot]") == (
        'dependabot <span class="badge" title="dependabot[bot]">bot</span>'
    )
    assert author_html("<Eve>") == "&lt;Eve&gt;"


def test_bot_badges_in_contributor_tables(mock_data_collector, temp_dir):
    bot = {**mock_data_collector.authors["Charlie Brown"]}
    mock_data_collector.authors = {**mock_data_collector.authors, "renovate[bot]": bot}
    mock_data_collector.get_authors.side_effect = lambda limit=None: [
        "Alice Smith",
        "Bob Jones",
        "renovate[bot]",
    ][:limit]
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    badge = 'renovate <span class="badge" title="renovate[bot]">bot</span>'
    with open(f"{temp_dir}/index.html", encoding="utf-8") as f:
        index = f.read()
    assert f'<tr><td class="num rank">3</td><td>{badge}</td>' in index  # Top Contributors
    # a bot's commits are not a person's work: its bar is grey
    row = index[index.index(f"<td>{badge}</td>") :]
    assert 'class="share-bar share-bar-muted"' in row[: row.index("</tr>")]
    with open(f"{temp_dir}/authors.html", encoding="utf-8") as f:
        assert f'<tr><td class="num rank">3</td><td>{badge}</td>' in f.read()  # List of Authors


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
        (4, "--cols: 4; --cols-md: 2; --cols-sm: 2"),
        # three on a phone: two, then the last one full width (not one per row)
        (3, "--cols: 3; --cols-md: 3; --cols-sm: 2; --span-sm: 2"),
        # five on a tablet: three, then two with the last spanning two columns
        (5, "--cols: 5; --cols-md: 3; --span-md: 2; --cols-sm: 2; --span-sm: 2"),
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
    """Files, Lines, Tags, Ownership, Hotspots and History open with stat tiles, not a bare <dl>."""
    HTMLReportCreator().create(mock_data_collector, temp_dir)

    def page(name):
        with open(os.path.join(temp_dir, name), encoding="utf-8") as f:
            return f.read()

    for name in (
        "files.html",
        "lines.html",
        "tags.html",
        "ownership.html",
        "hotspots.html",
        "history.html",
    ):
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
    assert '<dt>Latest</dt><dd class="stat-value">v1.1.0</dd>' in tags
    assert '<dd class="stat-note">2023-04-05</dd>' in tags
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
    assert "Month of year" in html
    assert "Commits by year/month" in html

    # The months lead, then coarse to fine: year, week, the daily rhythm
    order = ["Commits by year/month", "Commits by year", "Weekly activity", "Punch card"]
    positions = [html.index(f">{title}</a></h2>") for title in order]
    assert positions == sorted(positions)

    # Yearly activity duplicated Commits by Year; Hour of Day, Day of Week and
    # Hour of Week are merged into the punch card
    for gone in ("Yearly activity", "Hour of Day", "Day of Week", "Hour of Week"):
        assert f">{gone}</a></h2>" not in html
    for chart in ("chart-yearly-activity", "chart-hour-of-day", "chart-day-of-week"):
        assert f'<canvas id="{chart}"' not in html
    # ...but their anchors still exist, next to the sections that replaced them
    for anchor in ("yearly_activity", "hour_of_day", "day_of_week", "hour_of_week"):
        assert f'<span id="{anchor}"></span>' in html
    assert html.index('id="yearly_activity"') < html.index('id="commits_by_year"')
    assert html.index('id="hour_of_week"') < html.index('id="punch_card"')


def test_weekly_activity_labels_weeks_by_monday(mock_data_collector, monkeypatch):
    import datetime as real_datetime

    class FixedDatetime(real_datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 25, 12, 0)  # a Friday; its week starts on Mon 21 Sep

    monkeypatch.setattr("gitstats.report_creator.datetime.datetime", FixedDatetime)
    mock_data_collector.activity_by_year_week = {"2026-39": 7}  # the ISO week of 2026-09-21
    # the last commit in the same week
    mock_data_collector.last_commit_stamp = int(FixedDatetime(2026, 9, 22, 9, 0).timestamp())
    f = StringIO()
    HTMLReportCreator()._write_weekly_activity_section(f, mock_data_collector)
    html = f.getvalue()

    # Labels are the weeks' Mondays, not "2026-39" (which reads like a month),
    # without the year when all of them are in this one
    assert '"Feb 16", "Feb 23"' in html and '"Sep 21"]' in html
    assert '"2026-39"' not in html
    assert "Last 32 weeks, from the week of Feb 16, 2026 to the week of Sep 21, 2026." in html
    # The value for the current week is still found under its ISO week
    assert (
        '"data": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 7]'
        in html
    )


def test_weekly_activity_keeps_the_week_of_new_year_whole(mock_data_collector, monkeypatch):
    """Mon Dec 30, 2024 to Sun Jan 5, 2025 is one week, one bar: "%Y-%W"
    split it into 2024-53 and 2025-00, and the bar showed one of the two."""
    import datetime as real_datetime

    class FixedDatetime(real_datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 25, 12, 0)

    monkeypatch.setattr("gitstats.report_creator.datetime.datetime", FixedDatetime)
    mock_data_collector.last_commit_stamp = int(FixedDatetime(2025, 1, 2, 10, 0).timestamp())
    collector = GitDataCollector()
    for day in (30, 31, 31):
        collector._record_activity(real_datetime.datetime(2024, 12, day, 12, 0))
    collector._record_activity(real_datetime.datetime(2025, 1, 2, 12, 0))
    mock_data_collector.activity_by_year_week = collector.activity_by_year_week
    f = StringIO()
    HTMLReportCreator()._write_weekly_activity_section(f, mock_data_collector)
    html = f.getvalue()
    assert '"Dec 23, 2024", "Dec 30, 2024"]' in html
    assert html.count(", 4]") == 1  # the last bar: the four commits of that week


def test_weekly_activity_ends_at_the_last_commit(mock_data_collector, monkeypatch):
    import datetime as real_datetime

    class FixedDatetime(real_datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 25, 12, 0)

    monkeypatch.setattr("gitstats.report_creator.datetime.datetime", FixedDatetime)
    # nothing since May 2021: 32 weeks up to today would all be empty
    mock_data_collector.last_commit_stamp = int(FixedDatetime(2021, 5, 1, 10, 0).timestamp())
    mock_data_collector.activity_by_year_week = {"2021-16": 3}  # the week of 2021-04-19
    f = StringIO()
    HTMLReportCreator()._write_weekly_activity_section(f, mock_data_collector)
    html = f.getvalue()
    assert (
        "The 32 weeks up to the last commit, from the week of Sep 21, 2020 to the week of "
        "Apr 26, 2021: there has been none since."
    ) in html
    assert '"data": [' + "0, " * 30 + "3, 0]" in html
    # weeks of other years carry their year, in the axis and in the tooltip
    assert '["Sep 21, 2020", "Sep 28, 2020", ' in html
    assert '"Dec 28, 2020", "Jan 4, 2021", ' in html
    assert '"Apr 26, 2021"]' in html
    # without a last commit to go by, the weeks end today
    mock_data_collector.last_commit_stamp = 0
    f = StringIO()
    HTMLReportCreator()._write_weekly_activity_section(f, mock_data_collector)
    assert "Last 32 weeks" in f.getvalue()


def test_activity_summary_and_section_links(mock_data_collector, temp_dir):
    creator = HTMLReportCreator()
    creator.title = mock_data_collector.project_name
    creator.data = mock_data_collector
    creator.create_activity_html(mock_data_collector, temp_dir)
    with open(f"{temp_dir}/activity.html", encoding="utf-8") as f:
        html = f.read()

    # 50 commits, 4 active days, streak 4, busiest hour 14 (15 commits), busiest day Wed (12),
    # as stat tiles right under the heading like every other page
    assert '<h1>Activity</h1><dl class="stat-tiles"' in html
    for tile in (
        '<dt>Commits</dt><dd class="stat-value">50</dd><dd class="stat-note">on 4 active days</dd>',
        '<dt>Longest Streak</dt><dd class="stat-value">4 days</dd>',
        '<dt>Busiest Hour</dt><dd class="stat-value">14:00</dd><dd class="stat-note">15 commits</dd>',
        '<dt>Busiest Day</dt><dd class="stat-value">Wednesday</dd>',
    ):
        assert tile in html, tile
    assert 'class="page-meta"' not in html
    # Every "On this page" link points at a section heading on the page
    toc = re.search(r'<nav class="page-toc" aria-label="On this page">(.*?)</nav>', html).group(1)
    targets = re.findall(r'href="#([^"]+)"', toc)
    assert len(targets) == 6
    for target in targets:
        assert f'<h2 id="{target}">' in html, target
    assert "Longest Streak:" not in html  # folded into the summary line


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
    # Day totals with their share (Mon: 8 of 50) and a bar against the busiest day (Wed: 12)
    assert (
        '<td class="num punch-total">8 (16.0%)<span class="share-bar share-bar-inline" '
        'aria-hidden="true"><span style="width: 66.7%"></span></span></td>'
    ) in html
    # Commits per hour as bars above the grid: 14:00 is the busiest (15 of 50) -> 40px
    assert (
        '<td title="14:00 &middot; 15 commits &middot; 30.0%"><div class="punch-vbar">'
        '<span class="punch-vbar-value">15</span>'
        '<span class="punch-vbar-fill" style="height: 40px"></span></div></td>'
    ) in html
    # 16:00 has 8 commits -> 21px; an hour without commits has no bar
    assert '<span class="punch-vbar-fill" style="height: 21px">' in html
    assert (
        '<span class="punch-vbar-value"></span><span class="punch-vbar-fill" style="height: 0px">'
        in html
    )
    # The bar row sits between the hour labels and the first weekday
    assert html.index('class="punch-hour-bars"') < html.index("<tr><th>Mon</th>")
    assert '<p class="heat-legend">Fewer' in html


def test_activity_month_of_year_and_timezones(mock_data_collector, temp_dir):
    creator = HTMLReportCreator()
    creator.title = mock_data_collector.project_name
    creator.data = mock_data_collector
    creator.create_activity_html(mock_data_collector, temp_dir)
    with open(f"{temp_dir}/activity.html", encoding="utf-8") as f:
        html = f.read()

    # Month of Year: named months, counts drawn on the bars, share in the tooltip, no table
    month = html[html.index('id="month_of_year"') : html.index('id="commits_by_timezone"')]
    assert '"Jan", "Feb", "Mar"' in month
    assert 'gsAnnotations: {"values": true}' in month
    # "1 commit", not "1 commits"
    assert (
        "(item.parsed.y === 1 ? ' commit (' : ' commits (') + "
        "(100 * item.parsed.y / total).toFixed(1)"
    ) in month
    assert "<table" not in month

    # Timezones west to east as bars: -0500 (15), +0000 (5), +0800 (30) of 50
    assert (
        '<tr><td class="nowrap">UTC-05:00</td><td class="num">15</td><td class="num">30.0%</td>'
        '<td class="share-cell"><span class="share-bar" aria-hidden="true">'
        '<span style="width: 50.0%"></span></span></td></tr>'
    ) in html
    assert html.index("UTC-05:00") < html.index("UTC+00:00") < html.index("UTC+08:00")
    assert '<table class="heat">' not in html

    # The two sections sit side by side
    assert '<div class="two-columns"><section>' in html
    assert html.index('<div class="two-columns"><section>') < html.index('id="month_of_year"')


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
    assert html.index('<canvas id="chart-commits-by-year-month"') < html.index(summary)


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
    assert "Top author per year and month" in html
    assert "Commits by domain" in html
    assert "example.com" in html
    # Domains are data cells (not uppercased header cells) in a bar table
    assert "<tr><td>example.com</td>" in html
    assert "<th>example.com</th>" not in html
    assert (
        '<tr><th>Domain</th><th class="num">Commits</th><th class="num">Share</th>'
        '<th class="unsortable"><span class="visually-hidden">Bar</span></th></tr>' in html
    )
    assert "chart-domains" not in html
    assert "Contributor growth" in html


def test_render_chartjs_highlight_top_series():
    creator = HTMLReportCreator()
    datasets = [{"label": f"A{i}", "data": [i]} for i in range(7)]
    result = creator._render_chartjs("chart-hl", "line", ["X"], datasets, highlight=5)
    # The first 5 keep distinct colors; the rest are grey and drawn behind
    assert result.count(HTMLReportCreator.OTHER_SERIES_COLOR) == 4  # border + background x 2
    assert '"label": "A4", "data": [4], "borderColor": getCSSVar(\'--series-5\')' in result
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
    assert '<canvas id="chart-commits-by-author"' not in html
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
    assert (
        '<p class="section-note">Lines added over time by each author; '
        "the top 5 are in color, the rest in grey.</p>"
    ) in html


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


def test_contributor_timeline_places_a_month_inside_the_collapsed_stretch(mock_data_collector):
    """The stretch is squeezed into its slot, not cut out: a month inside it
    lands inside the band, in proportion, never past it."""
    months = {f"2010-{m:02d}": 2 for m in range(1, 13)}
    months.update({f"2013-{m:02d}": 3 for m in range(1, 13)})
    mock_data_collector.commits_by_month = months
    mock_data_collector.author_of_month = {m: {"Alice Smith": n} for m, n in months.items()}
    # a commit the monthly totals do not have, in the quiet 2011-01 .. 2012-12
    mock_data_collector.author_of_month["2011-07"] = {"Bob Jones": 1}
    html = HTMLReportCreator()._contributor_timeline_html(
        mock_data_collector, ["Alice Smith", "Bob Jones"]
    )
    # 48 months, the 24 quiet ones in one slot of 25: the band is at 48%, 4% wide
    assert '<span class="timeline-gap is-collapsed" style="left: 48.000%; width: 4.000%" ' in html
    # 2011-07 is 6.5 months into the 24 of the stretch: that far into the slot,
    # (12 + 6.5 / 24) / 25 of the axis
    assert 'aria-label="Bob Jones: 15 commits, 2011-07 to 2011-07"' in html
    assert 'class="timeline-mark" style="left: 49.083%;' in html


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
    # the files that change most are on the Hotspots page, next to this one
    assert "Most changed files" not in html
    assert 'id="churn"' not in html
    assert (
        '<p class="more-link"><a href="hotspots.html">'
        "The files that change most, by size and by changes &rarr;</a></p>"
    ) in html


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


def test_create_ai_insights_keeps_no_markup_a_committer_could_steer(mock_data_collector, temp_dir):
    """The model is asked for HTML about author names and commit subjects:
    a script in its answer, or markup in an error, does not reach the page."""
    data = mock_data_collector
    data.ai_summaries = {
        "index": {"summary": "<p>ok</p><script src=https://evil.example/x.js></script>"},
        "activity": {"error": "500 Server Error: <img src=x onerror=alert(1)>"},
        "lines": {"summary": '<ul><li onclick="steal()"><strong>Lines</strong> grew</li></ul>'},
    }
    creator = HTMLReportCreator()
    creator.title = data.project_name
    creator.data = data
    creator.create_ai_insights_html(data, temp_dir)

    with open(f"{temp_dir}/ai-insights.html", encoding="utf-8") as f:
        page = f.read()

    assert "evil.example" not in page
    assert "<img" not in page
    assert "steal()" not in page
    assert "<p>ok</p>" in page
    assert "<ul><li><strong>Lines</strong> grew</li></ul>" in page
    assert "500 Server Error: &lt;img src=x onerror=alert(1)&gt;" in page


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


def test_get_ai_summary_html_keeps_no_markup_a_committer_could_steer(mock_data_collector):
    creator = HTMLReportCreator()
    creator.data = mock_data_collector
    mock_data_collector.ai_summaries = {
        "index": {"summary": "<p>ok</p><script>alert(1)</script>"},
        "activity": {"error": "<img src=x onerror=alert(1)>"},
    }
    assert "<p>ok</p>" in creator.get_ai_summary_html("index")
    assert "<script>" not in creator.get_ai_summary_html("index")
    error = creator.get_ai_summary_html("activity")
    assert "<img" not in error
    assert "&lt;img src=x onerror=alert(1)&gt;" in error


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
        "hotspots.html",
        "history.html",
        "badges.html",
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


def test_commits_by_year_chart_first_table_folded(mock_data_collector, temp_dir):
    """Like the monthly section: the chart leads, the yearly table is folded below it."""
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    with open(os.path.join(temp_dir, "activity.html"), encoding="utf-8") as f:
        content = f.read()
    section = content[content.index('id="commits_by_year"') : content.index('id="weekly_activity"')]
    assert section.index('id="chart-commits-by-year"') < section.index("<details")
    assert (
        '<details class="table-details"><summary>Table: commits and lines per year '
        "(1 year with commits)</summary>"
    ) in section
    assert "table-with-chart" not in content


def test_create_all_pages_with_ai(mock_data_collector_with_ai, temp_dir):
    creator = HTMLReportCreator()
    creator.create(mock_data_collector_with_ai, temp_dir)

    assert os.path.exists(f"{temp_dir}/ai-insights.html")


def test_create_copies_static_files(mock_data_collector, temp_dir):
    creator = HTMLReportCreator()
    creator.create(mock_data_collector, temp_dir)

    for fname in ("sortable.js", "chart.umd.min.js", "gitstats.css"):
        assert os.path.exists(f"{temp_dir}/{fname}"), f"Missing static file: {fname}"
    # Sort arrows are drawn by CSS now; the old GIFs are no longer shipped
    assert not any(name.endswith(".gif") for name in os.listdir(temp_dir))
    with open(f"{temp_dir}/sortable.js", "rb") as f:
        sortable = f.read()
    assert b"<img" not in sortable
    assert b'arrow.setAttribute("data-sort", "none")' in sortable


def test_numeric_columns_are_marked(mock_data_collector, temp_dir):
    """Counts, percentages and spans carry class="num" so CSS right-aligns them."""
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    with open(os.path.join(temp_dir, "authors.html"), encoding="utf-8") as f:
        authors = f.read()
    # Alice Smith: 30 commits (60%) with a full-width share bar, +2,000 / -500
    assert (
        '<tr><td class="num rank">1</td><td>Alice Smith</td><td class="num">30 (60.0%)'
        '<span class="share-bar share-bar-inline" aria-hidden="true">'
        '<span style="width: 100.0%"></span></span></td>'
        '<td class="num stat-added">2,000</td><td class="num stat-removed">500</td>'
    ) in authors
    assert '<span style="width: 50.0%">' in authors  # Bob: 15 of Alice's 30
    assert '<th class="num">Commits (%)</th>' in authors
    assert '<th class="num">Age</th>' in authors
    # Text columns stay left-aligned
    assert "<th>First commit</th>" in authors

    with open(os.path.join(temp_dir, "files.html"), encoding="utf-8") as f:
        files = f.read()
    assert '<th class="num">Files</th><th class="num">Lines</th>' in files
    assert '<tr><td>py</td><td class="num">10</td>' in files


def test_authors_summary_and_folded_tables(mock_data_collector, temp_dir):
    creator = HTMLReportCreator()
    creator.title = mock_data_collector.project_name
    creator.data = mock_data_collector
    creator.create_authors_html(mock_data_collector, temp_dir)
    with open(f"{temp_dir}/authors.html", encoding="utf-8") as f:
        html = f.read()

    # 3 authors, all active and new in the 12 months to 2023-04-01; Alice (60%) and
    # Bob (30%) wrote 90% of commits; no bots
    assert '<h1>Authors</h1><dl class="stat-tiles"' in html
    for tile in (
        '<dt>Authors</dt><dd class="stat-value">3</dd><dd class="stat-note">no bot accounts</dd>',
        '<dt>Active Authors</dt><dd class="stat-value">3</dd>',
        '<dt>New Authors</dt><dd class="stat-value">3</dd>',
        '<dt>Top 2 Authors</dt><dd class="stat-value">90.0%</dd>',
    ):
        assert tile in html, tile
    # One section for the top author of each year (shown) and month (folded away);
    # the old Author of Month / Year anchors still land on it
    start = html.index('id="author_of_month"')
    heading = html.index("<h2", start)
    section = html[start : html.index("<h2", heading + 1)]
    assert 'id="author_of_year"' in section
    assert section.count("<h2") == 1
    assert section.index('id="aoy"') < section.index("<details")
    months = len(mock_data_collector.author_of_month)
    assert (
        '<details class="table-details"><summary>Table: top author of each month '
        f"({months} months with commits)</summary>"
    ) in section
    assert section.index("<details") < section.index('id="aom"')
    assert html.count("</table></div></details>") == 1


def test_authors_summary_counts_bots(mock_data_collector):
    mock_data_collector.get_authors.side_effect = lambda limit=None: [
        "Alice Smith",
        "renovate[bot]",
        "dependabot[bot]",
    ][:limit]
    mock_data_collector.get_author_info.side_effect = lambda a: {
        "commits_frac": 40.0,
        "date_first": "2021-01-01",
        "date_last": "2023-03-01",
    }
    summary = HTMLReportCreator()._authors_summary_html(mock_data_collector)
    assert '<dd class="stat-value">3</dd><dd class="stat-note">incl. 2 bot accounts</dd>' in summary
    # active since 2022-04-01 (a year before the last commit), none new
    assert '<dt>Active Authors</dt><dd class="stat-value">3</dd>' in summary
    assert '<dt>New Authors</dt><dd class="stat-value">0</dd>' in summary
    assert '<dt>Top 2 Authors</dt><dd class="stat-value">80.0%</dd>' in summary


def test_small_formatting_fixes(mock_data_collector, temp_dir):
    HTMLReportCreator().create(mock_data_collector, temp_dir)

    def page(name):
        with open(os.path.join(temp_dir, name), encoding="utf-8") as f:
            return f.read()

    # Author span is compact, with the exact day count on hover (Alice: 150 days)
    # the age sorts by its days, which its tooltip gives
    assert '<td class="nowrap num" title="150 days" data-sort="150">5 mo</td>' in page(
        "authors.html"
    )
    # Average file size in readable units (50000 bytes / 25 files)
    assert '<dt>Average File Size</dt><dd class="stat-value">2.0 KB</dd>' in page("files.html")
    # No cell carries a doubled "heat heat heatN" class
    activity = page("activity.html")
    assert "heat heat heat" not in activity
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

    # Bob alone is primary owner of two of the three files: more than half
    assert result["bus_factor"] == 1
    assert result["bus_factor_authors"] == ["Bob"]
    assert result["bus_factor_files"] == 2


def test_compute_code_ownership_empty():
    assert compute_code_ownership({}) == {
        "files": [],
        "authors": [],
        "total_files": 0,
        "single_owner_files": 0,
        "bus_factor": 0,
        "bus_factor_authors": [],
        "bus_factor_files": 0,
    }


def test_bus_factor_counts_owners_until_they_hold_more_than_half():
    # Ann owns four files, Ben three, Cy two, Di one: ten in all
    author_files = {
        "Ann": {f"a{i}.py": 5 for i in range(4)},
        "Ben": {f"b{i}.py": 5 for i in range(3)},
        "Cy": {f"c{i}.py": 5 for i in range(2)},
        "Di": {"d0.py": 5},
    }
    result = compute_code_ownership(author_files)
    # Ann's four are not more than half of ten, Ann's and Ben's seven are
    assert result["bus_factor"] == 2
    assert result["bus_factor_authors"] == ["Ann", "Ben"]
    assert result["bus_factor_files"] == 7

    # exactly half is not more than half: two files, one owner each
    even = compute_code_ownership({"Ann": {"a.py": 1}, "Ben": {"b.py": 1}})
    assert even["bus_factor"] == 2
    assert even["bus_factor_files"] == 2

    # a file only bots have changed has no owner, and is not counted
    bots = compute_code_ownership({"Ann": {"a.py": 1}, "dependabot[bot]": {"uv.lock": 9}})
    assert (bots["total_files"], bots["bus_factor"]) == (1, 1)


def test_ownership_page_renders(mock_data_collector, temp_dir):
    creator = HTMLReportCreator()
    creator.create(mock_data_collector, temp_dir)

    with open(f"{temp_dir}/ownership.html", encoding="utf-8") as f:
        content = f.read()

    assert "Code Ownership" in content
    assert "Bus factor risk" in content
    # Alice and Bob are primary owner of two files each: neither holds more than half
    assert (
        '<dt>Bus Factor</dt><dd class="stat-value">2</dd>'
        '<dd class="stat-note">2 authors are primary owner of 4 of 4 files</dd>'
    ) in content
    assert content.index("<dt>Files Tracked</dt>") < content.index("<dt>Bus Factor</dt>")
    assert content.index("<dt>Bus Factor</dt>") < content.index("<dt>Single-Owner Files</dt>")
    assert "The <strong>bus factor</strong> is the smallest number of people" in content
    # solo_alice.py is only touched by Alice -> appears as a single-owner file
    assert "solo_alice.py" in content
    assert "Alice Smith" in content
    assert "</html>" in content
    # File paths are set in monospace
    assert '<td class="path">solo_alice.py</td>' in content


def test_file_paths_are_monospace_cells(mock_data_collector, temp_dir):
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    with open(f"{temp_dir}/ownership.html", encoding="utf-8") as f:
        ownership = f.read()
    assert ownership.count('<td class="path">') >= 2  # single-owner and shared tables


def test_file_tables_name_their_cells_for_phones(mock_data_collector, temp_dir):
    """On a phone a row of files is two lines: the path, then the other cells,
    each named after its column by a data-label."""
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    expected = {
        "hotspots.html": {"hotspots": ["Lines", "Changes", "Authors", "Score"]},
        "ownership.html": {
            "ownership-busfactor": ["Sole owner", "Commits"],
            "ownership-shared": ["Contributors", "Primary owner", "Owner share"],
        },
    }
    for page, tables in expected.items():
        with open(f"{temp_dir}/{page}", encoding="utf-8") as f:
            html_text = f.read()
        for table_id, labels in tables.items():
            tag = re.search(rf'<table class="([^"]*)" id="{table_id}">', html_text)
            assert tag, table_id
            assert "file-table" in tag.group(1).split(), table_id
            rows = html_text[tag.end() : html_text.index("</table>", tag.end())].split("</tr>")
            header, first = rows[0], rows[1]
            # the path leads the row and needs no name
            assert first.startswith('<tr><td class="path">'), table_id
            assert re.findall(r'data-label="([^"]+)"', first) == labels, table_id
            # and the names are the headings of the columns they sit under
            headings = [h for h in re.findall(r"<th[^>]*>([^<]*)</th>", header) if h]
            assert [h.lower() for h in headings] == ["file", *(name.lower() for name in labels)]

    # a table whose rows are not files keeps its columns
    with open(f"{temp_dir}/files.html", encoding="utf-8") as f:
        files = f.read()
    extensions = re.search(r'<table class="([^"]*)" id="ext">', files)
    assert extensions and "file-table" not in extensions.group(1)


def test_file_tables_stack_on_phones():
    css_path = os.path.join(os.path.dirname(__file__), "..", "gitstats", "gitstats.css")
    with open(css_path, encoding="utf-8") as f:
        css = f.read()
    start = css.index("table.file-table,")
    # only under the phone breakpoint: wider screens keep the columns
    assert css[:start].rstrip().endswith("@media (max-width: 560px) {")
    rules = css[start:]
    assert "table.file-table td.path {\n\t\tflex: 0 0 100%;" in rules
    assert "content: attr(data-label);" in rules
    # the header row turns into the sort controls
    assert 'content: "Sort by";' in rules
    assert "table.file-table th.unsortable {\n\t\tdisplay: none;" in rules
    # and the first column is no longer pinned, as it is in tables that scroll
    unpinned = rules[rules.index(".table-scroll table.file-table tr > th") :]
    assert "position: static;" in unpinned[: unpinned.index("}")]


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


# ── Hotspots ─────────────────────────────────────────────────────────────


def _hotspots_html(data, path):
    creator = HTMLReportCreator()
    creator.data = data
    creator.title = "t"
    creator.create_hotspots_html(data, path)
    return _read_page(path, "hotspots.html")


def _hotspot_points(page):
    data = page.split('<script type="application/json" id="hotspot-data">', 1)[1]
    return json.loads(data.split("</script>", 1)[0])


def test_compute_hotspots_stats():
    hotspots = compute_hotspots(
        {
            "big_busy.py": {"lines": 400, "churn": 15, "score": 300.0},
            "small_busy.py": {"lines": 30, "churn": 12, "score": 65.73},
            "big_calm.py": {"lines": 900, "churn": 1, "score": 30.0},
            "small_calm.py": {"lines": 10, "churn": 1, "score": 3.16},
            # nothing to place on a logarithmic axis: no lines, or never changed
            "logo.png": {"lines": 0, "churn": 4, "score": 0.0},
            "vendored.py": {"lines": 5000, "churn": 0, "score": 0.0},
        }
    )

    # highest score first, rounded to one decimal
    assert [fs["path"] for fs in hotspots["files"]] == [
        "big_busy.py",
        "small_busy.py",
        "big_calm.py",
        "small_calm.py",
    ]
    assert hotspots["files"][1] == {
        "path": "small_busy.py",
        "lines": 30,
        "churn": 12,
        "score": 65.7,
    }
    # upper medians of (10, 30, 400, 900) and (1, 1, 12, 15)
    assert hotspots["median_lines"] == 400
    assert hotspots["median_churn"] == 12


def test_compute_hotspots_breaks_score_ties_by_path():
    files = {name: {"lines": 100, "churn": 2, "score": 20.0} for name in ("b.py", "a.py", "c.py")}
    assert [fs["path"] for fs in compute_hotspots(files)["files"]] == ["a.py", "b.py", "c.py"]


def test_compute_hotspots_empty():
    assert compute_hotspots({}) == {
        "files": [],
        "median_lines": 0,
        "median_churn": 0,
    }


def test_hotspots_page_renders(mock_data_collector, temp_dir):
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    content = _read_page(temp_dir, "hotspots.html")

    assert "<h1>Hotspots</h1>" in content
    # the upper medians of the four mocked files: 120 lines, 10 changes
    assert (
        '<dt>Files Analyzed</dt><dd class="stat-value">4</dd>'
        '<dd class="stat-note">with lines and at least one change</dd>'
    ) in content
    assert '<dt>Median File Size</dt><dd class="stat-value">120 lines</dd>' in content
    assert '<dt>Median Changes</dt><dd class="stat-value">10 commits</dd>' in content

    # the scatter plot: every file as [path, lines, churn, score], highest score first.
    # The quadrants are named on the plot, so there is no legend to leave room for
    assert '<div class="hotspot-plot"><div class="chart-box" style="--chart-ratio: 1.6">' in content
    assert (
        '<canvas id="chart-hotspots" role="img" aria-label="Scatter plot of 4 files by size in '
        'lines and number of changes, both on logarithmic scales"></canvas>'
    ) in content
    assert _hotspot_points(content) == {
        "medianLines": 120,
        "medianChurn": 10,
        "leastLines": 30,
        "leastChurn": 2,
        "points": [
            ["main.py", 400, 15, 300.0],
            ["utils.py", 120, 10, 109.5],
            ["setup.py", 60, 8, 62.0],
            ["Dockerfile", 30, 2, 11.0],
        ],
        "numbered": 4,
    }

    # the highest scores next to the plot, numbered as on it; the files at or
    # above both medians are the ones in color
    top = content[content.index('<div class="hotspot-top">') :]
    top = top[: top.index("</ol>")]
    assert re.findall(r'<span class="hotspot-rank([^"]*)">(\d+)</span>', top) == [
        (" numbered hot", "1"),
        (" numbered hot", "2"),
        (" numbered", "3"),
        (" numbered", "4"),
    ]
    assert (
        '<span class="hotspot-file"><span class="path">main.py</span>'
        '<span class="hotspot-numbers">400 lines &middot; 15 changes</span></span>'
    ) in top
    assert "The 4 highest scores are numbered as in the list." in content

    # the table ranks every file by score, with a bar scaled to the top score
    assert "Top hotspots</a></h2>" in content
    table = content[
        content.index('<table class="sortable share-table file-table" id="hotspots">') :
    ]
    table = table[: table.index("</table>")]
    assert re.findall(r'<td class="path"[^>]*>([^<]+)</td>', table) == [
        "main.py",
        "utils.py",
        "setup.py",
        "Dockerfile",
    ]
    assert (
        '<tr><td class="path">utils.py</td><td class="num" data-label="Lines">120</td>'
        '<td class="num" data-label="Changes">10</td>'
        '<td class="num" data-label="Authors">2</td>'
        '<td class="num" data-label="Score">109.5</td><td class="share-cell"><span class="share-bar" '
        'aria-hidden="true"><span style="width: 36.5%"></span></span></td></tr>'
    ) in table
    # no file is called critical: half of them are above each median anyway
    assert "ritical" not in content
    assert "</html>" in content


def test_hotspots_table_counts_the_authors_of_each_file(mock_data_collector, temp_dir):
    """As the Code Ownership page counts them, so the two pages agree."""
    content = _hotspots_html(mock_data_collector, temp_dir)
    table = content[content.index('id="hotspots">') :]
    table = table[: table.index("</table>")]

    assert (
        '<th class="num">Changes</th><th class="num">Authors</th><th class="num">Score</th>'
    ) in table
    authors = dict(
        re.findall(r'<td class="path"[^>]*>([^<]+)</td>.*?data-label="Authors">(\d+)</td>', table)
    )
    # main.py: Alice, Bob and Charlie; setup.py: Bob; nobody on record for Dockerfile
    assert authors == {"main.py": "3", "utils.py": "2", "setup.py": "1", "Dockerfile": "0"}

    # a hotspot only one person has changed is flagged; the flag is drawn by CSS
    # from the attribute, so the cell's text, which the table sorts by, is the path
    assert (
        '<td class="path" data-tag="sole owner" '
        'title="Only one person has changed this file">setup.py</td>'
    ) in table
    assert table.count("data-tag=") == 1
    assert "sole owner</td>" not in table
    assert '<a href="ownership.html">Code Ownership</a>' in content

    # only the files that still exist count, as on the Code Ownership page
    mock_data_collector.head_files = ["main.py", "utils.py", "setup.py", "Dockerfile"]
    mock_data_collector.author_files["Dana"] = {"gone.py": 3, "setup.py": 1}
    content = _hotspots_html(mock_data_collector, temp_dir)
    assert 'data-tag="sole owner"' not in content  # setup.py has two authors now


def test_hotspots_table_without_ownership_data_has_no_authors_column(mock_data_collector, temp_dir):
    mock_data_collector.author_files = {}
    content = _hotspots_html(mock_data_collector, temp_dir)
    assert '<th class="num">Authors</th>' not in content
    assert 'data-label="Authors"' not in content
    assert "<strong>Authors</strong>" not in content
    assert "data-tag" not in content
    assert (
        '<td class="num" data-label="Changes">10</td><td class="num" data-label="Score">109.5</td>'
    ) in content


def test_path_flag_is_drawn_by_css():
    css_path = os.path.join(os.path.dirname(__file__), "..", "gitstats", "gitstats.css")
    with open(css_path, encoding="utf-8") as f:
        css = f.read()
    rule = css[css.index("td.path[data-tag]::after {") :]
    rule = rule[: rule.index("}")]
    assert "content: attr(data-tag);" in rule
    assert "color: var(--orange-strong);" in rule


def test_hotspots_chart_follows_the_theme(mock_data_collector, temp_dir):
    """Colors come from the CSS variables, so the chart switches with the theme."""
    page = _hotspots_html(mock_data_collector, temp_dir)
    script = page.split('id="hotspot-data"', 1)[1].split("<script>", 1)[1]
    script = script[: script.index("</script>")]
    assert "getCSSVar('--series-' + " in script
    assert "getCSSVar('--border-strong')" in script
    assert "applyChartTheme();" in script
    assert "series: q[1]" in script  # read by applyChartTheme() on a theme switch
    assert not re.search(r"#[0-9a-fA-F]{6}\b|rgba?\(", script)


def test_hotspots_page_counts_against_the_current_tree(mock_data_collector, temp_dir):
    mock_data_collector.head_files = ["main.py", "utils.py", "setup.py", "Dockerfile", "logo.png"]
    page = _hotspots_html(mock_data_collector, temp_dir)
    assert (
        '<dt>Files Analyzed</dt><dd class="stat-value">4</dd>'
        '<dd class="stat-note">of 5 in the current tree</dd>'
    ) in page


def test_hotspots_page_empty_state(mock_data_collector, temp_dir):
    """The page is always written, since the nav links to it."""
    mock_data_collector.hotspot_files = {}
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    content = _read_page(temp_dir, "hotspots.html")

    assert "No hotspot data available" in content
    assert '<a href="hotspots.html" class="active" aria-current="page">Hotspots</a>' in content
    assert "chart-hotspots" not in content
    assert "</html>" in content


def test_hotspots_page_without_usable_data(mock_data_collector, temp_dir):
    """Data written before hotspots existed, or files that cannot be placed."""
    mock_data_collector.hotspot_files = None
    assert "No hotspot data available" in _hotspots_html(mock_data_collector, temp_dir)

    mock_data_collector.hotspot_files = {"logo.png": {"lines": 0, "churn": 3, "score": 0.0}}
    assert "No hotspot data available" in _hotspots_html(mock_data_collector, temp_dir)


def test_hotspots_page_escapes_paths(mock_data_collector, temp_dir):
    mock_data_collector.hotspot_files = {
        "we<i>rd</script>.py": {"lines": 500, "churn": 9, "score": 201.2},
        "plain.py": {"lines": 10, "churn": 2, "score": 6.3},
    }
    content = _hotspots_html(mock_data_collector, temp_dir)

    # HTML-escaped in the table, and no "<" at all in the data the chart reads
    assert '<td class="path">we&lt;i&gt;rd&lt;/script&gt;.py</td>' in content
    assert "we<i>rd" not in content
    data = content.split('id="hotspot-data">', 1)[1].split("</script>", 1)[0]
    assert "<" not in data
    assert json.loads(data)["points"][0][0] == "we<i>rd</script>.py"


def test_hotspots_table_shows_ten_and_folds_the_rest(mock_data_collector, temp_dir):
    mock_data_collector.hotspot_files = {
        f"f{i:02d}.py": {"lines": 100, "churn": 30 - i, "score": 10.0 * (30 - i)} for i in range(10)
    }
    # ten files or fewer are all shown, with nothing folded away
    content = _hotspots_html(mock_data_collector, temp_dir)
    assert content.count('<td class="path">') == 10
    assert '<details class="table-details"' not in content

    mock_data_collector.hotspot_files = {
        f"f{i:03d}.py": {"lines": 100, "churn": 400 - i, "score": 10.0 * (400 - i)}
        for i in range(300)
    }
    content = _hotspots_html(mock_data_collector, temp_dir)
    shown = content[content.index('id="hotspots"') :]
    shown = shown[: shown.index("</table>")]
    assert shown.count("<tr>") == 11  # header + the ten highest-scoring
    assert "f009.py" in shown
    assert "f010.py" not in shown
    assert (
        '<details class="table-details">'
        "<summary>Table: the 100 highest-scoring of 300 files</summary>"
        '<div class="table-scroll"><table class="sortable share-table file-table" '
        'id="hotspots-all">'
    ) in content
    folded = content[content.index('id="hotspots-all"') :]
    assert folded[: folded.index("</table>")].count("<tr>") == 101

    mock_data_collector.hotspot_files = {
        f"f{i:02d}.py": {"lines": 100, "churn": 60 - i, "score": 10.0 * (60 - i)} for i in range(40)
    }
    content = _hotspots_html(mock_data_collector, temp_dir)
    assert "<summary>Table: all 40 files</summary>" in content


def test_hotspots_page_shows_the_share_of_the_top_ten(mock_data_collector, temp_dir):
    """How much of the total score the ten files in the table hold."""
    mock_data_collector.hotspot_files = {
        f"f{i:02d}.py": {"lines": 100, "churn": 20 - i, "score": 10.0 * (20 - i)} for i in range(20)
    }
    content = _hotspots_html(mock_data_collector, temp_dir)
    # scores 200, 190, ... 10: the top ten hold 1,550 of 2,100
    assert (
        '<dt>Top 10 Files</dt><dd class="stat-value">73.8%</dd>'
        '<dd class="stat-note">of the total hotspot score</dd>'
    ) in content
    # second of four tiles, after the number of files
    assert content.index("<dt>Files Analyzed</dt>") < content.index("<dt>Top 10 Files</dt>")
    assert content.index("<dt>Top 10 Files</dt>") < content.index("<dt>Median File Size</dt>")


def test_hotspots_page_leaves_the_share_out_when_it_says_nothing(mock_data_collector, temp_dir):
    """With ten files or fewer the table holds them all, so the share is 100%."""
    mock_data_collector.hotspot_files = {
        f"f{i:02d}.py": {"lines": 100, "churn": 10 - i, "score": 10.0 * (10 - i)} for i in range(10)
    }
    content = _hotspots_html(mock_data_collector, temp_dir)
    assert "Files</dt>" not in content
    assert content.count('<div class="stat-tile">') == 3

    # nor when no file has a score to take a share of
    mock_data_collector.hotspot_files = {
        f"f{i:02d}.py": {"lines": 100, "churn": 1, "score": 0.0} for i in range(12)
    }
    assert "Files</dt>" not in _hotspots_html(mock_data_collector, temp_dir)


def test_hotspots_chart_plots_only_the_highest_scoring_files(mock_data_collector, temp_dir):
    """A huge repository gets a capped plot, and the page says so."""
    mock_data_collector.hotspot_files = {
        f"f{i}.py": {"lines": 10 + i, "churn": 1 + i, "score": float(i)} for i in range(12)
    }
    creator = HTMLReportCreator()
    creator.data = mock_data_collector
    creator.title = "t"
    creator.HOTSPOTS_MAX_POINTS = 5
    creator.create_hotspots_html(mock_data_collector, temp_dir)
    content = _read_page(temp_dir, "hotspots.html")

    points = _hotspot_points(content)["points"]
    assert [point[0] for point in points] == ["f11.py", "f10.py", "f9.py", "f8.py", "f7.py"]
    assert "Showing the 5 highest-scoring of 12 files." in content
    # the tiles and medians still cover every file
    assert '<dt>Files Analyzed</dt><dd class="stat-value">12</dd>' in content

    # nothing is said when every file is plotted
    mock_data_collector.hotspot_files = {"a.py": {"lines": 10, "churn": 2, "score": 6.3}}
    assert "highest-scoring of" not in _hotspots_html(mock_data_collector, temp_dir)


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


def test_section_headings_use_sentence_case(mock_data_collector, temp_dir):
    """Section headings are sentence case; only the first word is capitalized."""
    creator = HTMLReportCreator()
    creator.create(mock_data_collector, temp_dir)

    for page in ("index", "activity", "authors", "files", "lines", "ownership", "hotspots"):
        with open(os.path.join(temp_dir, f"{page}.html")) as f:
            headings = re.findall(r"<h2[^>]*>(?:<a [^>]*>)?([^<]+)", f.read())
        assert headings, page
        for heading in headings:
            rest = heading.split()[1:]
            assert all(not w[0].isupper() for w in rest), (page, heading)


def test_section_descriptions_share_one_style(mock_data_collector, temp_dir):
    """Every paragraph describing a section uses .section-note, none is italic."""
    creator = HTMLReportCreator()
    creator.create(mock_data_collector, temp_dir)

    notes = 0
    for page in (
        "index",
        "activity",
        "authors",
        "files",
        "lines",
        "ownership",
        "hotspots",
        "history",
    ):
        with open(os.path.join(temp_dir, f"{page}.html")) as f:
            html = f.read()
        assert "<p><em>" not in html, page
        notes += html.count('<p class="section-note">')
    assert notes >= 6


def test_contributor_growth_is_cumulative(mock_data_collector, temp_dir):
    """Contributors so far, as a step line up to the last month with commits."""
    creator = HTMLReportCreator()
    creator.create(mock_data_collector, temp_dir)
    with open(os.path.join(temp_dir, "authors.html")) as f:
        html = f.read()

    chart = html[html.index('id="chart-contributor-growth"') :]
    chart = chart[: chart.index("</script>")]
    assert "type: 'line'" in chart
    # one new contributor in each of Jan-Mar 2023, then none through June
    assert '"2023-01", "2023-02", "2023-03", "2023-04", "2023-05", "2023-06"' in chart
    assert '"data": [1, 2, 3, 3, 3, 3], "stepped": true' in chart
    assert '"notes": ["+1 new", "+1 new", "+1 new", "", "", ""]' in chart
    assert "afterLabel: function(item)" in chart


def test_render_chartjs_merges_tooltip_callbacks():
    """Notes add an afterLabel line without dropping the chart's other callbacks."""
    creator = HTMLReportCreator()
    result = creator._render_chartjs(
        "c",
        "bar",
        ["a", "b"],
        [{"label": "C", "data": [1, 2], "notes": ["x", ""]}],
        tooltip_share=True,
    )
    assert result.count("tooltip:") == 1
    assert "label: function(item)" in result
    assert "afterLabel: function(item)" in result


def test_render_chartjs_integer_y_ticks():
    """Every chart counts whole things, so the y-axis never shows 0.2 steps."""
    creator = HTMLReportCreator()
    result = creator._render_chartjs("c", "bar", ["a"], [{"label": "C", "data": [1]}])
    assert "y: { beginAtZero: true, ticks: { precision: 0 } }" in result


def test_bot_badges_wherever_authors_are_named(mock_data_collector, temp_dir):
    """Releases, tags and top-author tables mark bots like the author lists do."""
    bot = "dependabot[bot]"
    badge = 'dependabot <span class="badge" title="dependabot[bot]">bot</span>'
    mock_data_collector.tags["v1.1.0"]["authors"] = {bot: 5, "Alice Smith": 3}
    mock_data_collector.author_of_year = {2023: {bot: 40, "Alice Smith": 30}}
    mock_data_collector.author_of_month = {
        **mock_data_collector.author_of_month,
        "2023-04": {"Alice Smith": 5, bot: 2},
    }
    HTMLReportCreator().create(mock_data_collector, temp_dir)

    def page(name):
        with open(os.path.join(temp_dir, name), encoding="utf-8") as f:
            return f.read()

    assert f"{badge}, Alice Smith" in page("index.html")  # Latest releases
    assert f"{badge} (5), Alice Smith (3)" in page("tags.html")
    authors = page("authors.html")
    assert f"<tr><td>2023</td><td>{badge}</td>" in authors  # top author of the year
    assert f'<td>{badge}</td><td class="num">2</td></tr>' in authors  # runner-up


def test_chart_lines_are_one_and_a_half_pixels():
    creator = HTMLReportCreator()
    single = creator._render_chartjs("c1", "line", ["a"], [{"label": "L", "data": [1]}])
    assert '"borderWidth": 1.5' in single
    multi = creator._render_chartjs(
        "c2",
        "line",
        ["a"],
        [{"label": s, "data": [1]} for s in "ABC"],
        highlight=2,
    )
    # highlighted series 1.5px, the grey rest stay 1px behind them
    assert multi.count('"borderWidth": 1.5') == 2
    assert multi.count('"borderWidth": 1,') == 1


def test_pinned_column_divider_only_on_scrolling_tables():
    """JS marks overflowing .table-scroll boxes; only those draw the divider."""
    creator = HTMLReportCreator()
    creator.title = "p"
    f = StringIO()
    creator.print_header(f)
    assert "box.classList.toggle('is-scrollable'" in f.getvalue()
    css_path = os.path.join(os.path.dirname(__file__), "..", "gitstats", "gitstats.css")
    with open(css_path, encoding="utf-8") as f:
        css = f.read()
    rule = css[css.index(".table-scroll tr > :first-child {") :]
    assert "box-shadow" not in rule[: rule.index("}")]
    assert ".table-scroll.is-scrollable tr > :first-child," in css


def test_numbers_have_thousands_separators_everywhere(mock_data_collector, temp_dir):
    """Tables and the History page format numbers like the KPI tiles: 12,345."""
    mock_data_collector.lines_added_by_year = {2023: 12345}
    mock_data_collector.lines_added_by_month = {**mock_data_collector.lines_added_by_month}
    mock_data_collector.lines_added_by_month["2023-01"] = 23456
    mock_data_collector.extensions = {"py": {"files": 10, "lines": 34567}}
    HTMLReportCreator().create(mock_data_collector, temp_dir)

    def page(name):
        with open(os.path.join(temp_dir, name), encoding="utf-8") as f:
            return f.read()

    activity = page("activity.html")
    assert '<td class="num">12,345</td>' in activity  # commits by year
    assert '<td class="num">23,456</td>' in activity  # commits by month
    assert "34,567" in page("files.html")  # extensions
    assert "3,456" in page("files.html")  # lines per file
    assert "+12,345 / &minus;" in page("history.html")


def test_percentages_have_one_decimal(mock_data_collector, temp_dir):
    """Shares read the same on every page: 43.1%, never 43.11%."""
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    for page in (
        "index",
        "activity",
        "authors",
        "files",
        "ownership",
        "hotspots",
        "history",
        "tags",
    ):
        with open(os.path.join(temp_dir, f"{page}.html"), encoding="utf-8") as f:
            text = re.sub(r"<script>.*?</script>", "", f.read(), flags=re.S)
        assert not re.search(r"\d\.\d\d%", text), page


def test_timeline_names_bots_with_the_badge(mock_data_collector, temp_dir):
    bot = {**mock_data_collector.authors["Charlie Brown"]}
    mock_data_collector.authors = {**mock_data_collector.authors, "renovate[bot]": bot}
    mock_data_collector.get_authors.side_effect = lambda limit=None: [
        "Alice Smith",
        "renovate[bot]",
    ][:limit]
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    with open(os.path.join(temp_dir, "authors.html"), encoding="utf-8") as f:
        html = f.read()
    assert (
        '<span class="timeline-name">renovate '
        '<span class="badge" title="renovate[bot]">bot</span></span>'
    ) in html
    assert 'aria-label="renovate[bot]:' in html  # screen readers still get the full name


def _history_html(data, temp_dir):
    creator = HTMLReportCreator()
    creator.data = data
    creator.title = "t"
    creator.create_history_html(data, temp_dir)
    with open(f"{temp_dir}/history.html", encoding="utf-8") as f:
        return f.read()


def test_history_merges_a_run_of_dormant_years(mock_data_collector, temp_dir):
    mock_data_collector.commits_by_year = {2010: 5, 2014: 1, 2015: 0, 2016: 4}
    mock_data_collector.author_of_year = {
        2010: {"Alice Smith": 5},
        2014: {"Alice Smith": 1},
        2016: {"Alice Smith": 4},
    }
    html = _history_html(mock_data_collector, temp_dir)
    # 2011-2013 is one row; the single empty 2015 keeps its own
    assert '<span class="history-year-num">2011–2013</span>' in html
    assert "3 years without commits" in html
    assert '<span class="history-year-num">2012</span>' not in html
    assert '<span class="history-year-num">2015</span>' in html
    assert html.count("history-gap") == 1
    # one commit reads "1 commit"
    assert "(1 commit)</p>" in html


def test_data_tables_span_the_content_width():
    css_path = os.path.join(os.path.dirname(__file__), "..", "gitstats", "gitstats.css")
    with open(css_path, encoding="utf-8") as f:
        css = f.read()
    rule = css[css.index(".table-scroll > table {") :]
    assert "width: 100%;" in rule[: rule.index("}")]


def test_extensions_bar_table_ranked_by_lines(mock_data_collector, temp_dir):
    mock_data_collector.extensions = {
        "css": {"files": 1, "lines": 100},
        "py": {"files": 4, "lines": 800},
        "png": {"files": 3, "lines": 0},
        "": {"files": 1, "lines": 10},
    }
    mock_data_collector.get_total_loc.return_value = 910
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    with open(os.path.join(temp_dir, "files.html"), encoding="utf-8") as f:
        html = f.read()
    table = html[html.index('id="ext"') :]
    table = table[: table.index("</table>")]
    # most lines first; binary files last with dashes and an empty bar
    assert (
        table.index(">py<")
        < table.index(">css<")
        < table.index("no extension")
        < table.index(">png<")
    )
    assert (
        '<tr><td>py</td><td class="num">4</td><td class="num">800</td>'
        '<td class="num">87.9%</td><td class="num">200</td>'
        '<td class="share-cell"><span class="share-bar" aria-hidden="true">'
        '<span style="width: 100.0%"></span></span></td></tr>'
    ) in table
    assert (
        '<tr><td>png</td><td class="num">3</td><td class="num">—</td><td class="num">—</td>'
        '<td class="num">—</td><td class="share-cell"><span class="share-bar" '
        'aria-hidden="true"></span></td></tr>'
    ) in table
    assert "<td><em>no extension</em></td>" in table


def test_ownership_and_hotspots_skip_deleted_files(mock_data_collector, temp_dir):
    mock_data_collector.head_files = ["main.py", "utils.py", "setup.py"]
    mock_data_collector.author_files = {
        "Alice Smith": {"main.py": 10, "old_script": 40},
        "Bob Jones": {"main.py": 5, "utils.py": 8, "setup.py": 8},
    }
    mock_data_collector.file_churn = {"old_script": 40, "main.py": 15, "utils.py": 8}
    HTMLReportCreator().create(mock_data_collector, temp_dir)

    def page(name):
        with open(os.path.join(temp_dir, name), encoding="utf-8") as f:
            return f.read()

    ownership = page("ownership.html")
    assert "old_script" not in ownership
    assert (
        '<dd class="stat-value">3</dd><dd class="stat-note">of code in the current tree</dd>'
    ) in ownership
    hotspots = page("hotspots.html")
    assert "old_script" not in hotspots


def test_single_owner_files_are_grouped_by_owner(mock_data_collector, temp_dir):
    """The owners with the most single-owner files first, each with their
    most-changed files by name; after ten owners, the rest as one row; and
    every file folded away under them."""
    files = {"Alice Smith": {f"a{i:02d}.py": 30 - i for i in range(12)}}
    files["Bob Jones"] = {"b1.py": 9, "b2.py": 1}
    # ten more owners of one file each: the last two are summed up
    files.update({f"Person {n:02d}": {f"p{n:02d}.py": 20 - n} for n in range(10)})
    mock_data_collector.author_files = files
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    page = _read_page(temp_dir, "ownership.html")
    section = page[page.index('id="bus_factor_risk') : page.index('id="ownership_by_author"')]

    assert "Alice Smith is the only one to have changed 12 of the 24." in section
    owners = section[section.index('id="ownership-owners"') : section.index("</table>")]
    assert owners.count('<td class="owner-name">') == 11
    assert owners.index("Alice Smith") < owners.index("Bob Jones") < owners.index("Person 00")
    assert "Person 07" in owners
    assert "Person 08" not in owners
    # Alice: 12 files, 30 + 29 + ... + 19 commits, her three most-changed by name
    assert (
        '<td class="num" data-label="Files">12</td><td class="num" data-label="Commits">294</td>'
    ) in owners
    assert (
        '<td class="owner-files"><span class="path">a00.py</span><span class="path">a01.py</span>'
        '<span class="path">a02.py</span><span class="owner-files-more">and 9 more</span></td>'
    ) in owners
    # Bob's two files, both named
    assert '<span class="path">b2.py</span></td>' in owners
    assert (
        '<tr class="share-rest"><td class="owner-name">2 other owners</td>'
        '<td class="num" data-label="Files">2</td>'
    ) in owners
    assert (
        '<details class="table-details"><summary>All 24 single-owner files</summary>'
        '<div class="table-scroll"><table class="sortable file-table" id="ownership-busfactor">'
    ) in section


def test_single_owner_files_of_one_owner_and_more_than_a_hundred(mock_data_collector, temp_dir):
    mock_data_collector.author_files = {"Alice Smith": {f"a{i:03d}.py": i + 1 for i in range(120)}}
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    page = _read_page(temp_dir, "ownership.html")
    assert "Alice Smith is the only one to have changed all 120." in page
    assert "other owner" not in page
    folded = page[page.index("<summary>The 100 most-changed of 120 single-owner files</summary>") :]
    folded = folded[: folded.index("</details>")]
    assert folded.count('<td class="path">') == 100
    assert "a119.py" in folded
    assert "a019.py" not in folded


def test_every_page_opens_the_same_way(mock_data_collector, temp_dir):
    """h1, then an optional one-paragraph note, then stat tiles; no page-meta line
    except the overview's report period."""
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    for page in (
        "activity",
        "authors",
        "files",
        "lines",
        "tags",
        "ownership",
        "hotspots",
        "history",
    ):
        with open(os.path.join(temp_dir, f"{page}.html"), encoding="utf-8") as f:
            html = f.read()
        after_h1 = html[html.index("</h1>") + len("</h1>") :]
        assert re.match(r'(<p class="section-note">.*?</p>)?<dl class="stat-tiles"', after_h1), page
        assert 'class="page-meta"' not in html, page


def test_stat_tiles_span_the_content_width():
    css_path = os.path.join(os.path.dirname(__file__), "..", "gitstats", "gitstats.css")
    with open(css_path, encoding="utf-8") as f:
        css = f.read()
    rule = css[css.index(".stat-tiles {") :]
    assert "max-width" not in rule[: rule.index("}")]
    assert "grid-column: span var(--span-sm, 1);" in css


def test_quiet_stretch_is_shaded_on_line_charts_and_timeline(mock_data_collector, temp_dir):
    """The longest year+ without commits is shaded on every time chart, not just the bars."""
    # one quiet year in six: shaded, but too short to be cut out of the axis
    months = {f"{y}-{m:02d}": 2 for y in (2008, 2009, 2010) for m in range(1, 13)}
    months.update({f"{y}-{m:02d}": 3 for y in (2012, 2013) for m in range(1, 13)})
    mock_data_collector.commits_by_month = months
    mock_data_collector.author_of_month = {m: {"Alice Smith": n} for m, n in months.items()}
    mock_data_collector.new_contributors_by_month = {"2008-01": 1, "2013-06": 1}
    HTMLReportCreator().create(mock_data_collector, temp_dir)

    def page(name):
        with open(os.path.join(temp_dir, name), encoding="utf-8") as f:
            return f.read()

    start = int(datetime.datetime(2011, 1, 1).timestamp() * 1000)
    end = int(datetime.datetime(2012, 1, 1).timestamp() * 1000)
    band = f'"bands": [{{"from": {start}, "to": {end}, "text": "No commits 2011-01 \\u2013 2011-12"'
    for name, chart in (
        ("files.html", "chart-files-by-date"),
        ("lines.html", "chart-lines-of-code"),
        ("authors.html", "chart-loc-by-author"),
    ):
        html = page(name)
        script = html[html.index(f'id="{chart}"') :]
        assert band in script[: script.index("</script>")], chart
    authors = page("authors.html")
    growth = authors[authors.index('id="chart-contributor-growth"') :]
    growth = growth[: growth.index("</script>")]
    # 2008-01 .. 2013-12 by month: the quiet stretch is indexes 36..47
    assert '"bands": [{"from": 36, "to": 47, "text": "No commits 2011-01' in growth
    assert '"collapsed"' not in growth
    assert '<span class="timeline-gap" style="left: 50.000%; width: 16.667%" ' in authors
    assert "is-collapsed" not in authors


def test_long_quiet_stretch_is_cut_out_of_the_time_axes(mock_data_collector, temp_dir):
    """Half the history without commits: a short break, not half of every chart."""
    months = {f"2010-{m:02d}": 2 for m in range(1, 13)}
    months.update({f"2013-{m:02d}": 3 for m in range(1, 13)})
    mock_data_collector.commits_by_month = months
    mock_data_collector.author_of_month = {m: {"Alice Smith": n} for m, n in months.items()}
    mock_data_collector.new_contributors_by_month = {"2010-01": 1, "2013-06": 1}
    # a file count on each side of the two quiet years
    mock_data_collector.files_by_stamp = {
        int(datetime.datetime(2010, 1, 5).timestamp()): 3,
        int(datetime.datetime(2010, 12, 20).timestamp()): 8,
        int(datetime.datetime(2013, 1, 10).timestamp()): 9,
        int(datetime.datetime(2013, 12, 30).timestamp()): 12,
    }
    HTMLReportCreator().create(mock_data_collector, temp_dir)

    def page(name):
        with open(os.path.join(temp_dir, name), encoding="utf-8") as f:
            return f.read()

    authors = page("authors.html")
    growth = authors[authors.index('id="chart-contributor-growth"') :]
    growth = growth[: growth.index("</script>")]
    # 48 months, 24 of them quiet: those 24 are one slot, named after all of them
    labels = json.loads(growth.split("var labels = ", 1)[1].split(";\n", 1)[0])
    assert len(labels) == 25
    assert labels[11:14] == ["2010-12", "2011-01 \u2013 2012-12", "2013-01"]
    assert (
        '"bands": [{"from": 12, "to": 12, "text": "No commits 2011-01 \\u2013 2012-12", '
        '"short": "no commits", "collapsed": true, "axis": "2011\\u201312"}]'
    ) in growth
    # the line stays where it was through the break: one contributor so far
    data = json.loads(growth.split('"data": ', 1)[1].split("]", 1)[0] + "]")
    assert data[11:14] == [1, 1, 1]

    # the timeline cuts the same stretch to the same slot: 12 + 1 + 12 months
    assert (
        '<span class="timeline-gap is-collapsed" style="left: 48.000%; width: 4.000%" '
        'title="No commits 2011-01 \u2013 2012-12"><span>2011\u201312</span></span>'
    ) in authors
    # 2011 and 2012 have no gridline of their own; 2013 starts right after the break
    assert re.findall(
        r'<span class="timeline-year" style="left: ([\d.]+)%">(\d*)</span>', authors
    ) == [("52.000", "2013")]
    # a mark in 2013-01 sits half a month past the break
    assert 'class="timeline-mark" style="left: 54.000%;' in authors

    # the time-axis chart is handed the gap, and its band is the break
    files = page("files.html")
    chart = files[files.index('id="chart-files-by-date"') :]
    chart = chart[: chart.index("</script>")]
    start = int(datetime.datetime(2011, 1, 1).timestamp() * 1000)
    end = int(datetime.datetime(2013, 1, 1).timestamp() * 1000)
    gap = json.loads(chart.split("var gap = ", 1)[1].split(";\n", 1)[0])
    assert (gap["from"], gap["to"]) == (start, end)
    span = (
        datetime.datetime(2013, 12, 30).timestamp() - datetime.datetime(2010, 1, 5).timestamp()
    ) * 1000
    assert gap["width"] == round(0.05 * (span - (end - start)))
    assert (
        f'"bands": [{{"from": {start}, "to": {start + gap["width"]}, '
        '"text": "No commits 2011-01 \\u2013 2012-12", "short": "no commits", '
        '"collapsed": true, "axis": "2011\\u201312"}]'
    ) in chart


@pytest.mark.parametrize(
    ("total", "gap", "expected"),
    [
        (232, 106, 6.3),  # gitstats itself: 106 quiet months of 232
        (100, 25, 3.75),  # a quarter of the axis is enough
        (100, 24, None),  # under a quarter: shaded, and left as wide as it is
        (0, 0, None),
    ],
)
def test_collapsed_width(total, gap, expected):
    assert collapsed_width(total, gap) == pytest.approx(expected)


def test_collapsed_slots():
    assert collapsed_slots(232, 106) == 6
    # a year chart: eight empty years of twenty become one slot
    assert collapsed_slots(20, 8) == 1
    # nothing to gain when the stretch is no longer than its break would be
    assert collapsed_slots(4, 1) is None
    assert collapsed_slots(100, 24) is None


def test_year_span():
    assert year_span("2016-01", "2024-10") == "2016\u201324"
    assert year_span(2016, 2023) == "2016\u201323"
    assert year_span("2020-02", "2020-12") == "2020"
    assert year_span(1998, 2003) == "1998\u20132003"


def test_collapse_gap_categories_on_a_bar_chart():
    years = [2007, 2008, 2016, 2017, 2018, 2019, 2024, 2025]
    values = [9, 4, 0, 0, 0, 0, 6, 12]
    annotations = gap_annotations(years, values, min_gap=2)
    datasets = [{"label": "Commits", "data": values, "notes": ["a", "b", "", "", "", "", "c", "d"]}]
    labels, sets, collapsed = collapse_gap_categories(years, datasets, annotations)

    # four empty years of eight become one slot, named after all four
    assert labels == [2007, 2008, "2016 \u2013 2019", 2024, 2025]
    assert sets == [
        {"label": "Commits", "data": [9, 4, 0, 6, 12], "notes": ["a", "b", "", "c", "d"]}
    ]
    assert collapsed["bands"] == [
        {
            "from": 2,
            "to": 2,
            "text": "No commits 2016 \u2013 2019",
            "short": "no commits",
            "collapsed": True,
            "axis": "2016\u201319",
        }
    ]
    # the peak before the stretch stays put, the one after it moves up
    assert collapsed["peaks"] == [
        {"index": 0, "text": "2007 \u00b7 9"},
        {"index": 4, "text": "2025 \u00b7 12"},
    ]
    # the caller's lists are not touched
    assert len(years) == 8 and len(datasets[0]["data"]) == 8
    assert annotations["bands"][0]["to"] == 5


def test_collapse_gap_categories_keeps_a_cumulative_line_level():
    labels = [f"m{i}" for i in range(10)]
    band = {"from": 2, "to": 7, "text": "No commits", "short": "no commits"}
    datasets = [{"label": "Contributors", "data": [1, 2, 2, 2, 2, 2, 2, 2, 3, 4]}]
    new_labels, sets, _ = collapse_gap_categories(labels, datasets, {"bands": [band]})
    assert new_labels == ["m0", "m1", "m2 \u2013 m7", "m8", "m9"]
    assert sets[0]["data"] == [1, 2, 2, 3, 4]


def test_collapse_gap_categories_leaves_short_stretches_alone():
    years = [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027, 2028]
    values = [5, 0, 0, 3, 4, 5, 6, 7, 8, 9]
    annotations = gap_annotations(years, values, min_gap=2)
    datasets = [{"label": "Commits", "data": values}]
    # two empty years of ten are shaded, but under a quarter of the axis
    assert collapse_gap_categories(years, datasets, annotations) == (years, datasets, annotations)
    # and without a band there is nothing to collapse
    assert collapse_gap_categories(years, datasets, {"values": True}) == (
        years,
        datasets,
        {"values": True},
    )


def test_collapse_gap_time():
    day = 86_400_000
    stamps = [0, 10 * day, 110 * day, 200 * day]
    band = {"from": 20 * day, "to": 100 * day, "text": "No commits", "short": "no commits"}
    annotations, gap = collapse_gap_time(stamps, {"bands": [band]})

    # 80 quiet days of 200 are drawn as wide as 5% of the other 120: six days
    assert gap == {"from": 20 * day, "to": 100 * day, "width": 6 * day}
    assert annotations["bands"] == [
        {**band, "to": 26 * day, "collapsed": True, "axis": annotations["bands"][0]["axis"]}
    ]
    # the caller's band is not touched
    assert band["to"] == 100 * day


def test_collapse_gap_time_names_the_years_of_the_stretch():
    start = int(datetime.datetime(2016, 1, 1).timestamp() * 1000)
    end = int(datetime.datetime(2024, 11, 1).timestamp() * 1000)  # the day after 2024-10
    stamps = [
        int(datetime.datetime(2007, 7, 30).timestamp() * 1000),
        int(datetime.datetime(2026, 10, 11).timestamp() * 1000),
    ]
    annotations, _ = collapse_gap_time(stamps, {"bands": [{"from": start, "to": end}]})
    assert annotations["bands"][0]["axis"] == "2016\u201324"


def test_collapse_gap_time_leaves_the_rest_alone():
    day = 86_400_000
    band = {"from": 20 * day, "to": 40 * day, "text": "No commits"}
    annotations = {"bands": [band]}
    # under a quarter of the axis
    assert collapse_gap_time([0, 10 * day, 200 * day], annotations) == (annotations, None)
    # a stretch that is not between two of the chart's points
    assert collapse_gap_time([25 * day, 60 * day], annotations) == (annotations, None)
    # nothing to place it against
    assert collapse_gap_time([], annotations) == (annotations, None)
    assert collapse_gap_time([0, 200 * day], {"values": True}) == ({"values": True}, None)


def test_render_chartjs_collapses_a_long_gap_on_a_year_axis():
    creator = HTMLReportCreator()
    years = [2007, 2008, 2016, 2017, 2018, 2019, 2024, 2025]
    values = [9, 4, 0, 0, 0, 0, 6, 12]
    result = creator._render_chartjs(
        "chart-years",
        "bar",
        years,
        [{"label": "Commits", "data": values}],
        annotations=gap_annotations(years, values, min_gap=2),
    )
    assert 'var labels = [2007, 2008, "2016 \\u2013 2019", 2024, 2025];' in result
    assert '"data": [9, 4, 0, 6, 12]' in result
    assert '"collapsed": true, "axis": "2016\\u201319"' in result
    # the slot's own name is for tooltips: the tick under it is left to the band
    assert "callback: categoryTick" in result
    # a chart with nothing collapsed keeps the plain axis
    plain = creator._render_chartjs("c", "bar", [2020, 2021], [{"label": "C", "data": [1, 2]}])
    assert "categoryTick" not in plain


def test_chart_script_knows_how_to_draw_a_collapsed_stretch():
    from gitstats.report_creator import CHART_SCRIPT

    for name in ("function squeezeTime(gap, ms)", "function stretchTime(gap, at)"):
        assert name in CHART_SCRIPT
    assert "function timeAxis(xs, gap)" in CHART_SCRIPT
    assert "function categoryTick(value)" in CHART_SCRIPT
    # month axes do not label the slots standing in for the stretch
    assert "if (isCollapsedLabel(label)) return '';" in CHART_SCRIPT
    assert "band.collapsed" in CHART_SCRIPT


def test_quiet_months_needs_a_year():
    class Data:
        commits_by_month = {"2020-01": 1, "2020-06": 1}  # five empty months only

    assert quiet_months(Data()) is None


def test_tags_table_is_a_sortable_section(mock_data_collector, temp_dir):
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    with open(os.path.join(temp_dir, "tags.html"), encoding="utf-8") as f:
        html = f.read()
    assert '<h2 id="all_tags">' in html
    assert '<table class="tags sortable" id="tags">' in html
    assert '<th class="unsortable">Authors</th>' in html


def test_tags_page_without_tags_has_no_empty_table(mock_data_collector, temp_dir):
    mock_data_collector.tags = {}
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    with open(os.path.join(temp_dir, "tags.html"), encoding="utf-8") as f:
        html = f.read()
    assert "no tags yet" in html
    assert "<table" not in html


def test_authors_page_states_the_top_n_once_per_section(mock_data_collector, temp_dir):
    """When only the top authors are listed, each section's note says so, in one wording."""
    from unittest.mock import patch

    config = {**load_config(), "max_authors": 2, "max_authors_list": 10}
    with patch("gitstats.report_creator.load_config", return_value=config):
        HTMLReportCreator().create(mock_data_collector, temp_dir)
    with open(os.path.join(temp_dir, "authors.html"), encoding="utf-8") as f:
        html = f.read()
    assert '<p class="section-note">The top 2 of 3 authors, by commits.</p>' in html
    assert '<p class="moreauthors">The other 1: Charlie Brown.</p>' in html
    assert "Lines added over time by the top 2 of 3 authors;" in html
    assert "One row for each of the top 2 of 3 authors:" in html
    assert "Only top" not in html
    assert "didn't make it" not in html


def test_lines_per_author_heading_keeps_its_old_anchor(mock_data_collector, temp_dir):
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    with open(os.path.join(temp_dir, "authors.html"), encoding="utf-8") as f:
        html = f.read()
    old = html.index('<span id="cumulated_added_lines_of_code_per_author"></span>')
    assert html.index('<h2 id="cumulative_lines_added_per_author">') > old
    assert "Cumulated" not in html


def test_bar_charts_drop_redundant_lines():
    creator = HTMLReportCreator()
    bars = creator._render_chartjs("b", "bar", ["a", "b"], [{"label": "C", "data": [1, 2]}])
    # no gridline per category bar; the y gridlines stay
    assert "x: { ticks: { maxRotation: 0, autoSkipPadding: 12 }, grid: { display: false } }" in bars
    assert "y: { beginAtZero: true, ticks: { precision: 0 } }" in bars
    line = creator._render_chartjs("l", "line", ["a", "b"], [{"label": "C", "data": [1, 2]}])
    assert "grid: { display: false }" not in line
    # a bar chart labelled with every value hides the y-axis that would repeat them
    valued = creator._render_chartjs(
        "v", "bar", ["a", "b"], [{"label": "C", "data": [1, 2]}], annotations={"values": True}
    )
    assert "y: { display: false, beginAtZero: true, grace: '10%' }" in valued


def test_on_this_page_scrolls_sideways_on_phones():
    css_path = os.path.join(os.path.dirname(__file__), "..", "gitstats", "gitstats.css")
    with open(css_path, encoding="utf-8") as f:
        css = f.read()
    phones = css[css.index("@media (max-width: 768px) {") :]
    rule = phones[phones.index(".page-toc {") :]
    rule = rule[: rule.index("}")]
    assert "flex-wrap: nowrap;" in rule
    assert "overflow-x: auto;" in rule


def test_render_chartjs_diverging_with_theme_colors():
    creator = HTMLReportCreator()
    result = creator._render_chartjs(
        "d",
        "bar",
        ["2024-01", "2024-02"],
        [
            {"label": "Added", "data": [5, 3], "colorVar": "--success-color"},
            {"label": "Removed", "data": [-2, -1], "colorVar": "--danger-color"},
        ],
        month_axis=True,
        diverging=True,
    )
    # colors come from CSS variables (re-read on theme change), not the series palette
    assert "\"backgroundColor\": getCSSVar('--success-color')" in result
    assert "\"borderColor\": getCSSVar('--danger-color')" in result
    assert '"series"' not in result
    # stacked around zero, magnitudes on the axis and in the tooltip
    assert "x: { stacked: true, ticks: { autoSkip: false" in result
    assert "y: { stacked: true, beginAtZero: true, ticks: { precision: 0, callback:" in result
    assert "Math.abs(item.parsed.y).toLocaleString()" in result


def test_lines_page_charts_lines_added_and_removed_per_month(mock_data_collector, temp_dir):
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    with open(os.path.join(temp_dir, "lines.html"), encoding="utf-8") as f:
        html = f.read()
    assert '<h2 id="lines_added_and_removed_per_month">' in html
    chart = html[html.index('id="chart-lines-by-month"') :]
    chart = chart[: chart.index("</script>")]
    # fixture: +300/-100, +600/-200, +900/-300 in 2023-01..03
    assert '"label": "Added", "data": [300, 600, 900]' in chart
    assert '"label": "Removed", "data": [-100, -200, -300]' in chart


def test_domain_section_keeps_its_old_anchor(mock_data_collector, temp_dir):
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    with open(os.path.join(temp_dir, "authors.html"), encoding="utf-8") as f:
        html = f.read()
    old = html.index('<span id="commits_by_domains"></span>')
    assert html.index('<h2 id="commits_by_domain">') > old


def test_overview_flags_a_shallow_clone(mock_data_collector, temp_dir):
    """A report built from a shallow clone says so under the heading."""
    mock_data_collector.shallow = True
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    with open(os.path.join(temp_dir, "index.html"), encoding="utf-8") as f:
        html = f.read()
    assert '<p class="section-note shallow-note"><strong>Shallow clone:</strong>' in html
    assert html.index('class="page-meta"') < html.index("shallow-note")


def test_overview_has_no_shallow_note_for_a_full_clone(mock_data_collector, temp_dir):
    mock_data_collector.shallow = False
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    with open(os.path.join(temp_dir, "index.html"), encoding="utf-8") as f:
        assert "shallow-note" not in f.read()


# ── tags_newest_first ────────────────────────────────────────────────────


def test_tags_newest_first_follows_history_not_the_date():
    # "later" is the older commit but carries the later date, which is what a
    # rebase or an imported history produces. The report must agree with the
    # commit walk, which credits commits by position rather than by date.
    tags = {
        "later": {"order": 1, "date": "2026-05-01"},
        "newer": {"order": 0, "date": "2026-01-01"},
    }
    assert tags_newest_first(tags) == ["newer", "later"]


def test_tags_newest_first_orders_same_day_tags_by_history():
    # Sorting on the "%Y-%m-%d" string alone leaves same-day tags tied, and the
    # old tie-break on the name put v10 before v9.
    tags = {
        "v9": {"order": 1, "date": "2026-03-04"},
        "v10": {"order": 0, "date": "2026-03-04"},
    }
    assert tags_newest_first(tags) == ["v10", "v9"]


def test_tags_newest_first_falls_back_to_the_date_without_a_position():
    # A cache written before the position was recorded has no "order" key.
    tags = {
        "old": {"date": "2024-01-01"},
        "new": {"date": "2026-01-01"},
        "middle": {"date": "2025-06-15"},
    }
    assert tags_newest_first(tags) == ["new", "middle", "old"]


def test_tags_newest_first_puts_positioned_tags_before_the_fallback():
    tags = {
        "positioned": {"order": 3, "date": "2020-01-01"},
        "cached": {"date": "2026-01-01"},
    }
    assert tags_newest_first(tags) == ["positioned", "cached"]


def test_tags_newest_first_handles_an_unparsable_date():
    tags = {"a": {"date": "not-a-date"}, "b": {"date": "2026-01-01"}}
    assert tags_newest_first(tags) == ["b", "a"]


def test_tags_newest_first_is_empty_without_tags():
    assert tags_newest_first({}) == []


# ── HTMLReportCreator.create_badges_html ─────────────────────────────────


def _badges_page(mock_data_collector, temp_dir):
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    with open(os.path.join(temp_dir, "badges.html"), encoding="utf-8") as f:
        return f.read()


def test_badges_page_lists_every_badge(mock_data_collector, temp_dir):
    content = _badges_page(mock_data_collector, temp_dir)
    badges_dir = os.path.join(temp_dir, "badges", "flat")
    for name in os.listdir(badges_dir):
        name = name[: -len(".svg")]
        assert f'data-kind="style" data-badge="{name}"' in content
        assert f'<img src="badges/flat/{name}.svg"' in content
    assert content.count('class="badge-row"') == len(os.listdir(badges_dir)) + 2
    assert 'data-kind="default"' in content
    assert 'data-kind="endpoint"' in content


def _report_with_card(data, path, card):
    creator = HTMLReportCreator()
    creator.wrapped_card = card
    creator.create(data, path)

    def page(name):
        with open(os.path.join(path, name), encoding="utf-8") as f:
            return f.read()

    return page


def test_badges_page_shows_the_wrapped_card(mock_data_collector, temp_dir):
    """The card --wrapped wrote next to the report: a preview, a snippet, the file."""
    card = {"year": 2023, "theme": "sunset", "file": "wrapped-2023.svg"}
    content = _report_with_card(mock_data_collector, temp_dir, card)("badges.html")

    section = content[content.index('<h2 id="repo_wrapped">') :]
    # a row like the badges', so the page's script fills in its snippet and copies it
    assert (
        '<div class="badge-row" data-kind="card" data-badge="wrapped-2023.svg" '
        'data-alt="test-project in 2023" data-title="wrapped-2023.svg">'
    ) in section
    assert "<code>wrapped-2023.svg</code><span>1080 &times; 1080, sunset theme</span>" in section
    assert (
        '<a class="wrapped-preview" href="wrapped-2023.svg">'
        '<img src="wrapped-2023.svg" width="240" height="240" '
        'alt="Repo Wrapped card for test-project in 2023"></a>'
    ) in section
    # until the script knows the report's address, the placeholder stands in for it
    placeholder = BADGES_PLACEHOLDER_URL.replace("<", "&lt;").replace(">", "&gt;")
    assert (
        '<pre class="badge-code">[![test-project in 2023]'
        f"({placeholder}wrapped-2023.svg)]({placeholder})</pre>"
    ) in section
    assert 'aria-label="Copy Markdown for wrapped-2023.svg"' in section
    assert '<a href="wrapped-2023.svg" download>Download SVG &rarr;</a>' in section
    # it comes after the badges
    assert content.index('<h2 id="other_ways_to_use_them">') < content.index(
        '<h2 id="repo_wrapped">'
    )


def test_badges_page_without_a_wrapped_card_says_how_to_get_one(mock_data_collector, temp_dir):
    content = _badges_page(mock_data_collector, temp_dir)
    section = content[content.index('<h2 id="repo_wrapped">') :]
    assert "There is none next to this report" in section
    assert '<code class="nowrap">--wrapped</code>' in section
    assert 'data-kind="card"' not in content
    assert "download" not in section


def test_badges_script_gives_the_card_its_own_file_and_a_width():
    from gitstats.report_creator import BADGES_SCRIPT

    assert "if (kind === 'card') { path = name; alt = row.getAttribute('data-alt'); }" in (
        BADGES_SCRIPT
    )
    # 1080px wide: the formats that can say so show it at 480
    assert "snippet(image, link, alt, kind === 'card' ? 480 : 0)" in BADGES_SCRIPT
    assert "(width ? '\\n   :width: ' + width : '')" in BADGES_SCRIPT
    assert """(width ? ' width="' + width + '"' : '')""" in BADGES_SCRIPT


def test_history_links_the_wrapped_card_from_its_year(mock_data_collector, temp_dir):
    mock_data_collector.commits_by_year = {2022: 20, 2023: 50}
    card = {"year": 2023, "theme": "midnight", "file": "wrapped-2023.svg"}
    history = _report_with_card(mock_data_collector, temp_dir, card)("history.html")

    link = '<p class="history-people"><a href="wrapped-2023.svg">Wrapped card &rarr;</a></p>'
    assert history.count(link) == 1
    # in the entry for 2023, not the one for 2022
    assert history.index('<span class="history-year-num">2023</span>') < history.index(link)
    year_2022 = history[history.index('<span class="history-year-num">2022</span>') :]
    assert link not in year_2022[: year_2022.index('<span class="history-year-num">2023</span>')]

    # and no link at all without a card
    plain = _report_with_card(mock_data_collector, temp_dir, None)("history.html")
    assert "Wrapped card" not in plain


def test_badges_page_controls_and_placeholder(mock_data_collector, temp_dir):
    content = _badges_page(mock_data_collector, temp_dir)
    for style in ("flat", "flat-square", "terminal", "for-the-badge", "light"):
        assert f'data-style="{style}"' in content
    assert 'data-style="flat" aria-pressed="true"' in content
    assert 'data-format="md" aria-pressed="true"' in content
    # until the script knows the report's address, snippets use a placeholder
    assert (
        "[![GitStats summary](https://&lt;your-report-url&gt;/badges/flat/summary.svg)]"
        "(https://&lt;your-report-url&gt;/)" in content
    )
    data = re.search(r'<script type="application/json" id="badge-data">(.*?)</script>', content)
    assert json.loads(data[1]) == {
        "style": "flat",
        "siteUrl": "",
        "placeholder": "https://<your-report-url>/",
    }
    assert 'aria-live="polite"' in content


def test_badges_page_follows_badge_config(mock_data_collector, temp_dir, monkeypatch):
    monkeypatch.setitem(load_config(), "badge_style", "terminal")
    monkeypatch.setitem(load_config(), "badge_metric", "health")
    content = _badges_page(mock_data_collector, temp_dir)
    assert 'data-style="terminal" aria-pressed="true"' in content
    assert '<img src="badges/terminal/summary.svg"' in content
    assert "The default badge: health in terminal" in content
    assert "badges/health.json" in content


def test_badges_page_has_a_hint_for_each_url_state(mock_data_collector, temp_dir):
    content = _badges_page(mock_data_collector, temp_dir)
    for state in ("detected", "site", "entered", "cleared", "missing", "invalid"):
        assert f'data-url-hint="{state}"' in content
    # only a finished, valid address is remembered; an empty field forgets it
    assert "input.addEventListener('change'" in content
    assert "if (!url || url === auto || !looksValid(url)) localStorage.removeItem(key);" in content


def test_badges_page_script_keeps_escapes(mock_data_collector, temp_dir):
    content = _badges_page(mock_data_collector, temp_dir)
    # the snippet templates stay one-line JavaScript strings
    assert r"'\n   :target: '" in content
    assert r"url.replace(/\/*$/, '/')" in content


def test_overview_links_the_badges_page(mock_data_collector, temp_dir):
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    with open(os.path.join(temp_dir, "index.html"), encoding="utf-8") as f:
        content = f.read()
    # at the far end of the heading, not among the facts under it
    head = re.search(r'<div class="page-head">(.*?)</div>', content)[1]
    assert '<a href="badges.html">Badge for your README</a>' in head
    assert "badges.html" not in re.search(r'<p class="page-meta">(.*?)</p>', content)[1]


def test_nav_lists_the_pages_group_by_group(mock_data_collector, temp_dir):
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    with open(os.path.join(temp_dir, "index.html"), encoding="utf-8") as f:
        nav = f.read().split('<ul class="nav-pages">', 1)[1].split("</ul>", 1)[0]
    labels = re.findall(r'<a href="[^"]+\.html"[^>]*>([^<]+)</a></li>', nav)
    assert labels == [
        "General",
        "Badges",
        "Authors",
        "Code Ownership",
        "Hotspots",
        "Files",
        "Lines",
        "Activity",
        "History",
        "Tags",
    ]
    assert [name for name, _ in NAV_GROUPS] == ["Overview", "People", "Code", "Timeline"]


def test_authors_sections_order(mock_data_collector, temp_dir):
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    with open(os.path.join(temp_dir, "authors.html"), encoding="utf-8") as f:
        html = f.read()
    titles = [re.sub("<[^>]+>", "", h) for h in re.findall(r"<h2[^>]*>(.*?)</h2>", html)]
    assert titles == [
        "List of authors",
        "Contributor timeline",
        "Contributor growth",
        "Top author per year and month",
        "Cumulative lines added per author",
        "Commits by organization",
        "Commits by domain",
    ]
    # the old anchors still sit right before the sections that replaced them
    for anchor, section in (
        ("commits_per_author", "contributor_timeline"),
        ("cumulated_added_lines_of_code_per_author", "cumulative_lines_added_per_author"),
        ("commits_by_domains", "commits_by_domain"),
    ):
        assert html.index(f'<span id="{anchor}">') < html.index(f'<h2 id="{section}">')


# ── pages built from sparse or unusual data ──────────────────────────────


def _read_page(path, page):
    with open(os.path.join(path, page), encoding="utf-8") as f:
        return f.read()


def test_create_with_sparse_data(mock_data_collector, temp_dir):
    """No yearly, monthly, churn or hour-of-day data: every page still renders."""
    import gitstats

    gitstats._config["style"] = "missing.css"  # a stylesheet that isn't shipped is skipped
    data = mock_data_collector
    data.commits_by_year = {}
    data.author_of_year = {}
    data.commits_by_month = {}
    data.author_of_month = {}
    data.new_contributors_by_month = {}
    data.file_churn = {}
    data.lines_added_by_month = {}
    data.lines_removed_by_month = {}
    data.get_activity_by_hour_of_day.return_value = {}
    data.get_activity_by_day_of_week.return_value = {}
    data.get_total_files.return_value = 0

    HTMLReportCreator().create(data, temp_dir)

    assert not os.path.exists(os.path.join(temp_dir, "missing.css"))
    assert os.path.exists(os.path.join(temp_dir, "sortable.js"))
    activity = _read_page(temp_dir, "activity.html")
    assert "<dt>Busiest Hour</dt>" not in activity
    assert "<dt>Busiest Day</dt>" not in activity
    authors = _read_page(temp_dir, "authors.html")
    assert "Contributor growth" not in authors
    assert "timeline-row" not in authors
    files = _read_page(temp_dir, "files.html")
    assert "<dt>Average File Size</dt>" not in files
    assert "Most changed files" not in files
    assert "Lines added and removed per month" not in _read_page(temp_dir, "lines.html")


def test_authors_summary_without_a_last_commit_date_or_authors(mock_data_collector):
    mock_data_collector.get_last_commit_date.return_value = None
    mock_data_collector.get_authors.side_effect = lambda limit=None: []
    summary = HTMLReportCreator()._authors_summary_html(mock_data_collector)
    assert '<dd class="stat-value">0</dd>' in summary
    assert "Active Authors" not in summary
    assert "Top Author" not in summary


def test_lines_page_shades_a_long_quiet_stretch(mock_data_collector, temp_dir):
    mock_data_collector.commits_by_month = {"2020-01": 5, "2021-06": 3}
    mock_data_collector.lines_added_by_month = {"2020-01": 100, "2021-06": 40}
    mock_data_collector.lines_removed_by_month = {"2021-06": 10}
    creator = HTMLReportCreator()
    creator.title = mock_data_collector.project_name
    creator.data = mock_data_collector
    creator.create_lines_html(mock_data_collector, temp_dir)

    page = _read_page(temp_dir, "lines.html")
    assert "Lines added and removed per month" in page
    assert '"bands"' in page


def test_tags_page_limits_the_authors_listed(mock_data_collector, temp_dir):
    import gitstats

    gitstats._config["max_tags_authors"] = 1
    creator = HTMLReportCreator()
    creator.title = mock_data_collector.project_name
    creator.data = mock_data_collector
    creator.create_tags_html(mock_data_collector, temp_dir)

    page = _read_page(temp_dir, "tags.html")
    assert "<em>and 1 more author</em>" in page


def test_badges_page_falls_back_to_the_default_style_and_metric(mock_data_collector, temp_dir):
    import gitstats

    gitstats._config.update(badge_style="neon", badge_metric="stars")
    creator = HTMLReportCreator()
    creator.title = mock_data_collector.project_name
    creator.data = mock_data_collector
    creator.create_badges_html(mock_data_collector, temp_dir)

    page = _read_page(temp_dir, "badges.html")
    assert "The default badge: commits in flat" in page
    assert '"style": "flat"' in page


def _ownership_page(data, path):
    creator = HTMLReportCreator()
    creator.title = data.project_name
    creator.data = data
    creator.create_ownership_html(data, path)
    return _read_page(path, "ownership.html")


def test_ownership_page_without_usable_data(mock_data_collector, temp_dir):
    mock_data_collector.author_files = ["not", "a", "mapping"]
    assert "No ownership data available" in _ownership_page(mock_data_collector, temp_dir)


def test_ownership_page_when_every_file_is_shared(mock_data_collector, temp_dir):
    mock_data_collector.author_files = {"Ann": {"a.py": 2}, "Bo": {"a.py": 1}}
    page = _ownership_page(mock_data_collector, temp_dir)
    assert "No single-owner files" in page


def test_ownership_page_lists_the_top_25_contributors(mock_data_collector, temp_dir):
    mock_data_collector.author_files = {f"Author {i:02d}": {f"f{i}.py": 1} for i in range(26)}
    page = _ownership_page(mock_data_collector, temp_dir)
    assert "Showing top 25 of 26 contributors." in page


def test_history_page_without_a_top_author_or_dated_releases(mock_data_collector, temp_dir):
    mock_data_collector.commits_by_year = {2022: 3, 2023: 2}
    mock_data_collector.author_of_year = {2023: {"Alice Smith": 2}}
    mock_data_collector.tags = {"nightly": {"date": "unknown", "commits": 1, "authors": {}}}
    history = compute_project_history(mock_data_collector)
    assert history["total_releases"] == 0
    assert [y["top_author"] for y in history["years"]] == ["", "Alice Smith"]

    creator = HTMLReportCreator()
    creator.title = mock_data_collector.project_name
    creator.data = mock_data_collector
    creator.create_history_html(mock_data_collector, temp_dir)
    assert _read_page(temp_dir, "history.html").count("Led by") == 1


def test_ai_insights_section_without_summary_or_error(mock_data_collector, temp_dir):
    mock_data_collector.ai_summaries = {"index": {}}
    creator = HTMLReportCreator()
    creator.title = mock_data_collector.project_name
    creator.data = mock_data_collector
    creator.create_ai_insights_html(mock_data_collector, temp_dir)
    assert "No analysis available for this section." in _read_page(temp_dir, "ai-insights.html")


def test_author_time_series_ignores_authors_not_plotted(mock_data_collector):
    creator = HTMLReportCreator()
    creator.data = mock_data_collector
    mock_data_collector.changes_by_date_by_author = {
        1670000000: {
            "Alice Smith": {"lines_added": 10, "commits": 1},
            "Not Plotted": {"lines_added": 99, "commits": 1},
        }
    }
    _, datasets = creator._build_author_time_series(mock_data_collector)
    assert "Not Plotted" not in [ds["label"] for ds in datasets]


@pytest.mark.parametrize("by_month", [None, {}, ["2020-01"]])
def test_quiet_months_without_monthly_data(by_month):
    assert quiet_months(SimpleNamespace(commits_by_month=by_month)) is None


def test_gap_annotations_skip_an_empty_side():
    # the gap opens the series: only the bar after it gets a peak label
    annotations = gap_annotations(["2019", "2020", "2021", "2022"], [0, 0, 0, 5], min_gap=2)
    assert [peak["index"] for peak in annotations["peaks"]] == [3]


# ── AI-assisted commits (Authors page) ───────────────────────────────────


def _stamp(year, month, day):
    return int(datetime.datetime(year, month, day, 12).timestamp())


def _with_assistants(data):
    """Three years of commits, 60 in all; from 2025 on some name an assistant."""
    data.get_total_commits.return_value = 60
    data.commits_by_month = {
        "2023-05": 20,
        "2025-02": 10,
        "2025-03": 8,
        "2025-11": 12,
        "2026-01": 10,
    }
    data.ai_assisted_commits = 9
    data.ai_assisted_authored = 2
    data.ai_assisted_by_month = {"2025-03": 4, "2025-11": 3, "2026-01": 2}
    data.ai_assistants = {
        "Claude": {
            "commits": 3,
            "authored": 0,
            "first_commit_stamp": _stamp(2025, 11, 2),
            "last_commit_stamp": _stamp(2026, 1, 20),
        },
        "GitHub Copilot": {
            "commits": 7,
            "authored": 2,
            "first_commit_stamp": _stamp(2025, 3, 5),
            "last_commit_stamp": _stamp(2026, 1, 9),
        },
    }
    return data


def test_authors_summary_says_how_many_commits_name_an_assistant(mock_data_collector):
    summary = HTMLReportCreator()._authors_summary_html(_with_assistants(mock_data_collector))
    assert (
        '<dt>AI-assisted Commits</dt><dd class="stat-value">15.0%</dd>'
        '<dd class="stat-note">at least 9 of all 60 commits</dd>'
    ) in summary

    mock_data_collector.ai_assisted_commits = 1
    summary = HTMLReportCreator()._authors_summary_html(mock_data_collector)
    # the tile says the share is of all the commits, not of the last 12 months
    assert (
        '<dd class="stat-value">1.7%</dd><dd class="stat-note">at least 1 of all 60 commits</dd>'
    ) in summary


def test_authors_summary_when_no_commit_names_an_assistant(mock_data_collector):
    # data collected before these were counted has no such number at all
    summary = HTMLReportCreator()._authors_summary_html(mock_data_collector)
    tile = (
        '<dt>AI-assisted Commits</dt><dd class="stat-value">0</dd>'
        '<dd class="stat-note">no commit names an assistant</dd>'
    )
    assert tile in summary
    mock_data_collector.ai_assisted_commits = 0
    assert tile in HTMLReportCreator()._authors_summary_html(mock_data_collector)


def test_ai_assisted_section_is_left_out_without_any(mock_data_collector, temp_dir):
    creator = HTMLReportCreator()
    assert creator._ai_assisted_html(mock_data_collector) == ""
    mock_data_collector.ai_assisted_commits = 0
    assert creator._ai_assisted_html(mock_data_collector) == ""
    creator.create(mock_data_collector, temp_dir)
    authors = _read_page(temp_dir, "authors.html")
    assert "AI-assisted commits</a></h2>" not in authors
    assert "chart-ai-assisted" not in authors


def test_ai_assisted_section(mock_data_collector):
    section = HTMLReportCreator()._ai_assisted_html(_with_assistants(mock_data_collector))
    assert '<h2 id="ai-assisted_commits">' in section
    # the share of the whole history, those an assistant made itself, and the last
    # twelve months: February 2025 to January 2026, 40 commits, all nine among them
    assert "9 of 60 commits (15.0%) name an AI coding assistant" in section
    assert "2 of them were made by an assistant under its own account." in section
    assert "In the last 12 months: 9 of 40 (22.5%)." in section
    assert "These are lower bounds." in section

    # the chart starts with the twelve months, the first assisted commit being inside them
    labels = json.loads(re.search(r"var labels = (\[.*?\]);", section).group(1))
    assert labels == month_range(["2025-02", "2026-01"])
    chart = section[section.index("chart-ai-assisted") :]
    counts = json.loads(re.search(r'"data": (\[[^\]]*\])', chart).group(1))
    assert counts == [0, 4, 0, 0, 0, 0, 0, 0, 0, 3, 0, 2]
    assert '"50.0% of 8 that month"' in chart
    assert '"25.0% of 12 that month"' in chart

    # the assistants, the most named first; Copilot made two of its commits itself
    rows = re.findall(r"<tr><td>(.*?)</td><td class=\"num\">(\d+)</td>", section)
    assert rows == [("GitHub Copilot", "7"), ("Claude", "3")]
    assert (
        '<td class="num">2</td><td class="nowrap">2025-03-05</td><td class="nowrap">2026-01-09</td>'
    ) in section
    assert '<span style="width: 42.9%">' in section
    # 7 + 3 is more than 9: one commit names both
    assert "A commit that names two assistants is counted under both." in section
    assert "<summary>What is counted</summary>" in section


def _with_one_assisted_commit(data):
    """The fixture's six months of history, with one commit that names an assistant."""
    data.get_total_commits.return_value = 50
    data.ai_assisted_commits = 1
    data.ai_assisted_authored = 0
    data.ai_assisted_by_month = {"2023-04": 1}
    data.ai_assistants = {
        "Aider": {
            "commits": 1,
            "authored": 0,
            "first_commit_stamp": _stamp(2023, 4, 3),
            "last_commit_stamp": _stamp(2023, 4, 3),
        }
    }
    return data


def test_ai_assisted_section_of_a_short_history_with_one_commit(mock_data_collector):
    data = _with_one_assisted_commit(mock_data_collector)
    section = HTMLReportCreator()._ai_assisted_html(data)
    assert "1 of 50 commits (2.0%) names an AI coding assistant" in section
    # nothing an assistant made itself, and no "last 12 months" of a history of six
    assert "under its own account" not in section
    assert "In the last 12 months" not in section
    assert "counted under both" not in section
    # the chart covers the history, which is shorter than a year
    labels = json.loads(re.search(r"var labels = (\[.*?\]);", section).group(1))
    assert labels == month_range(data.commits_by_month)


def test_ai_assisted_section_starts_where_the_assistants_do(mock_data_collector):
    """Older than a year: the chart goes back to the first commit that names one,
    and a long stretch without commits is shaded as on the other charts."""
    data = _with_assistants(mock_data_collector)
    data.commits_by_month = {"2022-01": 20, "2023-06": 18, "2025-11": 12, "2026-01": 10}
    data.ai_assisted_by_month = {"2023-06": 4, "2025-11": 3, "2026-01": 2}
    section = HTMLReportCreator()._ai_assisted_html(data)
    labels = json.loads(re.search(r"var labels = (\[.*?\]);", section).group(1))
    assert labels[0] == "2023-06"
    assert labels[-1] == "2026-01"
    assert "2022-01" not in labels
    # the longest stretch without commits is inside it
    assert "No commits 2023-07 \\u2013 2025-10" in section
    assert "In the last 12 months: 5 of 22 (22.7%)." in section


def test_ai_assisted_section_escapes_what_it_shows(mock_data_collector):
    data = _with_assistants(mock_data_collector)
    data.ai_assistants = {"<b>Robo</b>": dict(data.ai_assistants["Claude"])}
    section = HTMLReportCreator()._ai_assisted_html(data)
    assert "&lt;b&gt;Robo&lt;/b&gt;" in section
    assert "<b>Robo</b>" not in section


def test_authors_page_has_the_ai_assisted_section(mock_data_collector, temp_dir):
    HTMLReportCreator().create(_with_one_assisted_commit(mock_data_collector), temp_dir)
    authors = _read_page(temp_dir, "authors.html")
    assert authors.count('<h2 id="ai-assisted_commits">') == 1
    # after the people, before the tables that rank them
    assert authors.index("ai-assisted_commits") < authors.index("Top author per year and month")


@pytest.mark.parametrize(
    "month, count, expected",
    [
        ("2026-01", 0, "2026-01"),
        ("2026-01", 1, "2025-12"),
        ("2026-01", 11, "2025-02"),
        ("2026-12", 11, "2026-01"),
        ("2026-03", 27, "2023-12"),
    ],
)
def test_months_back(month, count, expected):
    assert months_back(month, count) == expected


def test_sum_since():
    by_month = {"2025-01": 1, "2025-02": 2, "2025-12": 4, "2026-01": 8}
    assert sum_since(by_month, "2025-02") == 14
    assert sum_since(by_month, "2026-02") == 0
    assert sum_since({}, "2025-01") == 0


@pytest.mark.parametrize(
    "part, whole, expected",
    [
        (13, 583, "2.2%"),
        (1, 2, "50.0%"),
        (5, 5, "100.0%"),
        # too small for one decimal, but not nothing
        (10, 130654, "&lt;0.1%"),
        (88, 169347, "0.1%"),
        # short of all of them: not "100.0%"
        (3634, 3635, "99.9%"),
        (1999, 2000, "99.9%"),
        (1998, 2000, "99.9%"),
        (1989, 2000, "99.5%"),
        (0, 100, "0%"),
        (0, 0, "0%"),
        (3, 0, "0%"),
    ],
)
def test_share_text(part, whole, expected):
    assert share_text(part, whole) == expected


# ── share tags and cards ─────────────────────────────────────────────────


def test_share_tags_without_an_address():
    tags = share_meta_html(
        "CPython: Authors", "CPython: 1 commit.", "", "authors.html", "share-card.png"
    )
    assert '<meta name="description" content="CPython: 1 commit.">' in tags
    assert '<meta property="og:title" content="CPython: Authors">' in tags
    # places that show a link want absolute addresses: with none, no image either
    assert "og:url" not in tags
    assert "og:image" not in tags
    assert '<meta name="twitter:card" content="summary">' in tags


def test_share_tags_with_an_address_and_a_card():
    site = "https://example.com/report/"
    tags = share_meta_html("A <b>repo</b>", 'Say "hi"', site, "authors.html", "share-card.png")
    assert '<meta property="og:url" content="https://example.com/report/authors.html">' in tags
    assert '<meta property="og:image" content="https://example.com/report/share-card.png">' in tags
    assert '<meta property="og:image:width" content="1200">' in tags
    assert '<meta name="twitter:card" content="summary_large_image">' in tags
    assert '<meta name="twitter:image" content="https://example.com/report/share-card.png">' in tags
    # what the page says is escaped as an attribute
    assert 'content="A &lt;b&gt;repo&lt;/b&gt;"' in tags
    assert 'content="Say &quot;hi&quot;"' in tags
    # the index is the address itself
    index = share_meta_html("t", "d", site, "index.html", "")
    assert '<meta property="og:url" content="https://example.com/report/">' in index
    assert "og:image" not in index


def test_share_description(mock_data_collector):
    assert report_share_description(mock_data_collector) == (
        "test-project: 50 commits by 3 authors, 2022 to 2023. A report made with gitstats."
    )
    mock_data_collector.get_total_commits.return_value = 1
    mock_data_collector.get_total_authors.return_value = 1
    mock_data_collector.get_first_commit_date.return_value = datetime.datetime(2023, 1, 1)
    assert report_share_description(mock_data_collector) == (
        "test-project: 1 commit by 1 author, 2023. A report made with gitstats."
    )
    mock_data_collector.get_first_commit_date.return_value = None
    assert report_share_description(mock_data_collector).endswith(
        "by 1 author. A report made with gitstats."
    )


def test_share_card_of_a_report(mock_data_collector):
    mock_data_collector.project_name = "<b>proj</b>"
    mock_data_collector.commits_by_year = {2019: 5, 2021: 20, 2023: 10}
    card = report_share_card_html(mock_data_collector)
    assert card.startswith("<!DOCTYPE html>")
    assert "width:1200px;height:630px" in card
    assert "<h1>&lt;b&gt;proj&lt;/b&gt;</h1>" in card
    assert "<dt>Commits</dt><dd>50</dd>" in card
    assert "<dt>Lines of code</dt><dd>2,000</dd>" in card
    assert "2022-12-01 &rarr; 2023-04-01" in card
    # commits per year, the busiest the tallest, a year without commits flat
    assert card.count('<i style="height:') == 5
    assert '<i style="height:100.0%"></i>' in card
    assert '<i style="height:0.0%"></i>' in card
    assert "<span>2019</span><span>commits per year</span><span>2023</span>" in card
    # no AI-assisted commits counted: no line about them
    assert "AI coding assistant" not in card
    assert "github.com/shenxianpeng/gitstats" in card


def test_share_card_of_a_short_history(mock_data_collector):
    # a history of less than three years shows its months
    card = report_share_card_html(mock_data_collector)
    assert "<span>2023-01</span><span>commits per month</span><span>2023-06</span>" in card
    assert card.count('<i style="height:') == 6
    mock_data_collector.commits_by_year = {}
    mock_data_collector.commits_by_month = {}
    assert "commits per" not in report_share_card_html(mock_data_collector)
    # no dates: no span under the name
    mock_data_collector.get_first_commit_date.return_value = None
    assert "&rarr;" not in report_share_card_html(mock_data_collector)


def test_share_card_says_how_many_recent_commits_name_an_assistant(mock_data_collector):
    mock_data_collector.ai_assisted_by_month = {"2023-02": 2, "2023-05": 4}
    card = report_share_card_html(mock_data_collector)
    # 6 of the 50 commits of the twelve months up to the last one
    assert "<strong>12.0%</strong> of the commits of the last 12 months" in card


def test_report_pages_carry_their_share_tags(mock_data_collector, temp_dir, monkeypatch):
    creator = HTMLReportCreator()
    creator.site_url = "https://example.com/r/"
    monkeypatch.setitem(load_config(), "share_card", True)
    creator.create(mock_data_collector, temp_dir)
    authors = _read_page(temp_dir, "authors.html")
    assert '<meta property="og:title" content="test-project: Authors">' in authors
    assert '<meta property="og:url" content="https://example.com/r/authors.html">' in authors
    assert '<meta property="og:image" content="https://example.com/r/share-card.png">' in authors
    assert "test-project: 50 commits by 3 authors" in authors
    index = _read_page(temp_dir, "index.html")
    assert '<meta property="og:title" content="test-project">' in index
    assert '<meta property="og:url" content="https://example.com/r/">' in index
    # the card the image is rendered from is written next to the pages
    assert "<h1>test-project</h1>" in _read_page(temp_dir, "share-card.html")


def test_report_pages_without_share_card(mock_data_collector, temp_dir):
    creator = HTMLReportCreator()
    creator.site_url = "https://example.com/r/"
    creator.create(mock_data_collector, temp_dir)
    authors = _read_page(temp_dir, "authors.html")
    # a title and a description all the same, but no image the publisher may not render
    assert '<meta property="og:title" content="test-project: Authors">' in authors
    assert "og:image" not in authors
    assert os.path.exists(os.path.join(temp_dir, "share-card.html"))


def test_badges_page_offers_the_ai_assisted_badge_when_counted(mock_data_collector, temp_dir):
    content = _badges_page(mock_data_collector, temp_dir)
    assert 'data-badge="ai-assisted"' not in content  # a Mock does not count them

    mock_data_collector.ai_assisted_by_month = {}
    content = _badges_page(mock_data_collector, temp_dir)
    assert 'data-kind="style" data-badge="ai-assisted"' in content
    assert '<img src="badges/flat/ai-assisted.svg" alt="AI-assisted commits">' in content


# ── commits by organization ──────────────────────────────────────────────


def test_organizations_section(mock_data_collector):
    section = HTMLReportCreator()._organizations_html(mock_data_collector)
    assert '<h2 id="commits_by_organization">' in section
    # 13 of the 20 commits, at two organizations
    assert "13 of 20 commits (65.0%) come from an address at 2 organizations" in section
    assert "not who paid for the work" in section
    rows = re.findall(r"<tr><td>(.*?)</td>", section)
    assert rows[:2] == ["example.com", "test.org"]
    # example.com: 9 commits, 45% of all, every one in the last 12 months, two addresses
    assert '<td>example.com</td><td class="num">9</td><td class="num">45.0%</td>' in section
    assert '<td class="num">9</td><td class="num">2</td>' in section
    # by quarter, the latest first, with the share of each kind of address
    assert "Where the commits come from, by quarter" in section
    q2 = section.index('<td class="nowrap">2023-Q2</td>')
    q1 = section.index('<td class="nowrap">2023-Q1</td>')
    assert q2 < q1
    assert (
        '<td class="nowrap">2023-Q1</td><td class="num">5</td>'
        '<td class="num">80.0%</td><td class="num">0%</td><td class="num">20.0%</td>' in section
    )
    labels = (
        "Organizations",
        "One-person domains",
        "Personal email",
        "Hidden (noreply)",
        "Unknown",
        "Bots",
    )
    for label in labels:
        assert f'<th class="num">{label}</th>' in section


def test_organizations_section_names_one_organization(mock_data_collector):
    del mock_data_collector.organizations["test.org"]
    section = HTMLReportCreator()._organizations_html(mock_data_collector)
    assert "come from an address at 1 organization," in section


def test_organizations_section_escapes_the_domain(mock_data_collector):
    mock_data_collector.organizations["<b>.org"] = mock_data_collector.organizations.pop("test.org")
    section = HTMLReportCreator()._organizations_html(mock_data_collector)
    assert "&lt;b&gt;.org" in section
    assert "<b>.org" not in section


def test_organizations_section_is_left_out_with_one_person_domains_only(mock_data_collector):
    mock_data_collector.organization_authors = {"example.com": 1, "test.org": 1}
    assert HTMLReportCreator()._organizations_html(mock_data_collector) == ""


def test_organizations_section_is_left_out_without_any(mock_data_collector):
    creator = HTMLReportCreator()
    mock_data_collector.affiliation_by_month = {"2023-01": {"personal": 3}}
    assert creator._organizations_html(mock_data_collector) == ""
    # data collected before addresses were sorted
    mock_data_collector.affiliation_by_month = None
    assert creator._organizations_html(mock_data_collector) == ""


def test_overview_keeps_an_empty_place_for_what_stands_out(mock_data_collector, temp_dir):
    """A report made alone shows nothing there; a portfolio fills it."""
    from gitstats.report_creator import INSIGHTS_END, INSIGHTS_START

    HTMLReportCreator().create(mock_data_collector, temp_dir)
    page = _read_page(temp_dir, "index.html")
    assert INSIGHTS_START + INSIGHTS_END in page
    # under the heading and its meta line, above the tiles
    assert page.index('class="page-meta"') < page.index(INSIGHTS_START) < page.index("stat-tiles")


# ── counts, charts and tags said right ───────────────────────────────────


def test_plural():
    from gitstats.report_creator import plural

    assert plural(1, "commit") == "1 commit"
    assert plural(0, "commit") == "0 commits"
    assert plural(1234, "file") == "1,234 files"
    assert plural(2, "person", "people") == "2 people"
    assert plural(1, "author", number=False) == "author"
    assert plural(3, "author", number=False) == "authors"


def test_a_one_commit_report_says_its_counts_in_the_singular(mock_data_collector, temp_dir):
    data = mock_data_collector
    data.total_commits = 1
    data.get_total_commits = lambda: 1
    data.get_total_files = lambda: 1
    data.commits_by_year = {2023: 1}
    data.activity_by_hour_of_day = {10: 1}
    data.activity_by_day_of_week = {1: 1}
    data.activity_by_hour_of_week = {1: {10: 1}}
    HTMLReportCreator().create(data, temp_dir)
    text = " ".join(
        re.sub(r"<[^>]+>", " ", _read_page(temp_dir, page))
        for page in ("index.html", "activity.html", "lines.html", "history.html")
    )
    text = re.sub(r"\s+", " ", text)
    for wrong in ("1 commits", "in 1 files"):
        assert wrong not in text
    assert "in 1 file " in text


def test_chart_label():
    from gitstats.report_creator import chart_label

    assert chart_label("chart-commits-by-year", "bar", [2019, 2026]) == (
        "Bar chart of commits per year, 2019 to 2026"
    )
    assert chart_label("chart-x", "line", ["2026-10"]) == "Line chart, 2026-10"
    assert chart_label("chart-x", "bar", []) == "Bar chart"
    stamp = int(datetime.datetime(2026, 10, 20, 12).timestamp())
    assert chart_label("chart-lines-of-code", "line", [stamp], time_axis=True) == (
        "Line chart of lines of code over time, 2026-10-20"
    )


def test_render_chartjs_shows_the_points_of_a_short_line():
    """One or two points: a line chart draws nothing, or a bare line, without them."""
    creator = HTMLReportCreator()
    one = creator._render_chartjs(
        "c1", "line", [1792479600], [{"label": "L", "data": [1]}], time_axis=True
    )
    two = creator._render_chartjs(
        "c2",
        "line",
        ["X", "Y"],
        [{"label": "A", "data": [1, None, 2]}, {"label": "B", "data": [2]}],
    )
    highlight = creator._render_chartjs(
        "c3", "line", ["X"], [{"label": "A", "data": [1]}, {"label": "B", "data": [2]}], highlight=1
    )
    for result in (one, two, highlight):
        assert '"pointRadius": 3' in result
        assert '"pointRadius": 0' not in result


def test_time_axis_widens_around_a_single_moment():
    from gitstats.report_creator import CHART_SCRIPT

    assert "if (xs.length && min === max) {" in CHART_SCRIPT
    assert "min -= 15 * 864e5;" in CHART_SCRIPT


@pytest.mark.parametrize(
    ("count", "limit", "expected"),
    [
        (2, 50, "A0 (10), A1 (9)"),
        (3, -1, "A0 (10), A1 (9), A2 (8)"),
        (2, 1, "A0 (10), <em>and 1 more author</em>"),
        (2, 0, "<em>and 2 more authors</em>"),
        (
            5,
            50,
            'A0 (10), A1 (9), A2 (8) <details class="tag-authors"><summary>+2 more</summary>'
            "A3 (7), A4 (6)</details>",
        ),
        (
            6,
            4,
            'A0 (10), A1 (9), A2 (8) <details class="tag-authors"><summary>+3 more</summary>'
            "A3 (7), <em>and 2 more authors</em></details>",
        ),
    ],
)
def test_tag_authors_html(count, limit, expected):
    from gitstats.report_creator import tag_authors_html

    names = [f"A{n}" for n in range(count)]
    commits = {name: 10 - n for n, name in enumerate(names)}
    assert tag_authors_html(names, commits, limit) == expected


def test_tags_page_folds_long_author_lists(mock_data_collector, temp_dir):
    authors = {f"Author {n}": 100 - n for n in range(20)}
    mock_data_collector.tags = {"v1.0": {"date": "2023-05-01", "commits": 2000, "authors": authors}}
    creator = HTMLReportCreator()
    creator.title = mock_data_collector.project_name
    creator.data = mock_data_collector
    creator.create_tags_html(mock_data_collector, temp_dir)
    page = _read_page(temp_dir, "tags.html")
    assert '<details class="tag-authors"><summary>+17 more</summary>' in page
    css_path = os.path.join(os.path.dirname(__file__), "..", "gitstats", "gitstats.css")
    with open(css_path, encoding="utf-8") as f:
        assert "details.tag-authors > summary {" in f.read()


def test_a_year_whose_lines_count_in_a_later_one(mock_data_collector, temp_dir):
    """Along the main line of history, a branch's lines count in the year it
    is merged: the years of its commits show a dash, and why."""
    from gitstats.report_creator import FIRST_PARENT_LINES

    data = mock_data_collector
    data.commits_by_year = {2023: 50, 2024: 2}
    data.lines_added_by_year = {2023: 3000}
    data.lines_removed_by_year = {2023: 1000}
    data.author_of_year = {2023: {"Alice Smith": 50}, 2024: {"Bob": 2}}
    creator = HTMLReportCreator()
    creator.title = data.project_name
    creator.data = data
    creator.create_history_html(data, temp_dir)
    creator.create_activity_html(data, temp_dir)
    history = _read_page(temp_dir, "history.html")
    assert "2 commits (3.8%) &middot; lines &mdash; &middot; 1 author" in history
    assert "+3,000 / &minus;1,000 lines" in history
    assert f'<p class="history-people">{FIRST_PARENT_LINES}</p>' in history
    activity = _read_page(temp_dir, "activity.html")
    assert '<tr><td>2024</td><td class="num">2 (4.0%)</td><td class="num">&mdash;</td>' in activity
    assert f'<p class="section-note">&mdash;: {FIRST_PARENT_LINES}</p>' in activity


def test_lines_uncounted_only_along_the_main_line(monkeypatch):
    import gitstats
    from gitstats.report_creator import lines_uncounted

    assert lines_uncounted(2, 0, 0) is True
    assert lines_uncounted(2, 1, 0) is False
    assert lines_uncounted(0, 0, 0) is False
    # every commit counted: no lines is no lines
    monkeypatch.setitem(gitstats._config, "linear_linestats", 0)
    assert lines_uncounted(2, 0, 0) is False


def test_report_nav_starts_with_its_brand(mock_data_collector):
    from gitstats.report_creator import REPORT_BRAND

    creator = HTMLReportCreator()
    creator.data = mock_data_collector
    f = StringIO()
    creator.print_nav(f, "index.html")
    assert REPORT_BRAND in f.getvalue()


def test_files_without_an_extension_are_not_an_extension(mock_data_collector, temp_dir):
    """The "no extension" row is in the table, not in the count of extensions."""
    mock_data_collector.extensions = {
        "py": {"files": 1, "lines": 5},
        "md": {"files": 1, "lines": 2},
        "": {"files": 2, "lines": 5},
    }
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    for name in ("index.html", "files.html"):
        with open(os.path.join(temp_dir, name), encoding="utf-8") as f:
            content = f.read()
        assert "2 extensions" in content, name
        assert "3 extensions" not in content, name
    with open(os.path.join(temp_dir, "files.html"), encoding="utf-8") as f:
        assert "<em>no extension</em>" in f.read()


# ── each page: its title, its frame ──────────────────────────────────────


def test_page_title():
    assert page_title("flask: Authors") == "GitStats - flask: Authors"
    # "GitStats" is in the title once
    assert page_title("GitStats Portfolio") == "GitStats Portfolio"
    assert page_title("amazon.com in GitStats Gallery") == "amazon.com in GitStats Gallery"


def test_each_page_has_its_own_title(mock_data_collector, temp_dir):
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    for page, label in NAV_PAGES:
        title = re.search(r"<title>([^<]*)</title>", _read_page(temp_dir, page)).group(1)
        expected = "test-project" if page == "index.html" else f"test-project: {label}"
        assert title == f"GitStats - {expected}", page


def test_the_ai_insights_page_has_its_own_title():
    creator = HTMLReportCreator()
    creator.title = "flask"
    f = StringIO()
    creator.print_header(f, "ai-insights.html")
    assert "<title>GitStats - flask: AI Insights</title>" in f.getvalue()


def test_tag_names_sort_as_text(mock_data_collector, temp_dir):
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    assert '<th data-sort-as="text">Name</th>' in _read_page(temp_dir, "tags.html")


def test_every_page_has_its_frame(mock_data_collector, temp_dir):
    """A skip link first, then the nav, the page's content in <main>, and the
    footer after it; no header cell without a name."""
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    pages = [name for name in os.listdir(temp_dir) if name.endswith(".html")]
    assert len(pages) > 10
    for name in pages:
        page = _read_page(temp_dir, name)
        if name == "share-card.html":
            continue
        assert page.count(SKIP_LINK) == 1, name
        assert page.count(NAV_START) == page.count('<main id="main">') == 1, name
        assert page.count("</main>") == page.count('<footer class="footer">') == 1, name
        body = page.index("<body>")
        assert (
            body
            < page.index(SKIP_LINK)
            < page.index(NAV_START)
            < page.index('<main id="main">')
            < page.index("</main>")
            < page.index('<footer class="footer">')
            < page.index("</body>")
        ), name
        assert not re.search(r"<th[^>]*></th>", page), name


def test_one_author_and_one_tag_are_not_all(mock_data_collector, temp_dir):
    mock_data_collector.get_total_authors.return_value = 1
    mock_data_collector.tags = {"v1": dict(mock_data_collector.tags["v1.0.0"])}
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    index = _read_page(temp_dir, "index.html")
    assert '<a href="authors.html">The author in detail &rarr;</a>' in index
    assert '<a href="tags.html">The tag in detail &rarr;</a>' in index
    assert "All 1 " not in index


def test_an_age_of_one_day(mock_data_collector, temp_dir):
    info = mock_data_collector.get_author_info("Alice Smith")
    info["timedelta"] = datetime.timedelta(days=1)
    mock_data_collector.get_author_info = lambda author, info=info: info
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    assert 'title="1 day" data-sort="1"' in _read_page(temp_dir, "authors.html")


def test_the_top_author_tables_scroll_on_a_phone(mock_data_collector, temp_dir):
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    authors = _read_page(temp_dir, "authors.html")
    assert '<table class="sortable period-table" id="aoy">' in authors
    assert '<table class="sortable period-table" id="aom">' in authors


def test_a_few_hotspots_have_no_medians_to_mark(mock_data_collector, temp_dir):
    page = _hotspots_html(mock_data_collector, temp_dir)
    assert "The dashed lines mark the median file size" in page
    mock_data_collector.hotspot_files = {
        "main.py": {"churn": 1, "lines": 1, "score": 1.0},
    }
    page = _hotspots_html(mock_data_collector, temp_dir)
    assert "dashed lines" not in page
    assert (
        "a bigger dot is a higher score. The highest score is numbered as in the list. "
        "Both axes are logarithmic."
    ) in page
    # one file is not "large, changed often": it is numbered, not in color
    assert '<span class="hotspot-rank numbered">1</span>' in page


@pytest.mark.parametrize("month_axis", [False, True])
def test_a_single_point_is_in_the_middle(month_axis):
    creator = HTMLReportCreator()
    labels = ["2026-10"]
    one = creator._render_chartjs(
        "c", "line", labels, [{"label": "C", "data": [1]}], month_axis=month_axis
    )
    assert "x: { offset: true, ticks:" in one
    two = creator._render_chartjs(
        "c", "line", labels * 2, [{"label": "C", "data": [1, 2]}], month_axis=month_axis
    )
    assert "offset: true" not in two
    bar = creator._render_chartjs("c", "bar", labels, [{"label": "C", "data": [1]}])
    assert "offset: true" not in bar


# ── the overview: what to look at first, and the last 12 months ──────────


def _history(data, before: int, recent: int, first: str = "2019-01") -> None:
    """A history from ``first`` whose last 12 months (2022-07 to 2023-06) have
    ``recent`` commits and the 12 before them ``before``."""
    data.commits_by_month = {first: 5, "2022-01": before, "2023-06": recent}
    data.commits_by_month = {m: n for m, n in data.commits_by_month.items() if n}
    data.get_total_commits.return_value = sum(data.commits_by_month.values())


def test_last_year_commits_are_the_12_months_up_to_the_last_commit(mock_data_collector):
    _history(mock_data_collector, before=40, recent=100)
    recent, before = last_year_commits(mock_data_collector)
    assert list(recent) == [
        "2022-07", "2022-08", "2022-09", "2022-10", "2022-11", "2022-12",
        "2023-01", "2023-02", "2023-03", "2023-04", "2023-05", "2023-06",
    ]  # fmt: skip
    assert list(before)[0] == "2021-07"
    assert list(before)[-1] == "2022-06"
    assert (sum(recent.values()), sum(before.values())) == (100, 40)
    # data that has no commits by month
    assert last_year_commits(SimpleNamespace()) == (None, {})
    assert last_year_commits(SimpleNamespace(commits_by_month={})) == (None, {})


@pytest.mark.parametrize(
    "days, text",
    [(7050, "19 years"), (400, "1 year"), (120, "3 months"), (59, "59 days"), (1, "1 day")],
)
def test_span_text(days, text):
    assert span_text(days) == text


def test_sparkline_is_sized_by_attributes():
    svg = sparkline_svg([0, 5, 10, 1])
    # no bar for no commits; the smallest count still shows; the largest is 28px
    assert re.findall(r'<rect x="(\d+)" y="(\d+)" width="5" height="(\d+)"/>', svg) == [
        ("7", "14", "14"),
        ("14", "0", "28"),
        ("21", "25", "3"),
    ]
    assert 'viewBox="0 0 26 28"' in svg
    assert 'aria-hidden="true"' in svg
    # a server that forbids inline styles (Jenkins) would drop a styled bar
    assert "style" not in svg
    assert sparkline_svg([0, 0]).count("<rect") == 0


def _signals(data) -> dict[str, dict[str, str]]:
    return {signal["page"]: signal for signal in overview_signals(data)}


def test_overview_signals_of_the_sample_project(mock_data_collector):
    found = _signals(mock_data_collector)
    # two of three people own more than half of the files; four files and a
    # history of six months give no hotspot share and no trend
    assert list(found) == ["Code Ownership", "Authors"]
    assert found["Code Ownership"] == {
        "level": "watch",
        "tag": "Watch",
        "title": "Bus factor is 2",
        "detail": "Alice Smith and Bob Jones are, between them, primary owner of 4 of 4 "
        "files. 2 files have only ever been changed by one person.",
        "href": "ownership.html",
        "page": "Code Ownership",
    }
    # everyone is still active, which says nothing: the two shares do
    assert found["Authors"]["title"] == "2 authors made 90.0% of the commits"
    assert found["Authors"]["detail"] == "Alice Smith 60.0% and Bob Jones 30.0%."


def test_a_bus_factor_of_one_is_a_risk(mock_data_collector):
    mock_data_collector.author_files = {
        "Alice <Smith>": {"a.py": 5, "b.py": 5, "c.py": 5},
        "Bob Jones": {"a.py": 1},
    }
    signal = _signals(mock_data_collector)["Code Ownership"]
    assert (signal["level"], signal["tag"], signal["title"]) == ("risk", "Risk", "Bus factor is 1")
    assert signal["detail"] == (
        "Alice &lt;Smith&gt; is the primary owner of 3 of 3 files. "
        "2 files have only ever been changed by one person."
    )
    # one file that only one person has changed is said in the singular, and
    # none is not said at all
    mock_data_collector.author_files = {
        "Alice Smith": {"a.py": 5, "b.py": 5},
        "Bob Jones": {"a.py": 1},
    }
    assert _signals(mock_data_collector)["Code Ownership"]["detail"] == (
        "Alice Smith is the primary owner of 2 of 2 files. "
        "1 file has only ever been changed by one person."
    )
    mock_data_collector.author_files["Bob Jones"]["b.py"] = 1
    assert _signals(mock_data_collector)["Code Ownership"]["detail"] == (
        "Alice Smith is the primary owner of 2 of 2 files."
    )
    # a project one person has written has nobody else to share its files with
    mock_data_collector.author_files = {"Alice Smith": {"a.py": 5, "b.py": 5}}
    assert "Code Ownership" not in _signals(mock_data_collector)
    # it takes three of the four to own more than half: not few enough to say
    mock_data_collector.author_files = {
        "Alice Smith": {"a.py": 5, "b.py": 5},
        "Bob Jones": {"c.py": 5, "d.py": 5},
        "Charlie Brown": {"e.py": 5, "f.py": 5},
        "Dana White": {"g.py": 5, "h.py": 5},
    }
    assert "Code Ownership" not in _signals(mock_data_collector)


def test_the_authors_signal_needs_a_few_authors_with_most_of_the_commits(mock_data_collector):
    authors = mock_data_collector.authors
    authors["Alice Smith"]["commits_frac"] = 85.0
    authors["Bob Jones"]["commits_frac"] = 10.0
    assert (
        _signals(mock_data_collector)["Authors"]["title"] == "Alice Smith made 85.0% of the commits"
    )
    authors["Alice Smith"]["commits_frac"] = 45.0
    authors["Bob Jones"]["commits_frac"] = 30.0
    assert "Authors" not in _signals(mock_data_collector)  # 75% between two
    # one of the three has not committed in the last 12 months
    authors["Alice Smith"]["commits_frac"] = 60.0
    authors["Charlie Brown"]["date_last"] = "2021-04-20"
    authors["Charlie Brown"]["date_first"] = "2021-03-10"
    assert _signals(mock_data_collector)["Authors"]["detail"] == (
        "2 of 3 authors committed in the last 12 months, 2 of them for the first time."
    )
    # two authors are the whole project
    mock_data_collector.authors = {name: authors[name] for name in ("Alice Smith", "Bob Jones")}
    assert "Authors" not in _signals(mock_data_collector)


def test_the_hotspots_signal_is_the_share_of_the_ten_highest_scores(mock_data_collector):
    def files(count: int, top_score: float) -> dict:
        return {
            f"f{i:02d}.py": {"lines": 100, "churn": 5, "score": top_score if i < 10 else 1.0}
            for i in range(count)
        }

    mock_data_collector.hotspot_files = files(30, 4.0)  # 40 of 60
    signal = _signals(mock_data_collector)["Hotspots"]
    assert signal["title"] == "10 files hold 66.7% of the hotspot score"
    assert signal["detail"] == (
        '<span class="path">f00.py</span> leads: 100 lines, changed 5 times.'
    )
    mock_data_collector.hotspot_files = files(30, 1.0)  # a third: spread evenly
    assert "Hotspots" not in _signals(mock_data_collector)
    mock_data_collector.hotspot_files = files(10, 4.0)  # the ten are all there are
    assert "Hotspots" not in _signals(mock_data_collector)


@pytest.mark.parametrize(
    "before, recent, level, title",
    [
        (40, 100, "up", "Activity more than doubled in a year"),
        (40, 60, "up", "Activity is up 50% on the year before"),
        (40, 44, None, ""),
        (40, 36, None, ""),
        (40, 28, "down", "Activity is down 30% on the year before"),
        (40, 10, "down", "Activity fell by more than half in a year"),
        (0, 12, "up", "Commits again, after 12 months without any"),
    ],
)
def test_the_trend_signal_compares_the_last_12_months_with_those_before(
    mock_data_collector, before, recent, level, title
):
    _history(mock_data_collector, before, recent)
    signal = _signals(mock_data_collector).get("Activity")
    if level is None:
        assert signal is None
        return
    assert (signal["level"], signal["tag"], signal["title"]) == (level, "Trend", title)
    assert signal["detail"] == (
        f"{recent} commits in the last 12 months, against {before} in the 12 months before."
    )


def test_a_project_in_its_second_year_has_no_trend(mock_data_collector):
    # the 12 months before the last 12 began before the project did
    _history(mock_data_collector, before=5, recent=100, first="2021-12")
    assert "Activity" not in _signals(mock_data_collector)


def test_signals_are_a_section_of_the_overview(mock_data_collector, temp_dir):
    assert signals_html([]) == ""
    html = _render_index(mock_data_collector, temp_dir)
    section = html[html.index('<section class="signals-section">') :]
    section = section[: section.index("</section>")]
    assert "Worth a look</a></h2>" in section
    assert (
        '<li class="signal signal-watch"><span class="signal-tag">Watch</span>'
        '<strong class="signal-title">Bus factor is 2</strong>'
    ) in section
    assert '<a class="signal-link" href="ownership.html">Code Ownership &rarr;</a>' in section
    # under what a portfolio writes about the project, above its numbers
    assert html.index(INSIGHTS_END) < html.index("signals-section") < html.index("stat-tiles")
    # nothing to point at: no section
    mock_data_collector.author_files = {}
    mock_data_collector.get_authors.side_effect = lambda limit=None: ["Alice Smith"]
    assert "signals-section" not in _render_index(mock_data_collector, temp_dir)


def test_overview_of_a_long_history_shows_the_last_12_months(mock_data_collector, temp_dir):
    _history(mock_data_collector, before=40, recent=100)
    mock_data_collector.authors["Charlie Brown"]["date_last"] = "2021-04-20"
    html = _render_index(mock_data_collector, temp_dir)
    # the tiles say how the project is doing now, the commits with the months as bars
    assert (
        '<dt>Commits</dt><dd class="stat-value"><span class="stat-spark">145<svg class="sparkline"'
    ) in html
    assert '<dd class="stat-note">100 in the last 12 months</dd>' in html
    assert '<dd class="stat-note">2 active in the last 12 months</dd>' in html
    # and a chart of them next to the years
    assert '<div class="overview-charts"><section>' in html
    assert "Last 12 months</a></h2>" in html
    assert (
        '<p class="section-note">100 commits from Jul 2022 to Jun 2023, up from 40 in '
        "the 12 months before.</p>"
    ) in html
    chart = html[html.index("getElementById('chart-last-12-months')") :]
    chart = chart[: chart.index("</script>")]
    assert 'var labels = ["Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb"' in chart
    assert '"data": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 100]' in chart
    # twelve short labels in a third of the width: none is dropped
    assert "autoSkip: false" in chart
    # the last commit was not this month: its month is whole
    assert "chart-footnote" not in html


@pytest.mark.parametrize(
    "before, recent, wording",
    [
        (100, 40, "40 commits from Jul 2022 to Jun 2023, down from 100 in the 12 months before."),
        (40, 40, "40 commits from Jul 2022 to Jun 2023, as many as in the 12 months before."),
        (0, 1, "1 commit from Jul 2022 to Jun 2023; none in the 12 months before."),
    ],
)
def test_the_last_12_months_against_those_before(
    mock_data_collector, temp_dir, before, recent, wording
):
    _history(mock_data_collector, before, recent)
    assert f'<p class="section-note">{wording}</p>' in _render_index(mock_data_collector, temp_dir)


def test_a_month_that_is_not_over_is_said_so(mock_data_collector, temp_dir):
    now = datetime.datetime.now()
    mock_data_collector.commits_by_month = {"2019-01": 5, now.strftime("%Y-%m"): 3}
    html = _render_index(mock_data_collector, temp_dir)
    assert (
        f'<p class="chart-footnote">{now.strftime("%b %Y")} was not over when this report '
        "was made.</p>"
    ) in html


def test_a_history_of_a_year_or_less_keeps_the_pace(mock_data_collector, temp_dir):
    # every commit is in the last 12 months: they are the total, not news
    html = _render_index(mock_data_collector, temp_dir)
    assert "Last 12 months" not in html
    assert "overview-charts" not in html
    assert "sparkline" not in html
    assert "12.5 per active day" in html
    assert "16.7 commits per author" in html
    # without tags there is no release to date the project by
    mock_data_collector.tags = {}
    html = _render_index(mock_data_collector, temp_dir)
    assert '<dt>Longest Streak</dt><dd class="stat-value">4 days</dd>' in html
    assert "Latest Release" not in html


def test_contributors_beyond_the_top_five_are_one_row(mock_data_collector, temp_dir):
    people = {
        f"Author {n}": {
            **mock_data_collector.authors["Charlie Brown"],
            "commits": 2,
            "commits_frac": 4.0,
        }
        for n in range(1, 6)
    }
    mock_data_collector.authors = {**mock_data_collector.authors, **people}
    mock_data_collector.get_total_authors.return_value = 8
    html = _render_index(mock_data_collector, temp_dir)
    table = html[html.index("Top contributors</a></h2>") :]
    table = table[: table.index("</table>")]
    assert table.count('<td class="num rank">') == 5
    # the five listed have every one of the sample's 50 commits and more: counts
    # that leave nothing over get no row, rather than one with nothing in it
    assert '<tr class="share-rest">' not in table
    # 60 commits, 30 + 15 + 5 + 2 + 2 of them listed: the rows add up to all of them
    mock_data_collector.get_total_commits.return_value = 60
    html = _render_index(mock_data_collector, temp_dir)
    assert (
        '<tr class="share-rest"><td></td><td>3 other authors</td><td class="num">6</td>'
        '<td class="num">10.0%</td>'
        '<td class="share-cell"><span class="share-bar share-bar-muted" aria-hidden="true">'
        '<span style="width: 10.0%"></span></span></td></tr>'
    ) in html


@pytest.mark.parametrize("page", [page for page, _ in NAV_PAGES])
def test_every_page_says_how_the_report_was_made(mock_data_collector, temp_dir, page):
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    content = _read_page(temp_dir, page)
    footer = content[content.index('<footer class="footer">') :]
    made = re.search(
        r"gitstats</a> (\S+) &middot; (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) in \d+ s &middot; (.+?)</span>",
        footer,
    )
    assert made, footer
    # the same on every page of a report, and no longer under the overview's heading
    assert made[2] in _read_page(temp_dir, "index.html")
    assert "generated" not in re.search(r'<p class="page-meta">(.*?)</p>|$', content)[0]


def test_a_footer_without_the_time_of_the_run_leaves_it_out():
    # a page written before any data was collected has no start to count from
    creator = HTMLReportCreator()
    f = StringIO()
    creator.print_footer(f)
    footer = f.getvalue()
    assert re.search(
        r"gitstats</a> \S+ &middot; \d{4}-\d\d-\d\d \d\d:\d\d:\d\d &middot; [^<]+</span>", footer
    )
    assert " s &middot; " not in footer
    # what the first page said is what the others say
    again = StringIO()
    creator.print_footer(again)
    assert again.getvalue() == footer


# ── the code, apart from the documentation and the assets ────────────────


def test_hotspots_and_ownership_leave_out_what_is_not_code(mock_data_collector, temp_dir):
    """A guide rewritten with every release, the AUTHORS file and a logo are
    no hotspots, and who changed them says nothing of who knows the code."""
    data = mock_data_collector
    data.head_files = [
        "main.py",
        "utils.py",
        "setup.py",
        "Dockerfile",
        "docs/guide.rst",
        "AUTHORS",
        "ext/logo.ai",
    ]
    data.hotspot_files["docs/guide.rst"] = {"churn": 90, "lines": 900, "score": 2700.0}
    data.hotspot_files["ext/logo.ai"] = {"churn": 3, "lines": 8000, "score": 268.3}
    data.file_churn.update({"docs/guide.rst": 90, "AUTHORS": 60})
    data.author_files["Dana"] = {"docs/guide.rst": 90, "AUTHORS": 60, "ext/logo.ai": 3}
    HTMLReportCreator().create(data, temp_dir)

    hotspots = _read_page(temp_dir, "hotspots.html")
    assert _hotspot_points(hotspots)["points"][0][0] == "main.py"
    assert "docs/guide.rst" not in hotspots
    assert "ext/logo.ai" not in hotspots
    ownership = _read_page(temp_dir, "ownership.html")
    assert "Dana" not in ownership
    assert "AUTHORS" not in ownership


def test_a_repository_of_documents_has_them_analyzed(mock_data_collector, temp_dir):
    """With no code at all, the documents are what there is to look at."""
    data = mock_data_collector
    data.head_files = ["README.md", "docs/guide.rst"]
    data.hotspot_files = {
        "README.md": {"churn": 4, "lines": 50, "score": 28.3},
        "docs/guide.rst": {"churn": 9, "lines": 400, "score": 180.0},
    }
    data.file_churn = {"README.md": 4, "docs/guide.rst": 9}
    data.author_files = {"Ann": {"README.md": 4, "docs/guide.rst": 9}}
    HTMLReportCreator().create(data, temp_dir)

    assert [
        point[0] for point in _hotspot_points(_read_page(temp_dir, "hotspots.html"))["points"]
    ] == [
        "docs/guide.rst",
        "README.md",
    ]
    ownership = _read_page(temp_dir, "ownership.html")
    assert (
        '<dd class="stat-value">2</dd><dd class="stat-note">in the current tree</dd>'
    ) in ownership


def test_extensions_divide_their_lines_by_the_files_they_are_those_of(
    mock_data_collector, temp_dir
):
    """Vendored files of an extension count no lines: lines per file are
    those of the project's own files of it."""
    mock_data_collector.extensions = {
        "go": {"files": 10, "lines": 600, "line_files": 2},
        "ai": {"files": 1, "lines": 0, "line_files": 0},
    }
    HTMLReportCreator().create(mock_data_collector, temp_dir)
    files = _read_page(temp_dir, "files.html")
    table = files[files.index('id="ext"') :]
    table = table[: table.index("</table>")]
    assert '<tr><td>go</td><td class="num">10</td><td class="num">600</td>' in table
    assert '<td class="num">300</td>' in table
    assert (
        '<tr><td>ai</td><td class="num">1</td><td class="num">—</td><td class="num">—</td>'
        '<td class="num">—</td>'
    ) in table


def test_the_lines_chart_says_why_it_ends_elsewhere(mock_data_collector, temp_dir):
    """The chart adds up every diff; the lines of code are those of the code."""
    data = mock_data_collector
    data.changes_by_date = {1672531200: {"lines": 2600}}
    HTMLReportCreator().create(data, temp_dir)
    lines = _read_page(temp_dir, "lines.html")
    assert "That ends at 2,600, where the lines of code above, 2,000, leave out" in lines

    data.changes_by_date = {1672531200: {"lines": 2000}}
    HTMLReportCreator().create(data, temp_dir)
    assert "That ends at" not in _read_page(temp_dir, "lines.html")


# ── The Tags page's cadence, and the folded tables ───────────────────────


def _creator(data) -> HTMLReportCreator:
    creator = HTMLReportCreator()
    creator.title = data.project_name
    creator.data = data
    return creator


def _tag(date: str, commits: int = 1) -> dict:
    return {"date": date, "commits": commits, "authors": {"Alice Smith": commits}}


def test_tag_year_and_first_tag_year():
    assert tag_year(_tag("2026-05-14")) == 2026
    assert tag_year({"date": ""}) is None
    assert tag_year({}) is None
    assert first_tag_year({"a": _tag("2013-01-01"), "b": _tag("2011-06-01")}) == "2011"
    assert first_tag_year({"a": {"date": "unknown"}}) == "the start"


def test_release_gaps_count_days_since_the_previous_release_date():
    tags = {
        "v1": _tag("2026-01-01"),
        "v2": _tag("2026-01-11"),
        # an alias made the same day has the same gap
        "v2-alias": _tag("2026-01-11"),
        "v3": _tag("2026-02-10"),
        "broken": {"date": "not a date"},
    }
    assert release_gaps(tags) == {"v2": 10, "v2-alias": 10, "v3": 30}


def test_release_cadence_is_the_median_overall_and_over_the_last_five_years():
    dates = ["2011-01-01", "2011-01-03", "2011-01-05", "2011-01-07"]
    dates += ["2022-01-01", "2022-01-21", "2022-02-10", "2026-01-01"]
    tags = {f"v{i}": _tag(date) for i, date in enumerate(dates)}
    overall, recent, since = release_cadence(tags)
    assert since == 2022
    # gaps: 2, 2, 2, ~4000, 20, 20, ~1421
    assert overall == 20
    # between releases since 2022: 20, 20 and 1421 days (not the ~4000 before)
    assert recent == 20


def test_release_cadence_leaves_out_recent_years_that_are_the_whole_history():
    tags = {"a": _tag("2025-01-01"), "b": _tag("2025-01-11"), "c": _tag("2025-01-31")}
    assert release_cadence(tags) == (15, None, 2021)
    # one release date is no cadence
    assert release_cadence({"a": _tag("2025-01-01"), "b": _tag("2025-01-01")}) is None
    assert release_cadence({}) is None


def test_tags_page_leads_with_releases_per_year_and_folds_the_table(mock_data_collector, temp_dir):
    tags = {f"v1.{i}": _tag(f"{2015 + i // 2}-0{1 + i % 2 * 5}-15", i + 1) for i in range(12)}
    for i, name in enumerate(tags):
        tags[name]["order"] = 12 - i
    mock_data_collector.tags = tags
    _creator(mock_data_collector).create_tags_html(mock_data_collector, temp_dir)
    page = _read_page(temp_dir, "tags.html")

    assert '<section class="lead-section">' in page
    assert 'id="chart-tags-per-year"' in page
    assert "12 tags from 2015 to 2020. The most were in 2015, with 2; 2 in 2020." in page
    assert "<dt>Days between Releases</dt>" in page
    # Jan to Jun is 151 days (152 in a leap year), Jun to Jan 214: the median
    # of the 11 gaps, and of the 9 between the releases since 2016, is 152
    assert '<dt>Days between Releases</dt><dd class="stat-value">152</dd>' in page
    assert '<span class="nowrap">152 since 2016</span>' in page
    assert "<dt>Tags</dt>" in page
    assert "since 2015" in page

    latest = page[page.index('id="latest_tags"') : page.index('<details class="table-details"')]
    assert latest.count("<tr><td") == HTMLReportCreator.TAGS_SHOWN
    assert '<td class="nowrap">v1.11</td>' in latest
    assert '<td class="nowrap">v1.3</td>' not in latest
    assert 'id="tags"' not in latest
    folded = page[page.index('<details class="table-details"') :]
    assert (
        '<summary>All 12 tags</summary><div class="table-scroll">'
        '<table class="tags sortable" id="tags">'
    ) in folded
    assert folded.count("<tr><td") == 12
    # the oldest tag has no release before it
    assert (
        '<td class="nowrap">v1.0</td><td class="nowrap">2015-01-15</td><td class="num">&mdash;</td>'
    ) in folded


def test_tags_page_without_a_cadence_or_dates(mock_data_collector, temp_dir):
    mock_data_collector.tags = {"v1": {"date": "", "commits": 3, "authors": {"Alice Smith": 3}}}
    _creator(mock_data_collector).create_tags_html(mock_data_collector, temp_dir)
    page = _read_page(temp_dir, "tags.html")
    assert "since the start" in page
    assert "Days between Releases" not in page
    assert "chart-tags-per-year" not in page
    assert 'id="all_tags"' in page


def test_activity_page_leads_with_the_months(mock_data_collector, temp_dir):
    _creator(mock_data_collector).create_activity_html(mock_data_collector, temp_dir)
    page = _read_page(temp_dir, "activity.html")
    lead = page[page.index('<section class="lead-section">') : page.index("</section>")]
    assert 'id="chart-commits-by-year-month"' in lead
    busiest = max(
        mock_data_collector.commits_by_month, key=mock_data_collector.commits_by_month.get
    )
    count = mock_data_collector.commits_by_month[busiest]
    month = HTMLReportCreator.MONTH_NAMES[int(busiest[5:]) - 1]
    assert f"The busiest was {month} {busiest[:4]}, with {count} commits.</p>" in lead


def test_activity_page_without_commits_names_no_busiest_month(mock_data_collector, temp_dir):
    mock_data_collector.commits_by_month = {}
    _creator(mock_data_collector).create_activity_html(mock_data_collector, temp_dir)
    assert "The busiest was" not in _read_page(temp_dir, "activity.html")


def test_timezones_list_the_busiest_then_the_rest_with_all_folded(mock_data_collector, temp_dir):
    zones = {f"{'+' if h >= 0 else '-'}{abs(h):02d}00": 20 - abs(h) for h in range(-8, 4)}
    mock_data_collector.commits_by_timezone = zones
    _creator(mock_data_collector).create_activity_html(mock_data_collector, temp_dir)
    page = _read_page(temp_dir, "activity.html")
    section = page[page.index('id="commits_by_timezone"') :]
    shown = section[: section.index('<details class="table-details"')]
    # the eight busiest, from the busiest, then the other four as one row
    assert shown.index("UTC+00:00") < shown.index("UTC-01:00") < shown.index("UTC+01:00")
    assert "UTC-08:00" not in shown
    assert '<tr class="share-rest"><td class="nowrap">Remaining 4 offsets</td>' in shown
    assert 'class="share-bar share-bar-muted"' in shown
    folded = section[section.index('<details class="table-details"') : section.index("</details>")]
    assert "<summary>All 12 offsets, west to east</summary>" in folded
    assert folded.index("UTC-08:00") < folded.index("UTC+00:00") < folded.index("UTC+03:00")
    assert "Remaining" not in folded


def test_overview_charts_have_no_row_gap_side_by_side():
    """Side by side, the two chart sections share their rows through a subgrid:
    a row gap would open between each heading, sentence and chart."""
    css_path = os.path.join(os.path.dirname(__file__), "..", "gitstats", "gitstats.css")
    with open(css_path, encoding="utf-8") as f:
        css = f.read()
    rule = css[css.index(".overview-charts {") :]
    rule = rule[: rule.index("}")]
    assert "column-gap: var(--space-7);" in rule
    assert "\tgap:" not in rule
    assert "row-gap" not in rule


def test_timezones_put_offsets_no_clock_keeps_in_one_row_at_the_end(mock_data_collector, temp_dir):
    mock_data_collector.commits_by_timezone = {"+0800": 30, "+51800": 2, "+1900": 1, "-0500": 15}
    _creator(mock_data_collector).create_activity_html(mock_data_collector, temp_dir)
    page = _read_page(temp_dir, "activity.html")
    section = page[page.index('id="commits_by_timezone"') :]
    section = section[: section.index("</table>")]
    assert "UTC+51" not in section
    assert "UTC+19" not in section
    # west to east, then the invalid ones, counted in the shares
    assert section.index("UTC-05:00") < section.index("UTC+08:00") < section.index("2 invalid")
    # 3 of 48 commits
    assert (
        '<tr class="share-rest"><td class="nowrap" title="Recorded as +1900, +51800">'
        '2 invalid offsets</td><td class="num">3</td><td class="num">6.2%'
    ) in section


def test_timezones_fold_with_the_invalid_offsets_last(mock_data_collector, temp_dir):
    zones = {f"{'+' if h >= 0 else '-'}{abs(h):02d}00": 20 - abs(h) for h in range(-8, 4)}
    mock_data_collector.commits_by_timezone = {**zones, "+99999": 1}
    _creator(mock_data_collector).create_activity_html(mock_data_collector, temp_dir)
    page = _read_page(temp_dir, "activity.html")
    section = page[page.index('id="commits_by_timezone"') :]
    shown = section[: section.index('<details class="table-details"')]
    assert shown.index("Remaining 4 offsets") < shown.index("1 invalid offset<")
    folded = section[section.index('<details class="table-details"') : section.index("</details>")]
    assert "<summary>All 12 offsets, west to east</summary>" in folded
    assert folded.index("UTC+03:00") < folded.index("1 invalid offset<")


def test_authors_table_leads_with_the_rank(mock_data_collector, temp_dir):
    _creator(mock_data_collector).create_authors_html(mock_data_collector, temp_dir)
    page = _read_page(temp_dir, "authors.html")
    table = page[page.index('<table class="authors sortable" id="authors">') :]
    table = table[: table.index("</table>")]
    assert table.startswith(
        '<table class="authors sortable" id="authors">'
        '<tr><th class="num rank"><abbr title="Rank by commits">#</abbr></th><th>Author</th>'
    )
    assert "# by commits" not in table
    assert '<tr><td class="num rank">1</td><td>' in table


def test_table_scroll_clips_what_is_placed_absolutely_inside_it():
    """The bar column's header text for screen readers is placed absolutely:
    outside a positioned box, it widened the Files page on a phone."""
    css_path = os.path.join(os.path.dirname(__file__), "..", "gitstats", "gitstats.css")
    with open(css_path, encoding="utf-8") as f:
        css = f.read()
    rule = css[css.index(".table-scroll {") :]
    rule = rule[: rule.index("}")]
    assert "position: relative;" in rule
    assert "overflow-x: auto;" in rule
