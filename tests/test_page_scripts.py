"""The report's own scripts, run in Node: how tables sort, and how the
Hotspots plot splits the files. Skipped where Node is not installed."""

import json
import os
import shutil
import subprocess
import tempfile

import pytest

from gitstats.aggregate import GROUP_FILTER_SCRIPT
from gitstats.report_creator import CHART_SCRIPT, HOTSPOTS_SCRIPT

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node is not installed")

SORTABLE = os.path.join(os.path.dirname(__file__), "..", "gitstats", "sortable.js")

# Just enough of a DOM for sortable.js: cells with text, an optional
# data-sort value and child nodes, and rows of them.
FAKE_DOM = r"""
function el(tag, text, attrs) {
  const node = {tagName: tag.toUpperCase(), className: "", childNodes: [], attrs: Object.assign({}, attrs || {}),
    getAttribute(name) { return name in this.attrs ? this.attrs[name] : null; },
    setAttribute(name, value) { this.attrs[name] = String(value); },
    get firstChild() { return this.childNodes[0] || null; },
    appendChild(child) { const at = this.childNodes.indexOf(child);
      if (at < 0 && child.parent) child.parent.childNodes.splice(child.parent.childNodes.indexOf(child), 1);
      child.parent = this; this.childNodes.push(child); return child; },
    get innerText() { return this.childNodes.map(c => c.nodeType === 3 ? c.nodeValue : c.innerText).join(""); }};
  if (text !== undefined) node.appendChild({nodeType: 3, nodeValue: text});
  node.nodeType = 1;
  return node;
}
const window = {addEventListener() {}};
const document = {getElementsByTagName() { return []; }, createElement: tag => el(tag)};
function row(...cells) { return {cells: cells.map(c => typeof c === "string" ? el("td", c) : c)}; }
"""


def _run(script: str):
    """Run ``script`` in Node, from a file (a long command line is not safe on
    every system); what it prints, as JSON."""
    assert NODE is not None
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "script.js")
        with open(path, "w", encoding="utf-8") as f:
            f.write(script)
        done = subprocess.run(
            [NODE, path], capture_output=True, text=True, encoding="utf-8", check=False
        )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _node(body: str):
    """Run sortable.js and then ``body`` in Node; what ``body`` prints, as JSON."""
    with open(SORTABLE, encoding="utf-8") as f:
        sortable = f.read()
    return _run(FAKE_DOM + sortable + "\n" + body)


def _sorted(values, cells=None):
    rows = json.dumps(values)
    return _node(
        f"""
        const rows = {rows}.map(v => row(v));
        const t = {{}};
        const sortfn = ts_columnSort(t, 0, rows);
        SORT_COLUMN_INDEX = 0;
        console.log(JSON.stringify([sortfn.name, rows.sort(sortfn).map(r => r.cells[0].innerText)]));
        """
    )


def test_a_number_with_its_share_sorts_by_the_number():
    # "127 (78.4% of 162)" was 12778.4162, above "107 (100.0% of 107)"
    name, order = _sorted(["107 (100.0% of 107)", "127 (78.4% of 162)", "69 (76.7% of 90)"])
    assert name == "ts_sort_numeric"
    assert order == ["69 (76.7% of 90)", "107 (100.0% of 107)", "127 (78.4% of 162)"]


@pytest.mark.parametrize(
    "text, number",
    [
        ("127 (78.4% of 162)", "127"),
        ("1,234", "1234"),
        ("12.5%", "12.5"),
        ("-3", "-3"),
        ("1.5E+3", "1.5E+3"),
        ("n/a", ""),
    ],
)
def test_clean_num(text, number):
    assert _node(f"console.log(JSON.stringify(clean_num({json.dumps(text)})))") == number


def test_text_sorts_numbers_in_it_by_value():
    # tags: v0.10.0 after v0.9.1, not before v0.2.0
    name, order = _sorted(["v0.10.0", "v0.2.0", "V0.9.1", "2.0"])
    assert name == "ts_sort_caseinsensitive"
    assert order == ["2.0", "v0.2.0", "V0.9.1", "v0.10.0"]


def test_a_cell_sorts_by_its_data_sort_value():
    # an age shown as "1.9 yr" sorts by its days
    order = _node(
        """
        const cells = [["7.3 yr", "2671"], ["5 mo", "150"], ["1.9 yr", "694"]]
          .map(([text, days]) => row(el("td", text, {"data-sort": days})));
        const sortfn = ts_columnSort({}, 0, cells);
        SORT_COLUMN_INDEX = 0;
        console.log(JSON.stringify([sortfn.name, cells.sort(sortfn).map(r => r.cells[0].innerText)]));
        """
    )
    assert order == ["ts_sort_numeric", ["5 mo", "1.9 yr", "7.3 yr"]]


