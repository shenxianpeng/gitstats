# Copyright (c) 2007-2014 Heikki Hokkanen <hoxu@users.sf.net> & others contributors
# GPLv2 / GPLv3
# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
"""The charts of a page: the script that draws them in the browser
(CHART_SCRIPT, on Chart.js), and what renders one into a page.
"""

import datetime
import html
import json
import re
from typing import Any

from gitstats.periods import collapse_gap_categories, collapse_gap_time

# Chart helpers shared by every chart on a report page (see _render_chartjs).
CHART_SCRIPT = """<script>
	// Chart.js reads colors once when a chart is built, so re-read the CSS
	// variables whenever the theme switches. Datasets flagged `themed` follow --bar-color.
	function applyChartTheme(chart) {
		const text = getCSSVar('--chart-text');
		const grid = getCSSVar('--chart-grid');
		Chart.defaults.color = text;
		Chart.defaults.borderColor = grid;
		// axis ticks, legends and tooltips in the report's monospace, like its other numbers
		Chart.defaults.font.family = getCSSVar('--font-mono');
		Chart.defaults.font.size = 11;
		if (!chart) return;
		// Built charts keep the defaults they resolved, so set colors on each one.
		Object.values(chart.options.scales).forEach(function(scale) {
			scale.ticks.color = text;
			scale.title.color = text;
			// month axes draw gridlines only at their labelled years (see monthAxisGrid)
			scale.grid.color = scale.ticks.callback === monthAxisTick ? monthAxisGrid : grid;
			scale.border.color = grid;
		});
		chart.options.plugins.legend.labels.color = text;
		const bar = getCSSVar('--bar-color');
		chart.data.datasets.forEach(function(ds) {
			if (ds.themed) { ds.backgroundColor = bar; ds.borderColor = bar; }
			if (ds.colorVar) { ds.backgroundColor = ds.borderColor = getCSSVar(ds.colorVar); }
			if (ds.series) {
				const color = getCSSVar('--series-' + ds.series);
				ds.borderColor = color;
				ds.backgroundColor = color + '33';
			}
		});
	}

	document.addEventListener('themechange', function() {
		applyChartTheme();
		Object.values(Chart.instances).forEach(function(chart) {
			applyChartTheme(chart);
			chart.update('none');
		});
	});

	// Marks drawn onto a chart (see _render_chartjs(annotations=...)):
	//   bands  shaded x-ranges with a caption, e.g. a stretch of years without commits
	//   peaks  a label above chosen bars
	//   values a value label above every non-zero bar
	// A band flagged `collapsed` stands for a stretch cut out of the axis: it is
	// hatched, its caption runs up the band, and `axis` names it under the plot.
	// Colors are read from CSS at draw time, so they follow the theme.
	function bandEdges(chart, band) {
		const x = chart.scales.x;
		const half = x.type === 'category' && chart.data.labels.length > 1
			? (x.getPixelForValue(1) - x.getPixelForValue(0)) / 2 : 0;
		return [x.getPixelForValue(band.from) - half, x.getPixelForValue(band.to) + half];
	}

	const chartAnnotations = {
		id: 'gsAnnotations',
		beforeDatasetsDraw: function(chart, args, opts) {
			const area = chart.chartArea, ctx = chart.ctx;
			const height = area.bottom - area.top;
			(opts.bands || []).forEach(function(band) {
				const edges = bandEdges(chart, band), left = edges[0], right = edges[1];
				ctx.save();
				ctx.fillStyle = getCSSVar('--surface-color');
				ctx.fillRect(left, area.top, right - left, height);
				if (band.collapsed) {
					// hatched: not drawn to scale
					ctx.save();
					ctx.beginPath();
					ctx.rect(left, area.top, right - left, height);
					ctx.clip();
					ctx.strokeStyle = getCSSVar('--border-color');
					ctx.beginPath();
					for (let d = left - height; d < right; d += 8) {
						ctx.moveTo(d, area.bottom); ctx.lineTo(d + height, area.top);
					}
					ctx.stroke();
					ctx.restore();
				}
				ctx.strokeStyle = getCSSVar('--border-strong');
				ctx.setLineDash([3, 3]);
				ctx.beginPath();
				ctx.moveTo(left, area.top); ctx.lineTo(left, area.bottom);
				ctx.moveTo(right, area.top); ctx.lineTo(right, area.bottom);
				ctx.stroke();
				ctx.font = '11px ' + getCSSVar('--font-mono');
				ctx.textAlign = 'center';
				// the caption runs along the band's longer side
				const room = band.collapsed ? height : right - left;
				let text = band.text;
				if (ctx.measureText(text).width > room - 8) text = band.short || '';
				const width = ctx.measureText(text).width;
				const taken = band.collapsed && barMarks(chart, opts).some(function(mark) {
					return mark.onBand && mark.x + mark.half > left && mark.x - mark.half < right;
				});
				if (text && !taken && width <= room - 4 && (!band.collapsed || right - left >= 14)) {
					ctx.translate((left + right) / 2, area.top + height / 2);
					if (band.collapsed) {
						ctx.rotate(-Math.PI / 2);
						// clear the hatching behind the caption
						ctx.fillStyle = getCSSVar('--surface-color');
						ctx.fillRect(-width / 2 - 4, -7, width + 8, 14);
						ctx.textBaseline = 'middle';
					}
					ctx.fillStyle = getCSSVar('--chart-text');
					ctx.fillText(text, 0, 0);
				}
				ctx.restore();
			});
		},
		// The years a collapsed band stands for, on the row of the tick labels,
		// unless it would run into one of them (a narrow chart on a phone).
		afterDraw: function(chart, args, opts) {
			const x = chart.scales.x, ctx = chart.ctx;
			(opts.bands || []).forEach(function(band) {
				if (!band.collapsed || !band.axis) return;
				const edges = bandEdges(chart, band), center = (edges[0] + edges[1]) / 2;
				ctx.save();
				ctx.font = '11px ' + getCSSVar('--font-mono');
				const half = ctx.measureText(band.axis).width / 2;
				const clash = x.ticks.some(function(tick, i) {
					const label = Array.isArray(tick.label) ? tick.label.join(' ') : tick.label;
					if (!label) return false;
					const reach = half + ctx.measureText(String(label)).width / 2 + 6;
					return Math.abs(x.getPixelForTick(i) - center) < reach;
				});
				if (!clash) {
					const grid = x.options.grid;
					ctx.fillStyle = getCSSVar('--chart-text');
					ctx.textAlign = 'center';
					ctx.textBaseline = 'top';
					ctx.fillText(band.axis, center,
						x.top + (grid.drawTicks ? grid.tickLength : 0) + x.options.ticks.padding);
				}
				ctx.restore();
			});
		},
		afterDatasetsDraw: function(chart, args, opts) {
			const ctx = chart.ctx;
			barMarks(chart, opts).forEach(function(mark) {
				ctx.save();
				ctx.font = mark.font;
				ctx.textAlign = 'center';
				if (mark.onBand) {
					// no room beside the band: clear its hatching behind the label
					ctx.fillStyle = getCSSVar('--surface-color');
					ctx.fillRect(mark.x - mark.half - 2, mark.y - 10, 2 * mark.half + 4, 13);
				}
				ctx.fillStyle = getCSSVar(mark.plain ? '--chart-text' : '--text-color');
				ctx.fillText(mark.text, mark.x, mark.y);
				ctx.restore();
			});
		}
	};

	// Where the labels above bars go: {text, plain, font, x, y, half, onBand}.
	// A label stays inside the plot area and, when there is room, beside a
	// collapsed band rather than on it; `onBand` marks the ones left on one.
	function barMarks(chart, opts) {
		const meta = chart.getDatasetMeta(0), ctx = chart.ctx, area = chart.chartArea;
		const marks = (opts.peaks || []).slice();
		if (opts.values) {
			chart.data.datasets[0].data.forEach(function(v, i) {
				if (v) marks.push({ index: i, text: String(v), plain: true });
			});
		}
		const bands = (opts.bands || []).filter(function(band) { return band.collapsed; })
			.map(function(band) { return bandEdges(chart, band); });
		const placed = [];
		marks.forEach(function(mark) {
			const bar = meta.data[mark.index];
			if (!bar) return;
			const font = (mark.plain ? '' : '600 ') + '11px ' + getCSSVar('--font-mono');
			ctx.save();
			ctx.font = font;
			const half = ctx.measureText(mark.text).width / 2;
			ctx.restore();
			const inside = function(x) { return Math.min(Math.max(x, area.left + half), area.right - half); };
			let x = inside(bar.x);
			bands.forEach(function(edges) {
				if (bar.x >= edges[1]) x = inside(Math.max(x, edges[1] + half + 4));
				else if (bar.x <= edges[0]) x = inside(Math.min(x, edges[0] - half - 4));
			});
			const onBand = bands.some(function(edges) {
				return x + half > edges[0] && x - half < edges[1];
			});
			placed.push({ text: mark.text, plain: mark.plain, font: font, x: x, y: bar.y - 6,
				half: half, onBand: onBand });
		});
		return placed;
	}

	// The slots standing in for a collapsed stretch are named after all of it
	// ("2016 \u2013 2023"), for tooltips; under the plot the annotation names it.
	function isCollapsedLabel(label) {
		return String(label).indexOf(' \u2013 ') !== -1;
	}

	function categoryTick(value) {
		const label = this.getLabelForValue(value);
		return isCollapsedLabel(label) ? '' : label;
	}

	// Ticks for a category axis of "YYYY-MM" months: the year at each January,
	// thinned so labels never collide; short spans label every few months.
	function monthAxisTick(value) {
		const label = this.getLabelForValue(value);
		if (isCollapsedLabel(label)) return '';
		const n = this.chart.data.labels.length;
		const width = Math.max(this.width, 1);
		if (n <= 24) {
			return value % Math.max(1, Math.ceil(n * 64 / width)) === 0 ? label : '';
		}
		if (String(label).slice(5) !== '01') return '';
		const year = Number(String(label).slice(0, 4));
		const step = Math.max(1, Math.ceil((n / 12) * 40 / width));
		return year % step === 0 ? String(year) : '';
	}

	function monthAxisGrid(ctx) {
		return ctx.tick && ctx.tick.label ? getCSSVar('--chart-grid') : 'transparent';
	}

	function formatChartDate(ms, unit) {
		const d = new Date(ms);
		const pad = function(n) { return (n < 10 ? '0' : '') + n; };
		if (unit === 'year') return String(d.getFullYear());
		if (unit === 'month') return d.getFullYear() + '-' + pad(d.getMonth() + 1);
		return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
	}

	// A long stretch without commits is cut out of a time axis and drawn as a
	// short break: `gap` is {from, to, width} in milliseconds, and the stretch
	// from..to takes `width` on the axis. squeezeTime() gives a timestamp its
	// place on the cut axis, stretchTime() gives a place its timestamp back.
	// Without a gap both leave the value alone.
	function squeezeTime(gap, ms) {
		if (!gap || ms <= gap.from) return ms;
		if (ms >= gap.to) return ms - (gap.to - gap.from) + gap.width;
		return gap.from + (ms - gap.from) / (gap.to - gap.from) * gap.width;
	}

	function stretchTime(gap, at) {
		if (!gap || at <= gap.from) return at;
		if (at >= gap.from + gap.width) return at + (gap.to - gap.from) - gap.width;
		return gap.from + (at - gap.from) / gap.width * (gap.to - gap.from);
	}

	// A linear x-axis over millisecond timestamps, ticked on year (or month)
	// boundaries, so gaps in history take up the space they really span;
	// only a gap handed in as `gap` is cut short (see squeezeTime).
	function timeAxis(xs, gap) {
		var min = xs.length ? squeezeTime(gap, xs[0]) : undefined;
		var max = xs.length ? squeezeTime(gap, xs[xs.length - 1]) : undefined;
		// one point in time (a single commit) has no width: give it a month
		// around it, or the point has no place on the axis and is not drawn
		if (xs.length && min === max) {
			min -= 15 * 864e5;
			max += 15 * 864e5;
		}
		return {
			type: 'linear',
			min: min,
			max: max,
			afterBuildTicks: function(scale) {
				const first = stretchTime(gap, scale.min), last = stretchTime(gap, scale.max);
				const from = new Date(first), to = new Date(last);
				const ticks = [];
				// no tick inside the stretch that was cut out
				const add = function(ms) {
					if (!gap || ms < gap.from || ms >= gap.to) ticks.push({ value: squeezeTime(gap, ms) });
				};
				let unit = 'year';
				if (to.getFullYear() - from.getFullYear() >= 2) {
					for (let y = from.getFullYear() + 1; y <= to.getFullYear(); y++) {
						add(new Date(y, 0, 1).getTime());
					}
				} else {
					unit = 'month';
					const d = new Date(from.getFullYear(), from.getMonth() + 1, 1);
					for (; d.getTime() <= last; d.setMonth(d.getMonth() + 1)) {
						add(d.getTime());
					}
				}
				scale.dateUnit = ticks.length >= 2 ? unit : 'day';
				if (ticks.length >= 2) scale.ticks = ticks;
			},
			ticks: {
				maxRotation: 0,
				autoSkipPadding: 12,
				callback: function(value) {
					return formatChartDate(stretchTime(gap, value), this.dateUnit);
				}
			}
		};
	}
</script>"""


