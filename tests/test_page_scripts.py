"""The report's own scripts, run in Node: how tables sort, and how the
Hotspots plot splits the files. Skipped where Node is not installed."""

import json
import os
import shutil
import subprocess
import tempfile

import pytest

from gitstats.aggregate import GROUP_FILTER_SCRIPT
from gitstats.report_creator import HOTSPOTS_SCRIPT

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