def test_versions_sort_as_text():
    # "1.0.1" is not a number; and a column whose header says so sorts as
    # text even when every name looks like one, as "0.9" and "0.10"
    name, order = _sorted(["1.0.1", "1.0", "0.9"])
    assert name == "ts_sort_caseinsensitive"
    assert order == ["0.9", "1.0", "1.0.1"]
    order = _node(
        """
        const header = el("th", "Name", {"data-sort-as": "text"});
        const rows = ["0.10", "0.9", "0.1"].map(v => row(v));
        const sortfn = ts_columnSort({rows: [{cells: [header]}]}, 0, rows);
        SORT_COLUMN_INDEX = 0;
        console.log(JSON.stringify([sortfn.name, rows.sort(sortfn).map(r => r.cells[0].innerText)]));
        """
    )
    assert order == ["ts_sort_caseinsensitive", ["0.1", "0.9", "0.10"]]


def test_a_header_keeps_its_own_content():
    # rebuilt from innerText, it was what CSS showed: "COMMITS (%)"
    header = _node(
        """
        const abbr = el("abbr", "Commits", {title: "commits by these authors"});
        const th = el("th"); th.appendChild(abbr); th.appendChild({nodeType: 3, nodeValue: " (%)"});
        const skip = el("th", "Bar"); skip.className = "unsortable";
        const t = {rows: [{cells: [th, skip]}], tHead: null, getElementsByTagName: () => []};
        ts_makeSortable(t);
        const link = th.childNodes[0];
        console.log(JSON.stringify({
          link: [link.tagName, link.className, link.getAttribute("onclick")],
          inside: link.childNodes.map(c => c.tagName || c.nodeValue),
          arrow: link.childNodes[2].getAttribute("data-sort"),
          kept: link.childNodes[0] === abbr,
          skipped: skip.childNodes.length}));
        """
    )
    assert header == {
        "link": ["A", "sortheader", "ts_resortTable(this, 0);return false;"],
        "inside": ["ABBR", " (%)", "SPAN"],
        "arrow": "none",
        "kept": True,
        "skipped": 1,
    }


def _hotspot_series(points, median_lines, median_churn, least=None):
    """The Hotspots plot's datasets for ``points`` [lines, churn]: their
    labels and how many files each has, and whether the medians are drawn.
    ``least`` is the smallest size and change count of all the files, the
    plotted ones' unless given."""
    script = HOTSPOTS_SCRIPT.split("<script>", 1)[1].rsplit("</script>", 1)[0]
    least_lines, least_churn = least or (min(p[0] for p in points), min(p[1] for p in points))
    data = {
        "medianLines": median_lines,
        "medianChurn": median_churn,
        "leastLines": least_lines,
        "leastChurn": least_churn,
        "points": [
            [f"f{n}", lines, churn, lines * churn] for n, (lines, churn) in enumerate(points)
        ],
    }
    stubs = f"""
    const document = {{getElementById: () => ({{textContent: {json.dumps(json.dumps(data))},
                                                   getContext: () => ({{}})}})}};
    function getCSSVar() {{ return "#000000"; }}
    function applyChartTheme() {{}}
    let made = null;
    function Chart(ctx, config) {{ made = config; }}
    """
    body = """
    const lines = made.plugins[0];
    let drawn = false;
    const chart = {ctx: {save() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {}, restore() {},
                         setLineDash() {}}, chartArea: {top: 0, bottom: 1, left: 0, right: 1},
                   scales: {x: {getPixelForValue: () => 0}, y: {getPixelForValue: () => 0}}};
    chart.ctx.stroke = () => { drawn = true; };
    lines.beforeDatasetsDraw(chart);
    console.log(JSON.stringify({series: made.data.datasets.map(d => [d.label, d.data.length]), medians: drawn}));
    """
    return _run(stubs + script + body)


def test_hotspots_split_at_the_medians():
    # a file at the median is in the upper half, as the tiles say
    points = [(10, 1), (50, 2), (100, 5), (400, 9)]
    assert _hotspot_series(points, 100, 5) == {
        "series": [
            ["Large, changed often", 2],
            ["Small, rarely changed", 2],
        ],
        "medians": True,
    }