# What each chart of a report shows, for screen readers: a canvas has no text.
# The chart adds the span its labels cover ("…, 2019 to 2026").
CHART_DESCRIPTIONS = {
    "chart-overview-yearly": "Bar chart of commits per year",
    "chart-weekly-activity": "Bar chart of commits per week",
    "chart-month-of-year": "Bar chart of commits by month of the year",
    "chart-commits-by-year-month": "Bar chart of commits per month",
    "chart-commits-by-year": "Bar chart of commits per year",
    "chart-ai-assisted": "Bar chart of AI-assisted commits per month",
    "chart-contributor-growth": "Line chart of the number of contributors over time",
    "chart-loc-by-author": "Line chart of lines of code added by the top authors over time",
    "chart-files-by-date": "Line chart of the number of files over time",
    "chart-lines-of-code": "Line chart of lines of code over time",
    "chart-lines-by-month": "Bar chart of lines added and removed per month",
}


def chart_label(chart_id: str, chart_type: str, labels: list[Any], time_axis: bool = False) -> str:
    """What a chart shows, for its canvas's aria-label: its description and
    the span of its labels, "Bar chart of commits per year, 2019 to 2026"."""
    text = CHART_DESCRIPTIONS.get(chart_id, f"{chart_type.capitalize()} chart")
    if time_axis:
        labels = [
            datetime.datetime.fromtimestamp(int(stamp)).strftime("%Y-%m-%d") for stamp in labels
        ]
    if not labels:
        return text
    first, last = str(labels[0]), str(labels[-1])
    return f"{text}, {first}" if first == last else f"{text}, {first} to {last}"


