# Copyright (c) 2007-2014 Heikki Hokkanen <hoxu@users.sf.net> & others contributors
# GPLv2 / GPLv3
# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
"""The Hotspots page: every file by its size against how often it changes."""

import html
import json
from typing import Any

from gitstats.markup import BAR_HEADER, FILE_TABLE, html_header, plural, stat_tiles_html
from gitstats.ownership import compute_hotspots, head_files, head_ownership
from gitstats.pages.base import PageWriter
from gitstats.utils import format_int

# Draws the scatter plot on the Hotspots page: one dot per file, placed by its
# size and change count, sized by its score. Page data comes from #hotspot-data.
HOTSPOTS_SCRIPT = r"""<script>
(function() {
	const data = JSON.parse(document.getElementById('hotspot-data').textContent);
	const points = data.points.map(function(p) {
		return { path: p[0], x: p[1], y: p[2], score: p[3] };
	});
	const scores = points.map(function(p) { return p.score; });
	const low = Math.min.apply(null, scores);
	const range = (Math.max.apply(null, scores) - low) || 1;

	// One dataset per quadrant around the medians: each gets a legend entry and
	// a --series-N color that applyChartTheme() keeps in step with the theme.
	// A file at the median is in the upper half, as the tiles say, unless the
	// median is also the smallest value: then "at least the median" is every
	// file, and only those above it are large or changed often.
	// (the smallest values are over all the files, plotted or not, as the medians)
	const above = function(value, median, least) {
		return median > least ? value >= median : value > median;
	};
	const large = function(p) { return above(p.x, data.medianLines, data.leastLines); };
	const busy = function(p) { return above(p.y, data.medianChurn, data.leastChurn); };
	// With a few files, halves say nothing: they are one series, without medians
	const split = points.length >= 4;
	const quadrants = split ? [
		['Large, changed often', 3, function(p) { return large(p) && busy(p); }],
		['Small, changed often', 5, function(p) { return !large(p) && busy(p); }],
		['Large, rarely changed', 2, function(p) { return large(p) && !busy(p); }],
		['Small, rarely changed', 1, function(p) { return !large(p) && !busy(p); }]
	] : [['Files', 1, function() { return true; }]];
	const datasets = quadrants.map(function(q) {
		const own = points.filter(q[2]);
		const color = getCSSVar('--series-' + q[1]);
		// a bigger dot is a higher score
		const radius = own.map(function(p) { return 3 + 9 * (p.score - low) / range; });
		return {
			label: q[0],
			series: q[1],
			data: own,
			borderColor: color,
			backgroundColor: color + '33',
			borderWidth: 1.5,
			pointRadius: radius,
			pointHoverRadius: radius.map(function(r) { return r + 2; }),
			pointHitRadius: 6,
			clip: 16  // dots on the axes (one line, one change) are drawn whole
		};
	}).filter(function(ds) { return ds.data.length; });

	// Dashed lines at the median size and the median change count
	const medianLines = {
		id: 'gsMedianLines',
		beforeDatasetsDraw: function(chart) {
			if (!split) return;
			const ctx = chart.ctx, area = chart.chartArea;
			const x = chart.scales.x.getPixelForValue(data.medianLines);
			const y = chart.scales.y.getPixelForValue(data.medianChurn);
			ctx.save();
			ctx.strokeStyle = getCSSVar('--border-strong');
			ctx.setLineDash([3, 3]);
			ctx.beginPath();
			ctx.moveTo(x, area.top); ctx.lineTo(x, area.bottom);
			ctx.moveTo(area.left, y); ctx.lineTo(area.right, y);
			ctx.stroke();
			ctx.restore();
		}
	};

	// A logarithmic axis ticked at 1, 2, 5, 10, 20, 50, ... with room past the
	// largest value, so the highest-scoring dots are not drawn on the frame
	function logAxis(title) {
		return {
			type: 'logarithmic',
			min: 1,
			title: { display: true, text: title },
			afterDataLimits: function(scale) { scale.max *= 1.3; },
			afterBuildTicks: function(scale) {
				scale.ticks = scale.ticks.filter(function(tick) {
					const lead = tick.value / Math.pow(10, Math.floor(Math.log10(tick.value) + 1e-9));
					return [1, 2, 5].some(function(n) { return Math.abs(lead - n) < 1e-6; });
				});
			},
			ticks: {
				maxRotation: 0,
				callback: function(value) { return value.toLocaleString(); }
			}
		};
	}

	applyChartTheme();
	new Chart(document.getElementById('chart-hotspots').getContext('2d'), {
		type: 'scatter',
		plugins: [medianLines],
		data: { datasets: datasets },
		options: {
			responsive: true,
			maintainAspectRatio: false,
			plugins: {
				legend: { display: true, labels: { usePointStyle: true, pointStyle: 'circle' } },
				tooltip: {
					callbacks: {
						// the path on its own line: a deep one is as wide as the rest together
						label: function(item) {
							const p = item.raw;
							return [p.path, p.x.toLocaleString() + (p.x === 1 ? ' line' : ' lines')
								+ ', changed ' + p.y.toLocaleString() + (p.y === 1 ? ' time' : ' times')
								+ ', score ' + p.score.toLocaleString()];
						}
					}
				}
			},
			scales: {
				x: logAxis('File size (lines)'),
				y: logAxis('Changes (commits)')
			}
		}
	});
})();
</script>"""