def test_hotspots_at_the_smallest_value_are_not_in_the_upper_half():
    # most files changed once: the median is 1, and "at least 1" is every file
    points = [(10, 1), (20, 1), (30, 1), (40, 1), (50, 3)]
    assert _hotspot_series(points, 30, 1)["series"] == [
        ["Large, changed often", 1],
        ["Large, rarely changed", 2],
        ["Small, rarely changed", 2],
    ]


def test_hotspots_take_the_smallest_values_of_all_the_files():
    # only the top files are plotted: one changed 3 times is the least plotted,
    # but files changed once were left out, so 3 at the median is the upper half
    points = [(100, 3), (200, 3), (300, 5), (400, 9), (150, 4)]
    assert _hotspot_series(points, 200, 3, least=(10, 1))["series"] == [
        ["Large, changed often", 3],
        ["Small, changed often", 2],
    ]


def test_a_few_hotspots_are_not_split():
    # one file is not "large, changed often"
    assert _hotspot_series([(1, 1)], 1, 1) == {"series": [["Files", 1]], "medians": False}
    assert _hotspot_series([(5, 1), (9, 3), (12, 2)], 9, 2)["series"] == [["Files", 3]]


def _chart_script(chart_js: str, body: str):
    """Run the charts' shared script and then ``body`` in Node, on a page where
    Chart.js is ``chart_js`` (JavaScript for ``window.Chart``)."""
    script = CHART_SCRIPT.split("<script>", 1)[1].rsplit("</script>", 1)[0]
    stubs = f"""
    const document = {{addEventListener() {{}}}};
    let registered = [];
    const Chart = {chart_js};
    const window = {{Chart: Chart}};
    """
    return _run(stubs + script + body)


def test_a_chart_that_is_built_takes_its_note_away():
    # the note that the chart is not shown is in the chart's box, with the canvas
    removed = _chart_script(
        "{register: plugin => registered.push(plugin)}",
        """
        const note = {gone: false, remove() { this.gone = true; }};
        const asked = [];
        const box = {querySelector: selector => { asked.push(selector); return note; }};
        registered[0].beforeInit({canvas: {parentNode: box}});
        // a chart in a box without the note is built all the same
        registered[0].beforeInit({canvas: {parentNode: {querySelector: () => null}}});
        console.log(JSON.stringify({plugins: registered.length, asked: asked, gone: note.gone}));
        """,
    )
    assert removed == {"plugins": 1, "asked": [".chart-note"], "gone": True}


def test_the_chart_script_runs_without_chart_js():
    # chart.umd.min.js did not load: the helpers are still defined, and the
    # charts' own scripts fail one by one, leaving their notes
    defined = _chart_script("undefined", "console.log(JSON.stringify(typeof applyChartTheme));")
    assert defined == "function"


def _hotspot_plot(points, median_lines, median_churn, numbered, width):
    """What the Hotspots plot draws besides its dots, on a plot ``width``
    pixels wide: each dataset's label and color series, whether it has a
    legend, and the text written on it before and after the dots."""
    script = HOTSPOTS_SCRIPT.split("<script>", 1)[1].rsplit("</script>", 1)[0]
    data = {
        "medianLines": median_lines,
        "medianChurn": median_churn,
        "leastLines": min(p[0] for p in points),
        "leastChurn": min(p[1] for p in points),
        "points": [
            [f"f{n}", lines, churn, score] for n, (lines, churn, score) in enumerate(points)
        ],
        "numbered": numbered,
    }
    stubs = f"""
    const document = {{getElementById: () => ({{textContent: {json.dumps(json.dumps(data))},
                                                   getContext: () => ({{}})}})}};
    function getCSSVar(name) {{ return name; }}
    function applyChartTheme() {{}}
    let made = null;
    function Chart(ctx, config) {{ made = config; }}
    Chart.defaults = {{font: {{family: "mono"}}}};
    """
    body = f"""
    const names = made.plugins[1];
    const written = [], fills = [];
    // a character is 7px wide; values are their own pixels, the median in the middle
    const ctx = {{save() {{}}, restore() {{}}, fillRect() {{ fills.push(this.fillStyle); }},
                 measureText: text => ({{width: 7 * text.length}}),
                 fillText(text) {{ written.push([text, this.fillStyle]); }}}};
    const chart = {{ctx: ctx, chartArea: {{top: 0, bottom: 400, left: 0, right: {width}}},
                   scales: {{x: {{getPixelForValue: () => {width} / 2}},
                            y: {{getPixelForValue: () => 200}}}}}};
    names.beforeDatasetsDraw(chart);
    const before = written.splice(0);
    names.afterDatasetsDraw(chart);
    console.log(JSON.stringify({{
      series: made.data.datasets.map(d => [d.label, d.series]),
      legend: made.options.plugins.legend.display,
      tint: fills, before: before, numbers: written}}));
    """
    return _run(stubs + script + body)