class ChartRenderer:
    """Renders a chart into a page: see CHART_SCRIPT for what draws it."""

    # Multi-series colors are the CSS variables --series-1 .. --series-6, so
    # they switch with the theme (see applyChartTheme)
    SERIES_COLORS = 6
    # Series outside the highlighted top N: a neutral grey readable on both themes
    OTHER_SERIES_COLOR = "rgba(128, 128, 128, 0.45)"
    # The widest a bar is drawn, in pixels, unless a chart sets its own
    MAX_BAR_THICKNESS = 64

    def _render_chartjs(
        self,
        chart_id: str,
        chart_type: str,
        labels: list[Any],
        datasets: list[dict[str, Any]],
        x_ticks_rotate: bool = False,
        aspect_ratio: float = 3,
        max_bar_thickness: int | None = None,
        time_axis: bool = False,
        highlight: int | None = None,
        annotations: dict[str, Any] | None = None,
        tooltip_share: bool = False,
        month_axis: bool = False,
        diverging: bool = False,
    ) -> str:
        """Render a Chart.js chart as inline HTML.

        With ``time_axis=True``, ``labels`` are Unix timestamps (seconds) and the
        x-axis is linear in time, so quiet periods keep their real width instead
        of collapsing between two adjacent points. Line series are drawn as steps
        because each point holds its value until the next one.

        A shaded band (``annotations["bands"]``) that covers a quarter of the
        x-axis or more is cut out of it and drawn as a short hatched break, so
        the years with commits get the room: see collapsed_width(). This
        applies to category and time axes alike.

        With ``highlight=N`` (multi-series charts), only the first N series get
        colors and legend entries; the rest are thin grey lines drawn behind
        them, so colors never repeat.

        ``annotations`` (category bar charts) is a dict for the gsAnnotations
        plugin: ``bands`` ``[{"from": i, "to": j, "text", "short"}]`` shade
        category ranges, ``peaks`` ``[{"index": i, "text"}]`` label bars, and
        ``values: True`` labels every non-zero bar. See gap_annotations().

        With ``tooltip_share=True`` (single series), the tooltip also gives the
        value's share of the series total: "67 commits (12.1%)".

        With ``month_axis=True``, ``labels`` are "YYYY-MM" months and the x-axis
        labels only the years (at each January), horizontally.

        A dataset may carry ``notes``, one string per point, shown as an extra
        tooltip line (e.g. "+2 new"); empty strings add nothing. A dataset with
        ``colorVar`` (e.g. "--success-color") takes its color from that CSS
        variable, following the theme.

        With ``diverging=True`` (bars), datasets stack around zero: positive
        values above it, negative ones below, and the y-axis and tooltips show
        magnitudes, e.g. lines added up and lines removed down.
        """
        is_multi = len(datasets) > 1
        if chart_type == "bar" and not max_bar_thickness:
            # a few bars keep a bar's width: one would fill the chart as a slab
            max_bar_thickness = self.MAX_BAR_THICKNESS

        js_datasets = []
        for i, ds in enumerate(datasets):
            series = i % self.SERIES_COLORS + 1
            entry = dict(ds)
            # a line is drawn between points: one or two of them would leave
            # an empty chart, or a bare line, without their dots
            known = [value for value in entry.get("data") or [] if value is not None]
            radius = 3 if len(known) <= 2 else 0
            if "colorVar" in entry:
                entry["backgroundColor"] = entry["borderColor"] = f"__CSSVAR:{entry['colorVar']}__"
            if is_multi and highlight is not None and i >= highlight:
                entry.setdefault("borderColor", self.OTHER_SERIES_COLOR)
                entry.setdefault("backgroundColor", self.OTHER_SERIES_COLOR)
                entry.setdefault("fill", False)
                entry.setdefault("pointRadius", radius)
                entry.setdefault("borderWidth", 1)
                entry.setdefault("order", 1)  # higher order is drawn first, i.e. behind
            elif is_multi:
                entry.setdefault("borderColor", f"__CSS_SERIES_{series}__")
                entry.setdefault("backgroundColor", f"__CSS_SERIES_{series}_FILL__")
                if "colorVar" not in entry:
                    entry["series"] = series
                entry.setdefault("fill", False)
                entry.setdefault("tension", 0.1)
                entry.setdefault("pointRadius", radius)
                entry.setdefault("pointHoverRadius", 3)
                entry.setdefault("borderWidth", 1.5)
                if highlight is not None:
                    entry.setdefault("order", 0)
            else:
                # single dataset: use CSS var for theme-aware color
                entry["backgroundColor"] = "__CSS_BAR_COLOR__"
                entry["borderColor"] = "__CSS_BAR_COLOR__"
                entry["themed"] = True
                if chart_type == "line":
                    entry.setdefault("borderWidth", 1.5)
                    entry.setdefault("pointRadius", radius)
                    entry.setdefault("pointHoverRadius", 3)
            if time_axis and chart_type == "line":
                entry.setdefault("stepped", True)
            js_datasets.append(entry)

        gap_json = "null"
        shown_labels = list(labels)
        if time_axis:
            labels = [int(stamp) * 1000 for stamp in labels]
            if annotations:
                annotations, gap = collapse_gap_time(labels, annotations)
                gap_json = json.dumps(gap)
        elif annotations:
            labels, js_datasets, annotations = collapse_gap_categories(
                labels, js_datasets, annotations
            )
        collapsed = annotations is not None and any(
            band.get("collapsed") for band in annotations.get("bands", [])
        )
        labels_json = json.dumps(labels).replace("</", "<\\/")
        datasets_json = json.dumps(js_datasets).replace("</", "<\\/")
        # Replace quoted placeholders with JS expressions
        datasets_json = datasets_json.replace('"__CSS_BAR_COLOR__"', "getCSSVar('--bar-color')")
        datasets_json = re.sub(r'"__CSSVAR:(--[a-z0-9-]+)__"', r"getCSSVar('\1')", datasets_json)
        for n in range(1, self.SERIES_COLORS + 1):
            datasets_json = datasets_json.replace(
                f'"__CSS_SERIES_{n}__"', f"getCSSVar('--series-{n}')"
            ).replace(f'"__CSS_SERIES_{n}_FILL__"', f"getCSSVar('--series-{n}') + '33'")

        legend_display = "true" if is_multi else "false"
        legend_labels = []
        if is_multi and chart_type == "line":
            # a short line in the series color, clearer than a faint filled box
            legend_labels.append("usePointStyle: true, pointStyle: 'line'")
        if is_multi and highlight is not None:
            # Legend lists only the highlighted series
            legend_labels.append(
                "filter: function(item) { return item.datasetIndex < %d; }" % highlight
            )
        if legend_labels:
            legend_display += ", labels: { " + ", ".join(legend_labels) + " }"
        if time_axis:
            # pair each value with its timestamp: {x, y} points on a linear axis
            data_js = f"""datasets: (function(xs, sets) {{
        sets.forEach(function(ds) {{
          ds.data = ds.data.map(function(y, i) {{
            return {{ x: squeezeTime(gap, xs[i]), y: y }};
          }});
        }});
        return sets;
      }})(labels, {datasets_json})"""
            x_scale_js = "timeAxis(labels, gap)"
            tooltip_callbacks = [
                """title: function(items) {
          return items.length ? formatChartDate(stretchTime(gap, items[0].parsed.x)) : '';
        }"""
            ]
        else:
            data_js = f"""labels: labels,
      datasets: {datasets_json}"""
            if month_axis:
                x_scale_js = (
                    "{ ticks: { autoSkip: false, maxRotation: 0, callback: monthAxisTick }, "
                    "grid: { color: monthAxisGrid } }"
                )
            else:
                # unrotated labels keep a gap between them, as on the time axes
                x_ticks = (
                    "maxRotation: 45, minRotation: 45"
                    if x_ticks_rotate
                    else "maxRotation: 0, autoSkipPadding: 12"
                )
                if collapsed:
                    x_ticks += ", callback: categoryTick"
                # each bar is its own category: a gridline per bar is only noise
                x_grid = ", grid: { display: false }" if chart_type == "bar" else ""
                x_scale_js = f"{{ ticks: {{ {x_ticks} }}{x_grid} }}"
            if chart_type == "line" and len(labels) == 1:
                # a line's only point goes in the middle, not on the left edge
                x_scale_js = x_scale_js.replace("{ ", "{ offset: true, ", 1)
            tooltip_callbacks = []
            if tooltip_share:
                tooltip_callbacks.append(
                    """label: function(item) {
          const total = item.dataset.data.reduce(function(a, b) { return a + b; }, 0) || 1;
          return item.parsed.y + (item.parsed.y === 1 ? ' commit (' : ' commits (') + (100 * item.parsed.y / total).toFixed(1) + '%)';
        }"""
                )
        if any("notes" in ds for ds in datasets):
            tooltip_callbacks.append(
                """afterLabel: function(item) {
          return (item.dataset.notes || [])[item.dataIndex] || '';
        }"""
            )
        if diverging:
            tooltip_callbacks.append(
                """label: function(item) {
          return item.dataset.label + ': ' + Math.abs(item.parsed.y).toLocaleString();
        }"""
            )
        tooltip_js = ""
        if tooltip_callbacks:
            tooltip_js = (
                ",\n        tooltip: { callbacks: { " + ", ".join(tooltip_callbacks) + " } }"
            )

        # Lines have no point markers, so tooltips follow the nearest point
        # instead of needing the pointer exactly on one
        interaction_js = (
            "\n      interaction: { mode: 'nearest', intersect: false },"
            if chart_type == "line"
            else ""
        )

        if annotations:
            annotations_json = json.dumps(annotations).replace("</", "<\\/")
            plugins_js = f",\n        gsAnnotations: {annotations_json}"
            register_js = "\n    plugins: [chartAnnotations],"
            # headroom so labels above the tallest bar stay inside the chart
            labels_above = annotations.get("peaks") or annotations.get("values")
            grace_js = ", grace: '10%'" if labels_above else ""
        else:
            plugins_js = register_js = grace_js = ""

        y_scale_js = f"{{ beginAtZero: true{grace_js}, ticks: {{ precision: 0 }} }}"
        if annotations and annotations.get("values"):
            # every bar is labelled with its value, so the y-axis would only repeat them
            y_scale_js = f"{{ display: false, beginAtZero: true{grace_js} }}"
        if diverging:
            x_scale_js = x_scale_js.replace("{ ", "{ stacked: true, ", 1)
            y_scale_js = (
                f"{{ stacked: true, beginAtZero: true{grace_js}, ticks: {{ precision: 0, "
                "callback: function(v) { return Math.abs(v).toLocaleString(); } } }"
            )

        # The chart fills a .chart-box that keeps aspect_ratio on wide screens
        # but has a minimum height, so phones don't get a flattened plot.
        box_class = "chart-box has-legend" if is_multi else "chart-box"
        aria = html.escape(chart_label(chart_id, chart_type, shown_labels, time_axis), quote=True)
        return f"""<div class="{box_class}" style="--chart-ratio: {aspect_ratio}"><canvas id="{chart_id}" role="img" aria-label="{aria}"></canvas></div>
<script>
(function() {{
  var ctx = document.getElementById('{chart_id}').getContext('2d');
  var labels = {labels_json};
  var gap = {gap_json};
  applyChartTheme();
  new Chart(ctx, {{
    type: '{chart_type}',{register_js}
    data: {{
      {data_js}
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,{interaction_js}
      plugins: {{
        legend: {{ display: {legend_display} }}{tooltip_js}{plugins_js}
      }},
      scales: {{
        x: {x_scale_js},
        y: {y_scale_js}
      }}{f", datasets: {{ bar: {{ maxBarThickness: {max_bar_thickness} }} }}" if max_bar_thickness else ""}
    }}
  }});
}})();
</script>
"""