class HotspotsPage(PageWriter):
    """Writes hotspots.html."""

    # The scatter plot shows at most this many files (the highest-scoring),
    # so the page stays light on repositories with tens of thousands of files
    HOTSPOTS_MAX_POINTS = 2000

    def create_hotspots_html(self, data: Any, path: str) -> None:
        """Create the Hotspots page: change frequency against file size.

        A file that is both large and changed often is where defects tend to
        cluster and where refactoring pays off first. Every file in the
        current tree is plotted by its size and its number of changes, and
        the highest-scoring files are listed below the plot. The medians only
        color the plot: half of the files are above each one in any
        repository, so being above both says nothing about a file by itself.
        """
        page = "hotspots.html"
        f = self._open_report_file(path, page)
        self.print_header(f, page)
        self.print_nav(f, page)
        f.write("<h1>Hotspots</h1>")

        hotspot_files = getattr(data, "hotspot_files", {})
        if not isinstance(hotspot_files, dict):
            hotspot_files = {}
        hotspots = compute_hotspots(hotspot_files)
        files = hotspots["files"]

        if not files:
            f.write(
                '<p class="section-note">No hotspot data available. A file is analyzed '
                "when its lines are counted and at least one commit changed it.</p>"
            )
            self.print_footer(f)
            f.write("</body></html>")
            f.close()
            return

        median_lines = hotspots["median_lines"]
        median_churn = hotspots["median_churn"]
        current = head_files(data)
        # How many people have changed each file, as the Code Ownership page counts
        # them; empty when the data has no ownership, and then the column is left out
        authors_of = {fs["path"]: fs["contributors"] for fs in head_ownership(data)["files"]}
        # The ten highest-scoring files are the ones the table below shows
        top_files = files[:10]

        f.write(
            '<p class="section-note">'
            "Files that are both large and changed often are where bugs tend to "
            "cluster and where refactoring pays off first. Each file in the current "
            "tree is placed by its size and by the number of commits that changed it; "
            "its <strong>hotspot score</strong> is changes &times; &radic;lines. "
            "Files without counted lines, such as binary files, are left out.</p>"
        )
        tiles = [
            (
                "Files Analyzed",
                format_int(len(files)),
                f"of {format_int(len(current))} in the current tree"
                if current is not None
                else "with lines and at least one change",
            ),
            (
                "Median File Size",
                plural(median_lines, "line"),
                "half of the files are at least this large",
            ),
            (
                "Median Changes",
                plural(median_churn, "commit"),
                "half of the files changed at least this often",
            ),
        ]
        # How much of the risk sits in the ten files listed below; with ten
        # files or fewer that is all of it, which says nothing
        total_score = sum(fs["score"] for fs in files)
        if len(files) > len(top_files) and total_score:
            share = sum(fs["score"] for fs in top_files) / total_score
            tiles.insert(
                1,
                (
                    f"Top {len(top_files)} Files",
                    f"{100.0 * share:.1f}%",
                    "of the total hotspot score",
                ),
            )
        f.write(stat_tiles_html(tiles))

        # Hotspots :: the scatter plot
        f.write(html_header(2, "Change frequency by file size"))
        plotted = files[: self.HOTSPOTS_MAX_POINTS]
        shown = ""
        if len(plotted) < len(files):
            shown = (
                f" Showing the {format_int(len(plotted))} highest-scoring of "
                f"{format_int(len(files))} files."
            )
        # the plot splits the files at the medians from four files on (HOTSPOTS_SCRIPT)
        medians = (
            " The dashed lines mark the median file size and the median number of "
            "changes, so the large files that change often are in the top right."
            if len(plotted) >= 4
            else ""
        )
        f.write(
            '<p class="section-note">'
            f"Each dot is a file; a bigger dot is a higher score.{medians} "
            f"Both axes are logarithmic.{shown}</p>"
        )
        page_data = {
            "medianLines": median_lines,
            "medianChurn": median_churn,
            "leastLines": min(fs["lines"] for fs in files),
            "leastChurn": min(fs["churn"] for fs in files),
            "points": [[fs["path"], fs["lines"], fs["churn"], fs["score"]] for fs in plotted],
        }
        f.write(
            '<div class="chart-box has-legend" style="--chart-ratio: 2.4">'
            '<canvas id="chart-hotspots" role="img" aria-label="Scatter plot of '
            f"{plural(len(plotted), 'file')} by size in lines and number of changes, "
            'both on logarithmic scales"></canvas></div>'
        )
        # "<" is escaped whole: a path is repository content, and must not be
        # able to end or re-open the script element it is embedded in
        f.write(
            '<script type="application/json" id="hotspot-data">'
            + json.dumps(page_data).replace("<", "\\u003c")
            + "</script>"
        )
        f.write(HOTSPOTS_SCRIPT)

        # Hotspots :: the files as a table, highest score first
        f.write(html_header(2, "Top hotspots"))
        f.write(
            '<p class="section-note">'
            "The files ranked by hotspot score: the larger a file is and the more "
            "often it changes, the higher it ranks."
            + (
                " <strong>Authors</strong> is how many people have changed the file, bots "
                'aside, as on the <a href="ownership.html">Code Ownership</a> page: a '
                "hotspot only one person has changed is also a bus-factor risk.</p>"
                if authors_of
                else "</p>"
            )
        )
        max_score = files[0]["score"] or 1

        def path_cell(filepath: str) -> str:
            # the flag is drawn by CSS from data-tag, so the cell's text stays the path
            flag = (
                ' data-tag="sole owner" title="Only one person has changed this file"'
                if authors_of.get(filepath) == 1
                else ""
            )
            return f'<td class="path"{flag}>{html.escape(filepath)}</td>'

        def authors_cell(filepath: str) -> str:
            if not authors_of:
                return ""
            return (
                f'<td class="num" data-label="Authors">'
                f"{format_int(authors_of.get(filepath, 0))}</td>"
            )

        def hotspot_table(table_id: str, rows: list[dict[str, Any]]) -> str:
            return (
                f'<div class="table-scroll"><table class="sortable share-table {FILE_TABLE}" '
                f'id="{table_id}">'
                '<tr><th>File</th><th class="num">Lines</th><th class="num">Changes</th>'
                + ('<th class="num">Authors</th>' if authors_of else "")
                + f'<th class="num">Score</th>{BAR_HEADER}</tr>'
                + "".join(
                    f"<tr>{path_cell(fs['path'])}"
                    f'<td class="num" data-label="Lines">{format_int(fs["lines"])}</td>'
                    f'<td class="num" data-label="Changes">{format_int(fs["churn"])}</td>'
                    f"{authors_cell(fs['path'])}"
                    f'<td class="num" data-label="Score">{fs["score"]:,.1f}</td>'
                    '<td class="share-cell"><span class="share-bar" aria-hidden="true">'
                    f'<span style="width: {100.0 * fs["score"] / max_score:.1f}%"></span>'
                    "</span></td></tr>"
                    for fs in rows
                )
                + "</table></div>"
            )

        # The ten highest-scoring are shown; the full list (up to 100) is folded away
        f.write(hotspot_table("hotspots", top_files))
        if len(files) > len(top_files):
            count = len(files)
            what = (
                f"all {plural(count, 'file')}"
                if count <= 100
                else f"the 100 highest-scoring of {format_int(count)} files"
            )
            f.write(
                f'<details class="table-details"><summary>Table: {what}</summary>'
                f"{hotspot_table('hotspots-all', files[:100])}</details>"
            )

        self.print_footer(f)
        f.write("</body></html>")
        f.close()