def test_the_hotspots_plot_names_its_quadrants_and_numbers_its_top_files():
    # [lines, churn, score], highest score first, as the page gives them
    points = [(400, 9, 180.0), (100, 5, 50.0), (50, 2, 14.0), (10, 1, 3.0)]
    plot = _hotspot_plot(points, 100, 5, numbered=3, width=1000)
    # two colors, not four: the large files that change often, and the rest
    assert plot["series"] == [
        ["Large, changed often", "hot"],
        ["Small, rarely changed", "rest"],
    ]
    # the names are on the plot, each in its corner, in place of a legend
    assert plot["legend"] is False
    assert plot["tint"] == ["--series-hot0d"]
    assert plot["before"] == [
        ["LARGE, CHANGED OFTEN \u00b7 2 FILES", "--series-hot"],
        ["SMALL, CHANGED OFTEN", "--chart-text"],
        ["SMALL, RARELY CHANGED", "--chart-text"],
        ["LARGE, RARELY CHANGED", "--chart-text"],
        ["median 100 lines", "--chart-text"],
        ["median 5 changes", "--chart-text"],
    ]
    # the highest scores carry their rank, in their dot's color
    assert plot["numbers"] == [
        ["1", "--series-hot"],
        ["2", "--series-hot"],
        ["3", "--chart-text"],
    ]


def test_a_narrow_hotspots_plot_leaves_out_the_names_that_do_not_fit():
    points = [(400, 9, 180.0), (100, 5, 50.0), (50, 2, 14.0), (10, 1, 3.0)]
    # 150px a quadrant: room for no name ("SMALL, CHANGED OFTEN" is 140px and its
    # margins) and for the changes' median; the numbers are on the dots all the same
    plot = _hotspot_plot(points, 100, 5, numbered=2, width=300)
    assert plot["before"] == [["median 5 changes", "--chart-text"]]
    assert [number for number, _ in plot["numbers"]] == ["1", "2"]


def test_a_few_hotspots_are_numbered_without_quadrants():
    plot = _hotspot_plot([(9, 3, 9.0), (5, 1, 2.2)], 9, 3, numbered=2, width=1000)
    assert plot["series"] == [["Files", 1]]
    assert plot["before"] == []
    assert plot["tint"] == []
    assert plot["numbers"] == [["1", "--chart-text"], ["2", "--chart-text"]]


def _groups_after(hash_at_load: str, then: str) -> list:
    """Which rows the group filter shows when the page opens at
    ``hash_at_load`` and the address then changes to ``then``."""
    script = GROUP_FILTER_SCRIPT.split("<script>", 1)[1].rsplit("</script>", 1)[0]
    stubs = f"""
    const rows = ["py", "py", "web"].map(group => ({{hidden: false, getAttribute: () => group}}));
    const buttons = ["", "py", "web"].map(group => ({{
      attrs: {{}}, getAttribute: name => name === "data-group" ? group : null,
      setAttribute(name, value) {{ this.attrs[name] = value; }}, addEventListener() {{}}}}));
    const document = {{querySelectorAll: s => s.startsWith(".group-filter") ? buttons : rows}};
    const location = {{hash: {json.dumps(hash_at_load)}, pathname: "/", search: ""}};
    const history = {{replaceState() {{}}}};
    let changed = null;
    const window = {{addEventListener: (name, fn) => {{ changed = fn; }}}};
    """
    body = f"""
    location.hash = {json.dumps(then)};
    changed({{type: "hashchange"}});
    console.log(JSON.stringify(rows.map(r => r.hidden ? "" : r.getAttribute("data-group")).filter(Boolean)));
    """
    return _run(stubs + script + body)


def test_the_skip_link_keeps_the_group():
    # Skip to content sets #main: the rows of the group chosen stay as they are
    assert _groups_after("#group=py", "#main") == ["py", "py"]
    # a link to another group, or to none, still changes it
    assert _groups_after("#group=py", "#group=web") == ["web"]
    assert _groups_after("#group=py", "") == ["py", "py", "web"]
    # a page opened at #main shows every group
    assert _groups_after("#main", "#main") == ["py", "py", "web"]
