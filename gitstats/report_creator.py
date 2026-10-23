# Copyright (c) 2007-2014 Heikki Hokkanen <hoxu@users.sf.net> & others contributors
# GPLv2 / GPLv3
# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
import datetime
import html
import json
import math
import os
import re
import shutil
import statistics
import time
from typing import Any

from gitstats import WEEKDAYS, get_i18n_text, load_config
from gitstats.badge import AI_ASSISTED_LABEL, STYLE_NAMES, ai_assisted_share, create_badges
from gitstats.employers import KIND_LABELS, KINDS, ORGANIZATION
from gitstats.employers import summarize as summarize_organizations
from gitstats.utils import (
    format_bytes,
    format_duration,
    format_int,
    get_git_version,
    get_version,
    tags_newest_first,
)

# A table with its chart beside it; the chart wraps below on narrow screens.

# Runs before the stylesheet loads so the page never flashes the wrong theme.
# An explicit choice from the toggle wins; otherwise follow the OS setting.
THEME_INIT_SCRIPT = (
    "<script>(function(){var t;try{t=localStorage.getItem('theme');}catch(e){}"
    "if(t!=='light'&&t!=='dark'){t=window.matchMedia&&"
    "window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}"
    "document.documentElement.setAttribute('data-theme',t);})();</script>"
)

THEME_SCRIPT = """<script>
	function getCSSVar(v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }

	function setTheme(theme) {
		document.documentElement.setAttribute('data-theme', theme);
		updateThemeIcon(theme);
		document.dispatchEvent(new Event('themechange'));
	}

	function toggleTheme() {
		const newTheme = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
		try { localStorage.setItem('theme', newTheme); } catch (e) {}
		setTheme(newTheme);
	}

	function updateThemeIcon(theme) {
		const button = document.getElementById('theme-toggle');
		if (button) {
			button.setAttribute('aria-label', theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode');
		}
	}

	// Follow OS theme changes until the user picks one with the toggle.
	(function() {
		const query = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)');
		if (!query || !query.addEventListener) return;
		query.addEventListener('change', function(e) {
			let stored = null;
			try { stored = localStorage.getItem('theme'); } catch (err) {}
			if (stored !== 'light' && stored !== 'dark') setTheme(e.matches ? 'dark' : 'light');
		});
	})();

	// The nav scrolls sideways when it does not fit; start with the current page in view.
	function revealCurrentNavItem() {
		const current = document.querySelector('.nav a.active');
		if (!current) return;
		const list = current.closest('ul');
		const item = current.getBoundingClientRect(), box = list.getBoundingClientRect();
		list.scrollLeft += item.left - box.left - (box.width - item.width) / 2;
	}

	// Wide tables scroll sideways on phones, with the first column pinned; mark
	// the ones that actually overflow so only they draw the pinned column's divider.
	function watchScrollBoxes() {
		if (!window.ResizeObserver) return;
		const observer = new ResizeObserver(function(entries) {
			entries.forEach(function(entry) {
				const box = entry.target;
				box.classList.toggle('is-scrollable', box.scrollWidth > box.clientWidth + 1);
			});
		});
		document.querySelectorAll('.table-scroll, .timeline-scroll').forEach(function(box) {
			observer.observe(box);
		});
	}

	document.addEventListener('DOMContentLoaded', function() {
		updateThemeIcon(document.documentElement.getAttribute('data-theme'));
		revealCurrentNavItem();
		watchScrollBoxes();
	});
</script>"""

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
		return {
			type: 'linear',
			min: xs.length ? squeezeTime(gap, xs[0]) : undefined,
			max: xs.length ? squeezeTime(gap, xs[xs.length - 1]) : undefined,
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

_THEME_TOGGLE_ICONS = (
    '<svg class="icon-moon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="16" height="16" '
    'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
    'aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>'
    '<svg class="icon-sun" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="16" height="16" '
    'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
    'aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41'
    'M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>'
)

THEME_TOGGLE_BUTTON = (
    '<button id="theme-toggle" class="theme-toggle" onclick="toggleTheme()" '
    f'aria-label="Switch to dark mode">{_THEME_TOGGLE_ICONS}</button>'
)

# Class of a table whose rows are files. A path cannot share a phone's width
# with a few numbers, so under 560px each row is laid out as two lines: the
# path, then the other cells, each named by its ``data-label`` (the column's
# heading), and the header row becomes the sort controls. See gitstats.css.
FILE_TABLE = "file-table"

# Most-read first: the overview, then who and when, what is at risk (knowledge
# held by one person, then large files that keep changing), the code itself,
# the story, and the reference lists; the Badges tool comes last
NAV_PAGES = (
    ("index.html", "General"),
    ("activity.html", "Activity"),
    ("authors.html", "Authors"),
    ("ownership.html", "Code Ownership"),
    ("hotspots.html", "Hotspots"),
    ("files.html", "Files"),
    ("history.html", "History"),
    ("lines.html", "Lines"),
    ("tags.html", "Tags"),
    ("badges.html", "Badges"),
)


def nav_link(href: str, label: str, current: str | None = None) -> str:
    """Return a nav ``<li>``, marking it as the current page when ``href == current``."""
    if href == current:
        return f'<li><a href="{href}" class="active" aria-current="page">{label}</a></li>'
    return f'<li><a href="{href}">{label}</a></li>'


# The Badges page: its sections, and each badge's name and what it shows
BADGES_PAGE_SECTIONS = (
    (
        "At a glance",
        "Several numbers, or the pace of the last year, in one badge.",
        (
            ("summary", "Commits, authors and lines in one badge"),
            ("activity", "Commits per month over the last year"),
            ("health", "Active, quiet or dormant, by the age of the last commit"),
            (
                "ai-assisted",
                "Share of the last 12 months' commits that name an AI coding assistant",
            ),
        ),
    ),
    (
        "Metrics",
        "One number each.",
        (
            ("commits", "Total commits"),
            ("authors", "People who committed"),
            ("lines", "Lines of code"),
            ("files", "Files in the repository"),
            ("last-commit", "Month of the latest commit"),
            ("release", "Newest tag and the tag count"),
            ("active-days", "Days with at least one commit"),
        ),
    ),
)

# Where a snippet points until the report's address is known
BADGES_PLACEHOLDER_URL = "https://<your-report-url>/"

_COPY_ICONS = (
    '<svg class="icon-copy" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="14" '
    'height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="12" height="12"/>'
    '<path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/></svg>'
    '<svg class="icon-check" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="14" '
    'height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>'
)

# Keeps the snippets on the Badges page in step with the report URL, style and
# format controls, and copies them. Page data comes from #badge-data.
BADGES_SCRIPT = r"""<script>
(function() {
	const data = JSON.parse(document.getElementById('badge-data').textContent);
	const input = document.getElementById('badge-url');
	const status = document.getElementById('badge-url-status');
	const hints = document.querySelectorAll('[data-url-hint]');
	const live = document.getElementById('badge-live');
	const rows = document.querySelectorAll('.badge-row');
	const formats = { md: 'Markdown', rst: 'reStructuredText', html: 'HTML' };
	const key = 'gitstats-badge-url:' + location.pathname.replace(/[^/]*$/, '');
	let style = data.style;
	let format = 'md';

	// The report's own address: --site-url, else this page's directory when
	// served over http(s); a page opened from a file can't know it.
	const detected = /^https?:$/.test(location.protocol)
		? location.href.replace(/[?#].*$/, '').replace(/[^/]*$/, '')
		: '';
	const auto = data.siteUrl || detected;
	// A full http(s) address, with no second "://" from text pasted onto
	// the end of another address
	function looksValid(url) {
		return /^https?:\/\/[^\/\s?#]+(\/[^\s?#]*)?$/.test(url) && url.indexOf('://') === url.lastIndexOf('://');
	}

	let saved = null;
	try {
		saved = localStorage.getItem(key);
		if (saved !== null && !looksValid(saved)) {
			localStorage.removeItem(key);
			saved = null;
		}
	} catch (e) {}
	input.value = saved !== null ? saved : auto;

	function base() {
		const url = input.value.trim();
		return url ? url.replace(/\/*$/, '/') : data.placeholder;
	}

	// `width` is for the Wrapped card, which is 1080px wide: reStructuredText
	// and HTML can show it smaller, Markdown has no way to say so
	function snippet(image, link, alt, width) {
		if (format === 'rst') {
			return '.. image:: ' + image + '\n   :target: ' + link + '\n   :alt: ' + alt
				+ (width ? '\n   :width: ' + width : '');
		}
		if (format === 'html') {
			return '<a href="' + link + '"><img src="' + image + '" alt="' + alt + '"'
				+ (width ? ' width="' + width + '"' : '') + '></a>';
		}
		return '[![' + alt + '](' + image + ')](' + link + ')';
	}

	function showStatus() {
		const url = input.value.trim();
		let state = 'detected';
		if (!url) state = auto ? 'cleared' : 'missing';
		else if (!looksValid(url)) state = 'invalid';
		else if (url !== auto) state = 'entered';
		else if (data.siteUrl) state = 'site';
		status.textContent = { detected: 'detected', site: '--site-url', entered: 'entered', missing: 'not set', cleared: 'not set', invalid: 'invalid' }[state];
		const warn = state === 'missing' || state === 'cleared' || state === 'invalid';
		status.className = 'badge-url-status' + (warn ? ' is-missing' : state === 'site' ? '' : ' is-ok');
		hints.forEach(function(hint) { hint.hidden = hint.getAttribute('data-url-hint') !== state; });
	}

	function render() {
		const link = base();
		rows.forEach(function(row) {
			const name = row.getAttribute('data-badge');
			const kind = row.getAttribute('data-kind');
			let path = 'badges/' + style + '/' + name + '.svg';
			let alt = 'GitStats ' + name;
			if (kind === 'default') { path = 'badge.svg'; alt = 'GitStats'; }
			if (kind === 'card') { path = name; alt = row.getAttribute('data-alt'); }
			const image = kind === 'endpoint'
				? 'https://img.shields.io/endpoint?url=' + link + 'badges/' + name + '.json'
				: link + path;
			const img = row.querySelector('img');
			if (img && kind === 'style') img.src = path;
			row.querySelector('.badge-code').textContent = snippet(image, link, alt, kind === 'card' ? 480 : 0);
			row.querySelector('.badge-copy').setAttribute('aria-label', 'Copy ' + formats[format] + ' for ' + row.getAttribute('data-title'));
		});
		showStatus();
	}

	function pick(attr, value) {
		document.querySelectorAll('[' + attr + ']').forEach(function(button) {
			button.setAttribute('aria-pressed', String(button.getAttribute(attr) === value));
		});
	}

	document.querySelectorAll('[data-style]').forEach(function(button) {
		button.addEventListener('click', function() {
			style = button.getAttribute('data-style');
			pick('data-style', style);
			render();
		});
	});
	document.querySelectorAll('[data-format]').forEach(function(button) {
		button.addEventListener('click', function() {
			format = button.getAttribute('data-format');
			pick('data-format', format);
			render();
		});
	});

	input.addEventListener('input', render);

	// Once the reader is done typing (the field loses focus, or Enter), a
	// valid address is kept in this browser, so half-typed ones never are.
	// Emptying the field, or typing the detected address again, forgets it
	// and goes back to the detected address.
	input.addEventListener('change', function() {
		const url = input.value.trim();
		try {
			if (!url || url === auto || !looksValid(url)) localStorage.removeItem(key);
			else localStorage.setItem(key, url);
		} catch (e) {}
		if (!url && auto) input.value = auto;
		render();
	});

	// Pages opened from a file have no clipboard API, and a browser may refuse
	// it anyway: fall back to the older copy command
	function legacyCopy(text) {
		const area = document.createElement('textarea');
		area.value = text;
		area.setAttribute('readonly', '');
		area.style.position = 'fixed';
		area.style.opacity = '0';
		document.body.appendChild(area);
		area.select();
		let ok = false;
		try { ok = document.execCommand('copy'); } catch (e) {}
		document.body.removeChild(area);
		return ok;
	}

	function copyText(text) {
		if (navigator.clipboard && window.isSecureContext) {
			return navigator.clipboard.writeText(text).catch(function() {
				if (!legacyCopy(text)) throw new Error('copy failed');
			});
		}
		return legacyCopy(text) ? Promise.resolve() : Promise.reject(new Error('copy failed'));
	}

	rows.forEach(function(row) {
		const button = row.querySelector('.badge-copy');
		const label = button.querySelector('span');
		const code = row.querySelector('.badge-code');
		let timer;
		button.addEventListener('click', function() {
			copyText(code.textContent).then(function() {
				button.classList.add('is-copied');
				label.textContent = 'Copied';
				live.textContent = 'Copied ' + formats[format] + ' for ' + row.getAttribute('data-title');
				clearTimeout(timer);
				timer = setTimeout(function() {
					button.classList.remove('is-copied');
					label.textContent = 'Copy';
				}, 1600);
			}, function() {
				// No clipboard access: select the snippet for a manual copy
				const range = document.createRange();
				range.selectNodeContents(code);
				const selection = window.getSelection();
				selection.removeAllRanges();
				selection.addRange(range);
				live.textContent = 'Snippet selected, press Ctrl+C or Cmd+C to copy';
			});
		});
	});

	render();
})();
</script>"""


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
	const large = function(p) { return p.x >= data.medianLines; };
	const busy = function(p) { return p.y >= data.medianChurn; };
	const quadrants = [
		['Large, changed often', 3, function(p) { return large(p) && busy(p); }],
		['Small, changed often', 5, function(p) { return !large(p) && busy(p); }],
		['Large, rarely changed', 2, function(p) { return large(p) && !busy(p); }],
		['Small, rarely changed', 1, function(p) { return !large(p) && !busy(p); }]
	];
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


class ReportCreator:
    """Creates the actual report based on given data."""

    def __init__(self):
        self.data = None
        self.path = None

    def create(self, data, path):
        self.data = data
        self.path = path


class HTMLReportCreator(ReportCreator):
    # The report's public address, ending in "/", when it is known (--site-url)
    site_url = ""
    # The Repo Wrapped card written next to the report by --wrapped, as
    # {"year", "theme", "file"}; None when there is none to show
    wrapped_card: dict[str, Any] | None = None

    @staticmethod
    def _heat_level(value, max_value):
        if max_value <= 0 or value <= 0:
            return 0
        ratio = float(value) / float(max_value)
        if ratio <= 0.25:
            return 1
        if ratio <= 0.50:
            return 2
        if ratio <= 0.75:
            return 3
        return 4

    @classmethod
    def _heat_td_class(cls, value, max_value):
        return f"heat heat{cls._heat_level(value, max_value)}"

    def create(self, data: Any, path: str) -> None:
        ReportCreator.create(self, data, path)
        self.title = data.project_name

        # copy static files to the report directory
        basedir = os.path.dirname(os.path.abspath(__file__))
        for file in (
            load_config()["style"],
            "sortable.js",
            "chart.umd.min.js",
        ):
            src = basedir + "/" + file
            if os.path.exists(src):
                shutil.copyfile(src, path + "/" + file)

        # shareable badges served alongside the report (see gitstats/badge.py)
        create_badges(data, path)
        # what a link to the report shows where it is shared
        self.share_description = report_share_description(data)
        with open(os.path.join(path, "share-card.html"), "w", encoding="utf-8") as card:
            card.write(report_share_card_html(data))

        self.create_index_html(data, path)
        self.create_activity_html(data, path)
        self.create_authors_html(data, path)
        self.create_files_html(data, path)
        self.create_lines_html(data, path)
        self.create_tags_html(data, path)
        self.create_ownership_html(data, path)
        self.create_hotspots_html(data, path)
        self.create_history_html(data, path)
        self.create_badges_html(data, path)

        # Create AI Insights page if AI is enabled
        if hasattr(data, "ai_summaries") and data.ai_summaries:
            self.create_ai_insights_html(data, path)

    def create_index_html(self, data: Any, path: str) -> None:
        f = open(path + "/index.html", "w", encoding="utf-8")
        format = "%Y-%m-%d %H:%M:%S"
        self.print_header(f, "index.html")

        self.print_nav(f, "index.html")

        # The repository's name heads its overview; report metadata sits under it
        f.write(f"<h1>{html.escape(data.project_name)}</h1>")
        f.write(
            '<p class="page-meta">'
            f"{data.get_first_commit_date().strftime('%Y-%m-%d')} &rarr; "
            f"{data.get_last_commit_date().strftime('%Y-%m-%d')}"
            f" &middot; generated {datetime.datetime.now().strftime(format)}"
            f" in {time.time() - data.get_stamp_created():.0f} s"
            f" &middot; gitstats {get_version()}, {get_git_version()}"
            ' &middot; <a href="badges.html">Badge for your README</a>'
            "</p>"
        )
        if getattr(data, "shallow", False) is True:
            f.write(
                '<p class="section-note shallow-note"><strong>Shallow clone:</strong> this '
                "report only covers the commits that were fetched. Clone the full history "
                "(for example <code>git fetch --unshallow</code>) and generate it again.</p>"
            )

        total_commits = data.get_total_commits()
        active_days = len(data.get_active_days())
        delta_days = data.get_commit_delta_days()
        extensions = len(data.extensions)
        streak = data.get_longest_streak()
        f.write(
            stat_tiles_html(
                [
                    (
                        "Commits",
                        format_int(total_commits),
                        f"{total_commits / active_days:.1f} per active day"
                        f" &middot; {total_commits / delta_days:.1f} per day",
                    ),
                    (
                        "Authors",
                        format_int(data.get_total_authors()),
                        f"{total_commits / data.get_total_authors():.1f} commits per author",
                    ),
                    (
                        "Lines of Code",
                        format_int(data.get_total_loc()),
                        f'<span class="stat-added">+{format_int(data.total_lines_added)}</span> added'
                        f' &middot; <span class="stat-removed">−{format_int(data.total_lines_removed)}</span>'
                        " removed",
                    ),
                    (
                        "Files",
                        format_int(data.get_total_files()),
                        f"{extensions} extension{'' if extensions == 1 else 's'}",
                    ),
                    (
                        "Active Days",
                        format_int(active_days),
                        f"of {format_int(delta_days)} days &middot; {100.0 * active_days / delta_days:.1f}%",
                    ),
                    (
                        "Longest Streak",
                        f"{streak} day{'' if streak == 1 else 's'}",
                        "consecutive active days",
                    ),
                ]
            )
        )

        self._write_overview_yearly(f, data)

        sections = [self._overview_contributors_html(data)]
        if data.tags:
            sections.append(self._overview_releases_html(data))
        if len(sections) > 1:
            f.write('<div class="two-columns">' + "".join(sections) + "</div>")
        else:
            f.write(sections[0])

        self.print_footer(f)
        f.write("</body>\n</html>")
        f.close()

    def _write_overview_yearly(self, f: Any, data: Any) -> None:
        """Commits per year across the whole history, noting the longest quiet stretch."""
        f.write(html_header(2, "Commits per year"))
        if data.commits_by_year:
            years = list(range(min(data.commits_by_year), max(data.commits_by_year) + 1))
        else:
            years = []
        values = [data.commits_by_year.get(y, 0) for y in years]
        # Shade the longest run of two or more years without commits
        annotations = gap_annotations(years, values, min_gap=2)
        f.write(
            self._render_chartjs(
                "chart-overview-yearly",
                "bar",
                years,
                [{"label": "Commits", "data": values}],
                aspect_ratio=5,
                annotations=annotations,
            )
        )
        if annotations:
            # the chart's canvas is invisible to screen readers; say the same in text
            band = annotations["bands"][0]
            f.write(
                f'<p class="visually-hidden">No commits from {years[band["from"]]} '
                f"to {years[band['to']]}.</p>"
            )
        f.write('<p class="more-link"><a href="activity.html">Activity in detail &rarr;</a></p>')

    def _overview_contributors_html(self, data: Any) -> str:
        """Top five authors by commits, with their share as a bar."""
        authors = data.get_authors(5)
        top = max((data.get_author_info(a)["commits"] for a in authors), default=0) or 1
        rows = []
        for author in authors:
            info = data.get_author_info(author)
            width = 100.0 * info["commits"] / top
            rows.append(
                f"<tr><td>{author_html(author)}</td>"
                f'<td class="num">{format_int(info["commits"])}</td>'
                f'<td class="num">{info["commits_frac"]:.1f}%</td>'
                f'<td class="share-cell"><span class="share-bar" aria-hidden="true">'
                f'<span style="width: {width:.1f}%"></span></span></td></tr>'
            )
        total = data.get_total_authors()
        return (
            "<section>"
            + html_header(2, "Top contributors")
            + '<div class="table-scroll"><table class="share-table">'
            '<tr><th>Author</th><th class="num">Commits</th><th class="num">Share</th>'
            "<th></th></tr>" + "".join(rows) + "</table></div>"
            f'<p class="more-link"><a href="authors.html">All {format_int(total)} '
            f"author{'' if total == 1 else 's'} &rarr;</a></p>"
            "</section>"
        )

    def _overview_releases_html(self, data: Any) -> str:
        """The five most recent tags with their commit count and main authors."""
        latest = tags_newest_first(data.tags)[:5]
        rows = []
        for tag in latest:
            info = data.tags[tag]
            names = sorted(info["authors"], key=lambda a: (-info["authors"][a], a))
            shown = ", ".join(author_html(a) for a in names[:2])
            if len(names) > 2:
                shown += f" +{len(names) - 2}"
            rows.append(
                f'<tr><td class="nowrap">{html.escape(tag)}</td>'
                f'<td class="nowrap">{info["date"]}</td>'
                f'<td class="num">{format_int(info["commits"])}</td>'
                f"<td>{shown}</td></tr>"
            )
        total = len(data.tags)
        return (
            "<section>"
            + html_header(2, "Latest releases")
            + '<div class="table-scroll"><table class="share-table">'
            '<tr><th>Tag</th><th>Date</th><th class="num">Commits</th><th>Authors</th></tr>'
            + "".join(rows)
            + "</table></div>"
            f'<p class="more-link"><a href="tags.html">All {format_int(total)} '
            f"tag{'' if total == 1 else 's'} &rarr;</a></p>"
            "</section>"
        )

    def create_activity_html(self, data, path):
        ###
        # Activity
        f = open(path + "/activity.html", "w", encoding="utf-8")
        self.print_header(f, "activity.html")
        self.print_nav(f, "activity.html")
        f.write("<h1>Activity</h1>")

        self._write_activity_intro(f, data)

        # From the long view down to the daily rhythm
        self._write_commits_by_year_section(f, data)
        self._write_commits_by_year_month_section(f, data)
        self._write_weekly_activity_section(f, data)
        self._write_punch_card_section(f, data)
        # Month of year and timezones side by side (stacked on narrow screens)
        f.write('<div class="two-columns"><section>')
        self._write_month_of_year_section(f, data)
        f.write("</section><section>")
        self._write_commits_by_timezone_section(f, data)
        f.write("</section></div>")

        self.print_footer(f)
        f.write("</body></html>")
        f.close()

    # The Activity page's sections, in page order, for its "On this page" links
    ACTIVITY_SECTIONS = (
        ("Commits by year", "By year"),
        ("Commits by year/month", "By month"),
        ("Weekly activity", "Last weeks"),
        ("Punch card", "Punch card"),
        ("Month of year", "Month of year"),
        ("Commits by timezone", "Timezones"),
    )

    def _write_activity_intro(self, f, data) -> None:
        """The page's headline numbers as stat tiles, then links to its sections."""
        full_days = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
        streak = data.get_longest_streak()
        hours = data.get_activity_by_hour_of_day()
        days = data.get_activity_by_day_of_week()
        active = len(data.get_active_days())
        tiles = [
            (
                "Commits",
                format_int(data.get_total_commits()),
                f"on {format_int(active)} active day{'' if active == 1 else 's'}",
            ),
            (
                "Longest Streak",
                f"{streak} day{'' if streak == 1 else 's'}",
                "consecutive active days",
            ),
        ]
        if hours:
            hour = max(hours, key=lambda h: (hours[h], -h))
            tiles.append(("Busiest Hour", f"{hour:02d}:00", f"{format_int(hours[hour])} commits"))
        if days:
            day = max(days, key=lambda d: (days[d], -d))
            tiles.append(("Busiest Day", full_days[day], f"{format_int(days[day])} commits"))
        f.write(stat_tiles_html(tiles))
        links = "".join(
            f'<a href="#{html_linkify(title)}">{label}</a>'
            for title, label in self.ACTIVITY_SECTIONS
        )
        f.write(
            '<nav class="page-toc" aria-label="On this page">'
            f"<span>On this page</span>{links}</nav>"
        )

    def _write_weekly_activity_section(self, f, data) -> None:
        """Commits per week for the last 32 weeks.

        Weeks are labelled by the Monday they start on ("Feb 16"); the "%Y-%W"
        keys the data is stored under read like months ("2026-07").
        """
        weeks_count = 32
        f.write(html_header(2, "Weekly activity"))

        now = datetime.datetime.now()
        deltaweek = datetime.timedelta(7)
        weeks: list[str] = []
        mondays: list[datetime.date] = []
        stampcur = now
        for _ in range(weeks_count):
            weeks.insert(0, stampcur.strftime("%Y-%W"))
            mondays.insert(0, (stampcur - datetime.timedelta(days=stampcur.weekday())).date())
            stampcur -= deltaweek

        def day(d: datetime.date) -> str:
            return f"{d:%b} {d.day}"

        f.write(
            '<p class="section-note">'
            f"Last {weeks_count} weeks, from the week of {day(mondays[0])}, {mondays[0].year} "
            f"to the week of {day(mondays[-1])}, {mondays[-1].year}.</p>"
        )
        weekly_values = [data.activity_by_year_week.get(w, 0) for w in weeks]
        f.write(
            self._render_chartjs(
                "chart-weekly-activity",
                "bar",
                [day(m) for m in mondays],
                [{"label": "Commits", "data": weekly_values}],
                aspect_ratio=5,
            )
        )

    def _write_punch_card_section(self, f, data) -> None:
        """Commits by day of week x hour of day, with bars for every hour and day.

        A row of bars along the top gives the commits per hour of day, and a bar
        under each day's total gives the share per weekday. One grid replaces
        the former Hour of Day, Day of Week and Hour of Week sections; their
        anchors are kept so existing links still land here.
        """
        f.write('<span id="hour_of_day"></span><span id="day_of_week"></span>')
        f.write('<span id="hour_of_week"></span>')
        f.write(html_header(2, "Punch card"))
        f.write(
            '<p class="section-note">'
            "Commits by day of week and hour of day, in each commit's local time. "
            "The bars along the top are the commits per hour; the last column is "
            "the commits per day.</p>"
        )
        total = data.get_total_commits() or 1
        hour_totals = data.get_activity_by_hour_of_day()
        day_totals = data.get_activity_by_day_of_week()
        busiest_cell = data.activity_by_hour_of_week_busiest
        busiest_hour = max(hour_totals.values(), default=0) or 1
        busiest_day = max(day_totals.values(), default=0) or 1

        f.write('<div class="table-scroll"><table class="punch-card">')
        f.write(
            "<tr><th>Day</th>"
            + "".join(f"<th>{hour}</th>" for hour in range(24))
            + '<th class="num">Total</th></tr>'
        )
        # Commits per hour of day, as bars above the grid
        f.write('<tr class="punch-hour-bars"><th>Hour</th>')
        for hour in range(24):
            commits = hour_totals.get(hour, 0)
            height = round(40 * commits / busiest_hour) if commits else 0
            f.write(
                f'<td title="{hour:02d}:00 &middot; {format_int(commits)} commits &middot; '
                f'{100.0 * commits / total:.1f}%"><div class="punch-vbar">'
                f'<span class="punch-vbar-value">{format_int(commits) if commits else ""}</span>'
                f'<span class="punch-vbar-fill" style="height: {max(height, 1 if commits else 0)}px">'
                "</span></div></td>"
            )
        f.write("<td></td></tr>")
        for weekday in range(7):
            f.write(f"<tr><th>{WEEKDAYS[weekday]}</th>")
            for hour in range(24):
                commits = data.activity_by_hour_of_week.get(weekday, {}).get(hour, 0)
                f.write(
                    f'<td class="{self._heat_td_class(commits, busiest_cell)}">'
                    f"{format_int(commits) if commits else ''}</td>"
                )
            day = day_totals.get(weekday, 0)
            f.write(
                f'<td class="num punch-total">{format_int(day)} ({100.0 * day / total:.1f}%)'
                '<span class="share-bar share-bar-inline" aria-hidden="true">'
                f'<span style="width: {100.0 * day / busiest_day:.1f}%"></span></span></td></tr>'
            )
        f.write("</table></div>")
        f.write(
            '<p class="heat-legend">Fewer'
            + "".join(f'<span class="heat{level}"></span>' for level in range(5))
            + "More commits</p>"
        )

    MONTH_NAMES = (
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    )

    def _write_month_of_year_section(self, f, data) -> None:
        """Commits per calendar month, all years combined: counts on the bars, share on hover."""
        f.write(html_header(2, "Month of year"))
        values = [data.activity_by_month_of_year.get(mm, 0) for mm in range(1, 13)]
        f.write(
            self._render_chartjs(
                "chart-month-of-year",
                "bar",
                list(self.MONTH_NAMES),
                [{"label": "Commits", "data": values}],
                max_bar_thickness=40,
                aspect_ratio=2,
                annotations={"values": True},
                tooltip_share=True,
            )
        )

    def _write_commits_by_year_month_section(self, f, data) -> None:
        """Write commits by year/month: the chart, with the per-month table folded away."""
        f.write(html_header(2, "Commits by year/month"))
        cbym_keys = month_range(data.commits_by_month.keys())
        cbym_values = [data.commits_by_month.get(k, 0) for k in cbym_keys]
        f.write(
            self._render_chartjs(
                "chart-commits-by-year-month",
                "bar",
                cbym_keys,
                [{"label": "Commits", "data": cbym_values}],
                month_axis=True,
                # a year or more without commits gets shaded, with the peaks around it
                annotations=gap_annotations(cbym_keys, cbym_values, min_gap=12),
            )
        )
        months = sorted(data.commits_by_month.keys(), reverse=True)
        f.write(
            '<details class="table-details"><summary>Table: commits and lines per month '
            f"({len(months)} month{'' if len(months) == 1 else 's'} with commits)</summary>"
        )
        f.write(
            '<div class="table-scroll"><table><tr><th>Month</th><th class="num">Commits</th><th class="num">Lines added</th><th class="num">Lines removed</th></tr>'
        )
        for yymm in months:
            f.write(
                '<tr><td>%s</td><td class="num">%s</td><td class="num">%s</td><td class="num">%s</td></tr>'
                % (
                    yymm,
                    format_int(data.commits_by_month.get(yymm, 0)),
                    format_int(data.lines_added_by_month.get(yymm, 0)),
                    format_int(data.lines_removed_by_month.get(yymm, 0)),
                )
            )
        f.write("</table></div></details>")

    def _write_commits_by_year_section(self, f, data) -> None:
        """Commits by year: the chart, with the per-year table folded away below it
        (like the monthly section).

        It also carries the anchor of the former Yearly activity section, whose
        chart showed the same numbers.
        """
        f.write('<span id="yearly_activity"></span>')
        f.write(html_header(2, "Commits by year"))
        if data.commits_by_year:
            cby_all_years = list(
                range(min(data.commits_by_year.keys()), max(data.commits_by_year.keys()) + 1)
            )
        else:
            cby_all_years = []
        cby_values = [data.commits_by_year.get(y, 0) for y in cby_all_years]
        f.write(
            self._render_chartjs(
                "chart-commits-by-year",
                "bar",
                cby_all_years,
                [{"label": "Commits", "data": cby_values}],
                aspect_ratio=4,
                annotations=gap_annotations(cby_all_years, cby_values, min_gap=2),
            )
        )
        years = sorted(data.commits_by_year.keys(), reverse=True)
        f.write(
            '<details class="table-details"><summary>Table: commits and lines per year '
            f"({len(years)} year{'' if len(years) == 1 else 's'} with commits)</summary>"
        )
        f.write(
            '<div class="table-scroll"><table><tr><th>Year</th><th class="num">Commits (% of all)</th>'
            '<th class="num">Lines added</th><th class="num">Lines removed</th></tr>'
        )
        total = data.get_total_commits() or 1
        for yy in years:
            f.write(
                '<tr><td>%s</td><td class="num">%s (%.1f%%)</td><td class="num">%s</td><td class="num">%s</td></tr>'
                % (
                    yy,
                    format_int(data.commits_by_year.get(yy, 0)),
                    (100.0 * data.commits_by_year.get(yy, 0)) / total,
                    format_int(data.lines_added_by_year.get(yy, 0)),
                    format_int(data.lines_removed_by_year.get(yy, 0)),
                )
            )
        f.write("</table></div></details>")

    def _write_commits_by_timezone_section(self, f, data) -> None:
        """Commits per UTC offset, west to east, as horizontal bars."""
        f.write(html_header(2, "Commits by timezone"))
        total = sum(data.commits_by_timezone.values()) or 1
        busiest = max(data.commits_by_timezone.values(), default=0) or 1
        rows = []
        for offset in sorted(data.commits_by_timezone, key=lambda n: int(n)):
            commits = data.commits_by_timezone[offset]
            # "+0530" -> "UTC+05:30"
            label = f"UTC{offset[:3]}:{offset[3:]}" if len(offset) == 5 else html.escape(offset)
            rows.append(
                f'<tr><td class="nowrap">{label}</td>'
                f'<td class="num">{format_int(commits)}</td>'
                f'<td class="num">{100.0 * commits / total:.1f}%</td>'
                '<td class="share-cell"><span class="share-bar" aria-hidden="true">'
                f'<span style="width: {100.0 * commits / busiest:.1f}%"></span></span></td></tr>'
            )
        f.write(
            '<div class="table-scroll"><table class="share-table">'
            '<tr><th>UTC offset</th><th class="num">Commits</th><th class="num">Share</th>'
            "<th></th></tr>" + "".join(rows) + "</table></div>"
        )

    def _build_author_time_series(self, data):
        """Build per-author cumulative added-lines time series for Chart.js.

        For large repositories, data points are automatically downsampled to keep
        the HTML file size manageable and Chart.js rendering fast. Since the stored
        values are already cumulative, downsampling preserves the chart shape.
        """
        authors_to_plot = data.get_authors(load_config()["max_authors"])
        sorted_stamps = sorted(data.changes_by_date_by_author.keys())
        total_points = len(sorted_stamps)

        # Target max ~500 data points per chart to prevent browser lag and huge HTML.
        # 500 points covers ~10 years at weekly granularity — more than enough for
        # cumulative line charts.
        MAX_POINTS = 500
        if total_points > MAX_POINTS:
            step = total_points / MAX_POINTS
            sampled_indices = {int(i * step) for i in range(MAX_POINTS)}
            sampled_indices.add(total_points - 1)  # ensure the last point is always included
        else:
            sampled_indices = set(range(total_points))

        lines_by_authors = dict.fromkeys(authors_to_plot, 0)
        time_labels = []
        per_author_lines = {a: [] for a in authors_to_plot}

        for i, stamp in enumerate(sorted_stamps):
            # Update running totals: only the author(s) of this commit changed
            for author in data.changes_by_date_by_author[stamp]:
                if author in authors_to_plot:
                    lines_by_authors[author] = data.changes_by_date_by_author[stamp][author][
                        "lines_added"
                    ]

            # Only record a data point if this index is in the sampled set
            if i in sampled_indices:
                time_labels.append(stamp)
                for author in authors_to_plot:
                    per_author_lines[author].append(lines_by_authors[author])

        loc_datasets = [{"label": a, "data": per_author_lines[a]} for a in authors_to_plot]
        return time_labels, loc_datasets

    def _contributor_timeline_html(self, data: Any, authors: list[str], top_of: str = "") -> str:
        """One row per author on a shared, real time axis.

        A square marks each month with commits (bigger = more commits) and a thin
        line runs from the author's first to last active month, so who was
        active when, and for how long, reads at a glance. Plain HTML/CSS: it
        follows the theme without any script. ``top_of`` ("the top 20 of 40
        authors") goes in the note when not every author has a row.
        """
        months = month_range(data.author_of_month.keys())
        if not months or not authors:
            return ""
        index = {month: i for i, month in enumerate(months)}
        n = len(months)

        # The longest stretch without commits: months[a:b]. When it is long
        # enough to be collapsed on the charts it is here too, to `slots`
        # months wide, so the page's time axes agree.
        quiet = quiet_months(data)
        a = b = 0
        slots = None
        if quiet and quiet[0] in index and quiet[1] in index:
            a, b = index[quiet[0]], index[quiet[1]] + 1
            slots = collapsed_slots(n, b - a)
        width = n if slots is None else n - (b - a) + slots

        def place(i: float) -> float:
            """Where month index ``i`` falls on the axis, in months from its start."""
            if slots is None or i <= a:
                return i
            if i >= b:
                return i - (b - a) + slots
            return a + (i - a) / (b - a) * slots

        def left(i: float) -> str:
            return f"{100.0 * place(i) / width:.3f}%"

        def span(i: float, j: float) -> str:
            return f"{100.0 * (place(j) - place(i)) / width:.3f}%"

        per_author: dict[str, dict[str, int]] = {a: {} for a in authors}
        for month, counts in data.author_of_month.items():
            for author, commits in counts.items():
                if author in per_author:
                    per_author[author][month] = commits

        # Year boundaries as gridlines; label every year, or every 2nd/5th on long
        # histories. The years inside a collapsed stretch have no line of their own.
        first_year, last_year = int(months[0][:4]), int(months[-1][:4])
        years = [
            year
            for year in range(first_year + 1, last_year + 1)
            if slots is None or not a <= index[f"{year}-01"] < b
        ]
        every = 1 if len(years) < 12 else 2 if len(years) < 24 else 5
        grid = []
        for year in years:
            pos = left(index[f"{year}-01"])
            label = str(year) if year % every == 0 else ""
            grid.append(f'<span class="timeline-year" style="left: {pos}">{label}</span>')

        # The quiet stretch, shaded like the charts' gap bands; collapsed, it is
        # hatched and names its years where the year labels are
        if quiet and b > a:
            collapsed = slots is not None
            grid.insert(
                0,
                f'<span class="timeline-gap{" is-collapsed" if collapsed else ""}" '
                f'style="left: {left(a)}; width: {span(a, b)}" '
                f'title="No commits {quiet[0]} \u2013 {quiet[1]}">'
                + (f"<span>{year_span(quiet[0], quiet[1])}</span>" if collapsed else "")
                + "</span>",
            )

        rows = []
        for author in authors:
            active = sorted(per_author[author])
            name = html.escape(author)
            commits = data.get_author_info(author)["commits"]
            if active:
                start, end = index[active[0]], index[active[-1]]
                marks = [
                    f'<span class="timeline-span" style="left: {left(start + 0.5)}; '
                    f'width: {span(start, end)}"></span>'
                ]
                for month in active:
                    count = per_author[author][month]
                    size = min(18.0, 4 + 2.2 * math.sqrt(count))
                    marks.append(
                        f'<span class="timeline-mark" style="left: {left(index[month] + 0.5)}; '
                        f'--size: {size:.1f}px" title="{month}: {format_int(count)} '
                        f'commit{"" if count == 1 else "s"}"></span>'
                    )
                label = f"{name}: {format_int(commits)} commits, {active[0]} to {active[-1]}"
            else:
                marks = []
                label = f"{name}: {format_int(commits)} commits"
            bot = " bot" if is_bot(author) else ""
            rows.append(
                f'<div class="timeline-row{bot}" role="img" aria-label="{label}">'
                f'<span class="timeline-name">{author_html(author)}</span>'
                f'<span class="timeline-count">{format_int(commits)}</span>'
                f'<span class="timeline-track">{"".join(marks)}</span></div>'
            )

        # The axis row shows the year labels from the grid; a history within one
        # year has no year boundary, so label its first and last month instead
        ends = "" if grid else f"<span>{months[0]}</span><span>{months[-1]}</span>"
        return (
            '<p class="section-note">'
            + (f"One row for each of {top_of}" if top_of else "One row per author")
            + ": a square marks each month with commits (bigger means "
            "more), and the line runs from their first to their last active month. "
            "Bot accounts are grey.</p>"
            '<div class="timeline-scroll"><div class="timeline">'
            f'<div class="timeline-grid" aria-hidden="true">{"".join(grid)}</div>'
            + "".join(rows)
            + f'<div class="timeline-axis" aria-hidden="true">{ends}</div>'
            "</div></div>"
        )

    def _authors_summary_html(self, data: Any) -> str:
        """Stat tiles under the Authors heading: how many, how many are still active or
        new (in the 12 months up to the last commit), and how concentrated the work is."""
        everyone = data.get_authors()
        bots = sum(1 for a in everyone if is_bot(a))
        tiles = [
            (
                "Authors",
                format_int(len(everyone)),
                f"incl. {bots} bot account{'' if bots == 1 else 's'}"
                if bots
                else "no bot accounts",
            )
        ]
        last = data.get_last_commit_date()
        if isinstance(last, datetime.datetime):
            cutoff = (last - datetime.timedelta(days=365)).strftime("%Y-%m-%d")
            infos = [data.get_author_info(a) for a in everyone]
            active = sum(1 for i in infos if str(i.get("date_last", "")) >= cutoff)
            new = sum(1 for i in infos if str(i.get("date_first", "")) >= cutoff)
            tiles.append(("Active Authors", format_int(active), "committed in the last 12 months"))
            tiles.append(("New Authors", format_int(new), "first commit in the last 12 months"))
        top = everyone[:2]
        if top:
            share = sum(data.get_author_info(a)["commits_frac"] for a in top)
            label = "Top Author" if len(top) == 1 else "Top 2 Authors"
            tiles.append((label, f"{share:.1f}%", "of all commits"))
        assisted = ai_assisted_count(data)
        if assisted:
            tiles.append(
                (
                    "AI-assisted Commits",
                    share_text(assisted, data.get_total_commits()),
                    f"at least {format_int(assisted)} commit{'' if assisted == 1 else 's'}",
                )
            )
        else:
            tiles.append(("AI-assisted Commits", "0", "no commit names an assistant"))
        return stat_tiles_html(tiles)

    def _ai_assisted_html(self, data: Any) -> str:
        """The "AI-assisted commits" section of the Authors page: how many
        commits name an AI coding assistant, when, and which. Nothing when
        none does."""
        assisted = ai_assisted_count(data)
        if not assisted:
            return ""
        total = data.get_total_commits()
        by_month = data.ai_assisted_by_month
        authored = data.ai_assisted_authored
        parts = [html_header(2, "AI-assisted commits")]

        note = (
            f"{format_int(assisted)} of {format_int(total)} commits "
            f"({share_text(assisted, total)}) name{'s' if assisted == 1 else ''} an AI coding "
            "assistant: as their author, as a co-author, or in the line it signs with."
        )
        if authored:
            note += (
                f" {format_int(authored)} of them {'was' if authored == 1 else 'were'} made by "
                "an assistant under its own account."
            )
        # the twelve months that end with the last commit
        last = max([*data.commits_by_month, *by_month])
        year_ago = months_back(last, 11)
        if min(data.commits_by_month, default=last) < year_ago:
            recent = sum_since(by_month, year_ago)
            recent_total = sum_since(data.commits_by_month, year_ago)
            note += (
                f" In the last 12 months: {format_int(recent)} of {format_int(recent_total)} "
                f"({share_text(recent, recent_total)})."
            )
        parts.append(f'<p class="section-note">{note}</p>')
        parts.append(
            '<p class="section-note">These are lower bounds. An assistant that leaves no mark '
            "in the commit is not counted, and a mark does not say how much of the commit the "
            "assistant wrote.</p>"
        )

        # per month since the first one, and the last twelve months at least,
        # as far as the history goes back
        first = max(min(min(by_month), year_ago), min([*data.commits_by_month, *by_month]))
        months = month_range([first, last])
        counts = [by_month.get(month, 0) for month in months]
        notes = [
            f"{share_text(count, data.commits_by_month.get(month, 0))} of "
            f"{format_int(data.commits_by_month.get(month, 0))} that month"
            if count
            else ""
            for month, count in zip(months, counts)
        ]
        quiet = quiet_months(data)
        gap = {}
        if quiet and quiet[0] in months and quiet[1] in months:
            gap = {"bands": [quiet_band(*quiet, months.index(quiet[0]), months.index(quiet[1]))]}
        parts.append(
            self._render_chartjs(
                "chart-ai-assisted",
                "bar",
                months,
                [{"label": "AI-assisted commits", "data": counts, "notes": notes}],
                month_axis=True,
                aspect_ratio=4,
                annotations=gap,
            )
        )

        assistants = sorted(
            data.ai_assistants.items(), key=lambda item: (-item[1]["commits"], item[0])
        )
        most = assistants[0][1]["commits"]
        rows = []
        for name, info in assistants:
            first, last_day = (
                datetime.datetime.fromtimestamp(info[key]).strftime("%Y-%m-%d")
                for key in ("first_commit_stamp", "last_commit_stamp")
            )
            rows.append(
                f"<tr><td>{html.escape(name)}</td>"
                f'<td class="num">{format_int(info["commits"])}</td>'
                '<td class="share-cell"><span class="share-bar" aria-hidden="true">'
                f'<span style="width: {100.0 * info["commits"] / most:.1f}%"></span></span></td>'
                f'<td class="num">{format_int(info["authored"])}</td>'
                f'<td class="nowrap">{first}</td><td class="nowrap">{last_day}</td></tr>'
            )
        parts.append(
            '<div class="table-scroll"><table class="share-table">'
            '<tr><th>Assistant</th><th class="num">Commits</th><th></th>'
            '<th class="num">As author</th><th>First commit</th><th>Last commit</th></tr>'
            + "".join(rows)
            + "</table></div>"
        )
        if len(assistants) > 1 and sum(info["commits"] for _, info in assistants) > assisted:
            parts.append(
                '<p class="section-note">A commit that names two assistants is counted '
                "under both.</p>"
            )
        parts.append(AI_ASSISTED_COUNTED)
        return "".join(parts)

    def _organizations_html(self, data: Any) -> str:
        """The "Commits by organization" section of the Authors page: the
        organizations whose addresses the commits come from, and by quarter
        how many come from organizations, personal mail, hidden addresses
        and bots. Nothing when no commit comes from an organization."""
        overview = summarize_organizations(data, limit=load_config()["max_domains"])
        if not overview or not overview["by_kind"][ORGANIZATION]:
            return ""
        total = overview["commits"]
        from_orgs = overview["by_kind"][ORGANIZATION]
        count = overview["organization_count"]
        parts = [html_header(2, "Commits by organization")]
        parts.append(
            f'<p class="section-note">{format_int(from_orgs)} of {format_int(total)} commits '
            f"({share_text(from_orgs, total)}) come from an address at "
            f"{format_int(count)} organization{'' if count == 1 else 's'}, counted by the "
            "domain of the address and committed from by two addresses or more. Domains of "
            "one address (most often a person's own), personal mail providers, hidden "
            "noreply addresses and bots are counted apart, below.</p>"
        )
        parts.append(
            '<p class="section-note">The domain says where an address is, not who paid for '
            "the work: people commit from personal addresses on paid time, and from work "
            "addresses on their own.</p>"
        )
        rows = []
        most = overview["organizations"][0]["commits"]
        for row in overview["organizations"]:
            first, last_day = (
                datetime.datetime.fromtimestamp(row[key]).strftime("%Y-%m-%d")
                for key in ("first_commit_stamp", "last_commit_stamp")
            )
            rows.append(
                f"<tr><td>{html.escape(row['organization'])}</td>"
                f'<td class="num">{format_int(row["commits"])}</td>'
                f'<td class="num">{share_text(row["commits"], total)}</td>'
                '<td class="share-cell"><span class="share-bar" aria-hidden="true">'
                f'<span style="width: {100.0 * row["commits"] / most:.1f}%"></span></span></td>'
                f'<td class="num">{format_int(row["commits_last_12mo"])}</td>'
                f'<td class="num">{format_int(row["authors"])}</td>'
                f'<td class="nowrap">{first}</td><td class="nowrap">{last_day}</td></tr>'
            )
        parts.append(
            '<div class="table-scroll"><table class="share-table">'
            '<tr><th>Organization</th><th class="num">Commits</th><th class="num">Share</th>'
            '<th></th><th class="num">Last 12 months</th><th class="num">Addresses</th>'
            "<th>First commit</th><th>Last commit</th></tr>" + "".join(rows) + "</table></div>"
        )

        header = "".join(f'<th class="num">{KIND_LABELS[kind]}</th>' for kind in KINDS)
        quarter_rows = []
        for quarter in reversed(overview["quarters"]):
            cells = "".join(
                f'<td class="num">{share_text(quarter["by_kind"][kind], quarter["commits"])}</td>'
                for kind in KINDS
            )
            quarter_rows.append(
                f'<tr><td class="nowrap">{quarter["quarter"]}</td>'
                f'<td class="num">{format_int(quarter["commits"])}</td>{cells}</tr>'
            )
        parts.append(html_header(3, "Where the commits come from, by quarter"))
        parts.append(
            '<div class="table-scroll"><table class="share-table">'
            f'<tr><th>Quarter</th><th class="num">Commits</th>{header}</tr>'
            + "".join(quarter_rows)
            + "</table></div>"
        )
        return "".join(parts)

    def create_authors_html(self, data: Any, path: str) -> None:
        ###
        # Authors
        f = open(path + "/authors.html", "w", encoding="utf-8")
        self.print_header(f, "authors.html")

        self.print_nav(f, "authors.html")
        f.write("<h1>Authors</h1>")
        f.write(self._authors_summary_html(data))

        # Authors :: List of authors
        f.write(html_header(2, "List of authors"))
        # When only the top authors are listed, each section says so once, in its note
        max_authors = load_config()["max_authors"]
        allauthors = data.get_authors()
        top_of = (
            f"the top {max_authors} of {format_int(len(allauthors))} authors"
            if len(allauthors) > max_authors
            else ""
        )
        if top_of:
            f.write(f'<p class="section-note">{top_of[0].upper()}{top_of[1:]}, by commits.</p>')

        f.write('<div class="table-scroll"><table class="authors sortable" id="authors">')
        f.write(
            '<tr><th>Author</th><th class="num">Commits (%)</th><th class="num">+ lines</th><th class="num">- lines</th><th>First commit</th><th>Last commit</th><th class="unsortable num">Age</th><th class="num">Active days</th><th class="num"># by commits</th></tr>'
        )
        listed = data.get_authors(load_config()["max_authors"])
        top_commits = max((data.get_author_info(a)["commits"] for a in listed), default=0) or 1
        for author in listed:
            info = data.get_author_info(author)
            # A thin bar under the commit count shows the share relative to the top author
            share_bar = (
                '<span class="share-bar share-bar-inline" aria-hidden="true">'
                f'<span style="width: {100.0 * info["commits"] / top_commits:.1f}%"></span></span>'
            )
            f.write(
                '<tr><td>%s</td><td class="num">%s (%.1f%%)%s</td><td class="num stat-added">%s</td><td class="num stat-removed">%s</td><td class="nowrap">%s</td><td class="nowrap">%s</td><td class="nowrap num" title="%s days">%s</td><td class="num">%s</td><td class="num">%d</td></tr>'
                % (
                    author_html(author),
                    format_int(info["commits"]),
                    info["commits_frac"],
                    share_bar,
                    format_int(info["lines_added"]),
                    format_int(info["lines_removed"]),
                    info["date_first"],
                    info["date_last"],
                    format_int(info["timedelta"].days),
                    format_duration(info["timedelta"]),
                    format_int(len(info["active_days"])),
                    info["place_by_commits"],
                )
            )
        f.write("</table></div>")

        if top_of:
            rest = allauthors[max_authors:]
            max_list = load_config()["max_authors_list"]
            shown = ", ".join(author_html(a) for a in rest[:max_list])
            more = len(rest) - max_list
            f.write(
                f'<p class="moreauthors">The other {format_int(len(rest))}: {shown}'
                + (f", and {format_int(more)} more" if more > 0 else "")
                + ".</p>"
            )

        # The people first: who is around and when, how the group grew; then
        # the per-month leaders, and the measures that need more care to read
        # (lines added swing with generated or vendored code) or say less.

        # Replaces the former "Commits per Author" line chart; its anchor still lands here
        f.write('<span id="commits_per_author"></span>')
        f.write(html_header(2, "Contributor timeline"))
        f.write(self._contributor_timeline_html(data, data.get_authors(max_authors), top_of))

        # Contributor growth: everyone who has contributed so far, month by month
        if data.new_contributors_by_month:
            f.write(html_header(2, "Contributor growth"))
            f.write(
                '<p class="section-note">'
                "Contributors so far, month by month: each step up is a month in "
                "which someone made their first commit.</p>"
            )
            new = data.new_contributors_by_month
            growth_months = month_range([*new, *data.commits_by_month])
            total, totals, notes = 0, [], []
            for month in growth_months:
                total += new.get(month, 0)
                totals.append(total)
                notes.append(f"+{new[month]} new" if new.get(month) else "")
            quiet = quiet_months(data)
            growth_gap = {}
            if quiet and quiet[0] in growth_months and quiet[1] in growth_months:
                band = quiet_band(
                    *quiet, growth_months.index(quiet[0]), growth_months.index(quiet[1])
                )
                growth_gap = {"bands": [band]}
            f.write(
                self._render_chartjs(
                    "chart-contributor-growth",
                    "line",
                    growth_months,
                    [{"label": "Contributors", "data": totals, "stepped": True, "notes": notes}],
                    month_axis=True,
                    aspect_ratio=4,
                    annotations=growth_gap,
                )
            )

        f.write(self._ai_assisted_html(data))

        # Authors :: the top author of each year, then of each month (folded away).
        # The old "Author of Month/Year" anchors are kept so existing links still land here.
        f.write('<span id="author_of_month"></span><span id="author_of_year"></span>')
        f.write(html_header(2, "Top author per year and month"))
        f.write(
            '<p class="section-note">'
            "Who made the most commits in each year and month, the runners-up, "
            "and how many people committed.</p>"
        )
        f.write(self._top_authors_table("aoy", "Year", data.author_of_year, data.commits_by_year))
        months = len(data.author_of_month)
        f.write(
            '<details class="table-details"><summary>Table: top author of each month '
            f"({months} month{'' if months == 1 else 's'} with commits)</summary>"
        )
        f.write(
            self._top_authors_table("aom", "Month", data.author_of_month, data.commits_by_month)
        )
        f.write("</details>")

        # Build per-author time series data for Chart.js
        time_labels, loc_datasets = self._build_author_time_series(data)

        # The former heading's anchor still lands here
        f.write('<span id="cumulated_added_lines_of_code_per_author"></span>')
        f.write(html_header(2, "Cumulative lines added per author"))
        f.write(
            '<p class="section-note">'
            f"Lines added over time by {top_of or 'each author'}; "
            "the top 5 are in color, the rest in grey.</p>"
        )
        f.write(
            self._render_chartjs(
                "chart-loc-by-author",
                "line",
                time_labels,
                loc_datasets,
                time_axis=True,
                highlight=5,
                annotations=time_gap_annotations(data),
            )
        )

        f.write(self._organizations_html(data))

        # Domains: a bar table (the numbers used to be shown twice, as a table and a chart).
        # The former "Commits by Domains" anchor still lands here.
        f.write('<span id="commits_by_domains"></span>')
        f.write(html_header(2, "Commits by domain"))
        domains_by_commits = get_keys_sorted_by_value_key(data.domains, "commits")
        domains_by_commits.reverse()  # most first
        top_domains = domains_by_commits[: load_config()["max_domains"]]
        busiest = max((data.get_domain_info(d)["commits"] for d in top_domains), default=0) or 1
        total = data.get_total_commits() or 1
        rows = []
        for domain in top_domains:
            commits = data.get_domain_info(domain)["commits"]
            rows.append(
                f"<tr><td>{html.escape(domain)}</td>"
                f'<td class="num">{format_int(commits)}</td>'
                f'<td class="num">{100.0 * commits / total:.1f}%</td>'
                '<td class="share-cell"><span class="share-bar" aria-hidden="true">'
                f'<span style="width: {100.0 * commits / busiest:.1f}%"></span></span></td></tr>'
            )
        f.write(
            '<div class="table-scroll"><table class="share-table">'
            '<tr><th>Domain</th><th class="num">Commits</th><th class="num">Share</th><th></th></tr>'
            + "".join(rows)
            + "</table></div>"
        )

        self.print_footer(f)
        f.write("</body></html>")
        f.close()

    def create_files_html(self, data: Any, path: str) -> None:
        ###
        # Files
        f = open(path + "/files.html", "w", encoding="utf-8")
        self.print_header(f, "files.html")
        self.print_nav(f, "files.html")
        f.write("<h1>Files</h1>")

        total_files = data.get_total_files()
        extensions = len(data.extensions)
        tiles = [
            (
                "Files",
                format_int(total_files),
                f"{extensions} extension{'' if extensions == 1 else 's'}",
            ),
            (
                "Lines of Code",
                format_int(data.get_total_loc()),
                f"{data.get_total_loc() / total_files:.0f} per file" if total_files else "",
            ),
        ]
        if total_files:
            tiles.append(
                (
                    "Average File Size",
                    format_bytes(float(data.get_total_size()) / total_files),
                    f"{format_bytes(data.get_total_size())} in total",
                )
            )
        f.write(stat_tiles_html(tiles))

        # Files :: File count by date
        f.write(html_header(2, "File count by date"))

        # keep one point per day: the day's last commit
        files_by_date = {}
        for stamp in sorted(data.files_by_stamp.keys()):
            date_str = datetime.datetime.fromtimestamp(stamp).strftime("%Y-%m-%d")
            files_by_date[date_str] = (stamp, data.files_by_stamp[stamp])

        fbd_points = sorted(files_by_date.values())
        fbd_stamps = [stamp for stamp, _ in fbd_points]
        fbd_values = [count for _, count in fbd_points]
        f.write(
            self._render_chartjs(
                "chart-files-by-date",
                "line",
                fbd_stamps,
                [{"label": "Files", "data": fbd_values}],
                time_axis=True,
                annotations=time_gap_annotations(data),
            )
        )

        # f.write('<h2>Average file size by date</h2>')

        # Files :: Extensions
        f.write(html_header(2, "Extensions"))
        f.write(
            '<p class="section-note">'
            "Files with excluded extensions are not shown; "
            "configure <code>exclude_exts</code> in gitstats.conf.</p>"
        )
        # A bar table ranked by lines, like the churn and domain tables; binary
        # files (no lines) show a dash instead of "0 (0.0%)"
        total_loc = data.get_total_loc()
        exts = sorted(
            data.extensions.items(), key=lambda kv: (-kv[1]["lines"], -kv[1]["files"], kv[0])
        )
        max_lines = max((info["lines"] for _, info in exts), default=0) or 1
        rows = []
        for ext, info in exts:
            files, lines = info["files"], info["lines"]
            name = html.escape(ext) if ext else "<em>no extension</em>"
            if lines:
                share = f"{100.0 * lines / total_loc:.1f}%" if total_loc else "—"
                cells = (
                    f'<td class="num">{format_int(lines)}</td><td class="num">{share}</td>'
                    f'<td class="num">{format_int(lines // files) if files else "—"}</td>'
                )
                bar = f'<span style="width: {100.0 * lines / max_lines:.1f}%"></span>'
            else:
                cells = '<td class="num">—</td><td class="num">—</td><td class="num">—</td>'
                bar = ""
            rows.append(
                f'<tr><td>{name}</td><td class="num">{format_int(files)}</td>{cells}'
                '<td class="share-cell"><span class="share-bar" aria-hidden="true">'
                f"{bar}</span></td></tr>"
            )
        f.write(
            '<div class="table-scroll"><table class="sortable share-table" id="ext">'
            '<tr><th>Extension</th><th class="num">Files</th><th class="num">Lines</th>'
            '<th class="num">Share</th><th class="num">Lines/file</th>'
            '<th class="unsortable"></th></tr>' + "".join(rows) + "</table></div>"
        )

        # Files :: Code Churn (most frequently changed files)
        if data.file_churn:
            f.write(html_header(2, "Most changed files (code churn)"))
            f.write(
                '<p class="section-note">'
                "Files in the current tree touched most often across all commits. "
                "High-churn files are hotspots that may benefit from extra review or refactoring.</p>"
            )
            # Only files that still exist: a deleted file is no hotspot to review
            current = head_files(data)
            churn_sorted = sorted(
                (
                    (path, count)
                    for path, count in data.file_churn.items()
                    if current is None or path in current
                ),
                key=lambda x: x[1],
                reverse=True,
            )
            top_churn = churn_sorted[:25]
            max_churn = max(1, top_churn[0][1]) if top_churn else 1
            # A bar table: the counts used to be shown twice, in a heat-colored
            # table and a bar chart whose rotated path labels were unreadable
            rows = [
                f'<tr><td class="path">{html.escape(filepath)}</td>'
                f'<td class="num" data-label="Times changed">{format_int(count)}</td>'
                '<td class="share-cell"><span class="share-bar" aria-hidden="true">'
                f'<span style="width: {100.0 * count / max_churn:.1f}%"></span></span></td></tr>'
                for filepath, count in top_churn
            ]
            f.write(
                f'<div class="table-scroll"><table class="sortable share-table {FILE_TABLE}" id="churn">'
                '<tr><th>File</th><th class="num">Times Changed</th><th class="unsortable"></th></tr>'
                + "".join(rows)
                + "</table></div>"
            )
            # The Hotspots page weighs the same counts against each file's size
            f.write(
                '<p class="more-link"><a href="hotspots.html">'
                "Change frequency by file size &rarr;</a></p>"
            )

        self.print_footer(f)
        f.write("</body></html>")
        f.close()

    def create_lines_html(self, data: Any, path: str) -> None:
        ###
        # Lines
        f = open(path + "/lines.html", "w", encoding="utf-8")
        self.print_header(f, "lines.html")
        self.print_nav(f, "lines.html")
        f.write("<h1>Lines</h1>")

        total_commits = data.get_total_commits()
        f.write(
            stat_tiles_html(
                [
                    (
                        "Lines of Code",
                        format_int(data.get_total_loc()),
                        f"in {format_int(data.get_total_files())} files",
                    ),
                    (
                        "Lines Added",
                        f'<span class="stat-added">+{format_int(data.total_lines_added)}</span>',
                        f"{data.total_lines_added / total_commits:.0f} per commit"
                        if total_commits
                        else "",
                    ),
                    (
                        "Lines Removed",
                        f'<span class="stat-removed">−{format_int(data.total_lines_removed)}</span>',
                        f"{data.total_lines_removed / total_commits:.0f} per commit"
                        if total_commits
                        else "",
                    ),
                ]
            )
        )

        f.write(html_header(2, "Lines of code"))
        loc_stamps = sorted(data.changes_by_date.keys())
        loc_values = [data.changes_by_date[s]["lines"] for s in loc_stamps]
        f.write(
            self._render_chartjs(
                "chart-lines-of-code",
                "line",
                loc_stamps,
                [{"label": "Lines", "data": loc_values}],
                time_axis=True,
                annotations=time_gap_annotations(data),
            )
        )

        # Lines :: added (up) and removed (down) in each month
        months = month_range([*data.lines_added_by_month, *data.lines_removed_by_month])
        if months:
            f.write(html_header(2, "Lines added and removed per month"))
            f.write(
                '<p class="section-note">Lines added (green, up) and removed (red, down) '
                "by each month's commits.</p>"
            )
            quiet = quiet_months(data)
            churn_gap = {}
            if quiet and quiet[0] in months and quiet[1] in months:
                band = quiet_band(*quiet, months.index(quiet[0]), months.index(quiet[1]))
                churn_gap = {"bands": [band]}
            f.write(
                self._render_chartjs(
                    "chart-lines-by-month",
                    "bar",
                    months,
                    [
                        {
                            "label": "Added",
                            "data": [data.lines_added_by_month.get(m, 0) for m in months],
                            "colorVar": "--success-color",
                            "borderWidth": 0,
                        },
                        {
                            "label": "Removed",
                            "data": [-data.lines_removed_by_month.get(m, 0) for m in months],
                            "colorVar": "--danger-color",
                            "borderWidth": 0,
                        },
                    ],
                    month_axis=True,
                    diverging=True,
                    aspect_ratio=4,
                    annotations=churn_gap,
                )
            )

        self.print_footer(f)
        f.write("</body></html>")
        f.close()

    def create_tags_html(self, data: Any, path: str) -> None:
        ###
        # tags.html
        f = open(path + "/tags.html", "w", encoding="utf-8")
        self.print_header(f, "tags.html")
        self.print_nav(f, "tags.html")
        f.write("<h1>Tags</h1>")

        if data.tags:
            latest = tags_newest_first(data.tags)[0]
            f.write(
                stat_tiles_html(
                    [
                        (
                            "Tags",
                            format_int(len(data.tags)),
                            f"latest {html.escape(latest)} &middot; {data.tags[latest]['date']}",
                        ),
                        (
                            "Commits per Tag",
                            f"{data.get_total_commits() / len(data.tags):.1f}",
                            f"{format_int(data.get_total_commits())} commits in total",
                        ),
                    ]
                )
            )
        else:
            f.write(stat_tiles_html([("Tags", "0", "no tags yet")]))

        if data.tags:
            f.write(html_header(2, "All tags"))
            f.write(
                '<p class="section-note">Newest first. Commits are those since the '
                "previous tag, and the authors who made them.</p>"
            )
            f.write('<div class="table-scroll"><table class="tags sortable" id="tags">')
            f.write(
                '<tr><th>Name</th><th>Date</th><th class="num">Commits</th>'
                '<th class="unsortable">Authors</th></tr>'
            )
            max_tags_authors = load_config()["max_tags_authors"]
            for tag in tags_newest_first(data.tags):
                authorinfo = []
                self.authors_by_commits = get_keys_sorted_by_values(data.tags[tag]["authors"])
                authors_reversed = list(reversed(self.authors_by_commits))
                # max_tags_authors < 0 (e.g., -1) means no limit
                if max_tags_authors >= 0 and len(authors_reversed) > max_tags_authors:
                    authors_shown = authors_reversed[:max_tags_authors]
                    remaining = len(authors_reversed) - max_tags_authors
                    for i in authors_shown:
                        authorinfo.append(
                            f"{author_html(i)} ({format_int(data.tags[tag]['authors'][i])})"
                        )
                    authorinfo.append("<em>and %d more authors</em>" % remaining)
                else:
                    for i in authors_reversed:
                        authorinfo.append(
                            f"{author_html(i)} ({format_int(data.tags[tag]['authors'][i])})"
                        )
                f.write(
                    '<tr><td class="nowrap">%s</td><td class="nowrap">%s</td><td class="num">%s</td><td>%s</td></tr>'
                    % (
                        html.escape(tag),
                        data.tags[tag]["date"],
                        format_int(data.tags[tag]["commits"]),
                        ", ".join(authorinfo),
                    )
                )
            f.write("</table></div>")

        self.print_footer(f)
        f.write("</body></html>")
        f.close()

    def create_badges_html(self, data: Any, path: str) -> None:
        """Create the Badges page: every badge, ready to copy into a README.

        The snippets need the report's public address, which the report
        cannot know when it is generated. The page's script reads it from
        the address the page is served from, and lets the reader type it in
        (remembered in their browser) when the page is opened from a file.
        """
        conf = load_config()
        style = str(conf.get("badge_style", "") or "flat")
        if style not in STYLE_NAMES:
            style = "flat"
        names = [name for _, _, badges in BADGES_PAGE_SECTIONS for name, _ in badges]
        metric = str(conf.get("badge_metric", "") or "commits")
        if metric not in names:
            metric = "commits"
        link = self.site_url or BADGES_PLACEHOLDER_URL

        def option_buttons(attr: str, options: list[tuple[str, str]], current: str) -> str:
            return "".join(
                f'<button type="button" {attr}="{value}" '
                f'aria-pressed="{"true" if value == current else "false"}">{label}</button>'
                for value, label in options
            )

        def row(kind: str, name: str, title: str, desc: str, image: str, alt: str) -> str:
            if kind == "endpoint":
                preview = f'<span class="badge-json">badges/{name}.json</span>'
            else:
                preview = f'<img src="{image}" alt="{html.escape(alt)}">'
            code = f"[![{alt}]({link}{image})]({link})"
            if kind == "endpoint":
                code = f"[![{alt}](https://img.shields.io/endpoint?url={link}{image})]({link})"
            return (
                f'<div class="badge-row" data-kind="{kind}" data-badge="{name}" '
                f'data-title="{html.escape(title)}">'
                f'<div class="badge-info"><div class="badge-name"><code>{html.escape(title)}</code>'
                f"<span>{html.escape(desc)}</span></div>{preview}</div>"
                f'<pre class="badge-code">{html.escape(code)}</pre>'
                f'<button type="button" class="badge-copy" '
                f'aria-label="Copy Markdown for {html.escape(title)}">{_COPY_ICONS}'
                "<span>Copy</span></button></div>"
            )

        f = self._open_report_file(path, "badges.html")
        self.print_header(f, "badges.html")
        self.print_nav(f, "badges.html")
        f.write("<h1>Badges</h1>")
        f.write(
            '<p class="section-note">Live badges for this report. Pick a style and a format, '
            "then copy a snippet into a README or wiki page: the badge links back here and "
            "updates every time the report is regenerated.</p>"
        )

        f.write(
            '<div class="badge-url"><label for="badge-url">Report URL</label>'
            '<div class="badge-url-field">'
            '<input id="badge-url" type="url" placeholder="https://reports.example.com/my-repo/" '
            f'value="{html.escape(self.site_url)}" spellcheck="false" autocomplete="off">'
            '<span id="badge-url-status" class="badge-url-status is-missing">not set</span></div>'
            '<p class="badge-url-hint" data-url-hint="detected" hidden>Read from this page\'s '
            "address. Change it if the report is also served from another URL.</p>"
            '<p class="badge-url-hint" data-url-hint="site" hidden>Set with '
            "<code>--site-url</code> when the report was generated.</p>"
            '<p class="badge-url-hint" data-url-hint="entered" hidden>Remembered in this '
            "browser.</p>"
            '<p class="badge-url-hint" data-url-hint="cleared" hidden>Enter the address the '
            "report is published at, or leave it empty to use this page's address.</p>"
            '<p class="badge-url-hint" data-url-hint="invalid" hidden>That doesn\'t look like a '
            "web address: use the report's full address, starting with https://. It won't "
            "be remembered.</p>"
            '<p class="badge-url-hint" data-url-hint="missing">This page was opened from a file, '
            "so it can't tell where the report lives. Enter the address it's published at, or "
            "generate the report with <code>--site-url</code> to fill it in.</p></div>"
        )

        f.write(
            '<div class="badge-controls">'
            '<div class="badge-options" role="group" aria-labelledby="badge-style-label">'
            '<span id="badge-style-label" class="badge-options-label">Style</span>'
            '<div class="badge-option-list">'
            + option_buttons("data-style", [(name, name) for name in STYLE_NAMES], style)
            + "</div></div>"
            '<div class="badge-options" role="group" aria-labelledby="badge-format-label">'
            '<span id="badge-format-label" class="badge-options-label">Format</span>'
            '<div class="badge-option-list">'
            + option_buttons(
                "data-format",
                [("md", "Markdown"), ("rst", "reStructuredText"), ("html", "HTML")],
                "md",
            )
            + "</div></div></div>"
        )

        for title, note, badges in BADGES_PAGE_SECTIONS:
            f.write(html_header(2, title))
            f.write(f'<p class="section-note">{note}</p><div class="badge-list">')
            for name, desc in badges:
                if name == "ai-assisted" and ai_assisted_share(data) is None:
                    continue  # data collected without counting them
                alt = AI_ASSISTED_LABEL if name == "ai-assisted" else f"GitStats {name}"
                f.write(row("style", name, name, desc, f"badges/{style}/{name}.svg", alt))
            f.write("</div>")

        f.write(html_header(2, "Other ways to use them"))
        f.write(
            '<p class="section-note">Every badge is a plain SVG file under '
            "<code>badges/&lt;style&gt;/</code>, rewritten each time the report is "
            'generated.</p><div class="badge-list">'
        )
        f.write(
            row(
                "default",
                metric,
                "badge.svg",
                f"The default badge: {metric} in {style}, set by badge_metric and badge_style",
                "badge.svg",
                "GitStats",
            )
        )
        f.write(
            row(
                "endpoint",
                metric,
                "shields.io endpoint",
                "The same numbers as JSON, for shields.io styles and logos",
                f"badges/{metric}.json",
                f"GitStats {metric}",
            )
        )
        f.write("</div>")

        # Badges :: Repo Wrapped, the card written by --wrapped
        f.write(html_header(2, "Repo Wrapped"))
        card = self.wrapped_card
        if card:
            name = html.escape(str(card["file"]))
            year = int(card["year"])
            project = str(getattr(data, "project_name", "") or "repository")
            alt = f"{project} in {year}"
            code = f"[![{alt}]({link}{card['file']})]({link})"
            f.write(
                '<p class="section-note">A card of one year in the repository, written by '
                '<code class="nowrap">--wrapped</code>: show it in a README, or save it and '
                "share it as "
                'an image.</p><div class="badge-list">'
                f'<div class="badge-row" data-kind="card" data-badge="{name}" '
                f'data-alt="{html.escape(alt)}" data-title="{name}">'
                f'<div class="badge-info"><div class="badge-name"><code>{name}</code>'
                f"<span>1080 &times; 1080, {html.escape(str(card.get('theme', '')))} theme</span>"
                f'</div><a class="wrapped-preview" href="{name}">'
                f'<img src="{name}" width="240" height="240" '
                f'alt="Repo Wrapped card for {html.escape(alt)}"></a></div>'
                f'<pre class="badge-code">{html.escape(code)}</pre>'
                f'<button type="button" class="badge-copy" '
                f'aria-label="Copy Markdown for {name}">{_COPY_ICONS}'
                "<span>Copy</span></button></div></div>"
                f'<p class="more-link"><a href="{name}" download>Download SVG &rarr;</a></p>'
            )
        else:
            f.write(
                '<p class="section-note">A card of one year in the repository, to show in a '
                "README or share as an image. There is none next to this report: generate it "
                'with <code class="nowrap">--wrapped</code> to get one.</p>'
            )
        f.write('<p id="badge-live" class="visually-hidden" aria-live="polite"></p>')

        page_data = {
            "style": style,
            "siteUrl": self.site_url,
            "placeholder": BADGES_PLACEHOLDER_URL,
        }
        f.write(
            '<script type="application/json" id="badge-data">'
            + json.dumps(page_data).replace("</", "<\\/")
            + "</script>"
        )
        f.write(BADGES_SCRIPT)

        self.print_footer(f)
        f.write("</body></html>")
        f.close()

    def _open_report_file(self, path: str, filename: str) -> Any:
        """Open a report page for writing, confined to the report directory.

        ``filename`` is always a hard-coded page name; resolving the target and
        checking it stays under the report root guards against directory
        traversal.
        """
        base = os.path.abspath(path)
        target = os.path.abspath(os.path.join(base, filename))
        if os.path.commonpath([base, target]) != base:
            raise ValueError(f"Refusing to write outside report directory: {filename}")
        return open(target, "w", encoding="utf-8")

    def create_ownership_html(self, data: Any, path: str) -> None:
        """Create the Code Ownership page.

        Turns the per-author file-edit data into actionable views: files with a
        single owner (bus-factor / knowledge-silo risk), how ownership is
        concentrated per author, and the files touched by the most people
        (coordination hotspots).
        """
        f = self._open_report_file(path, "ownership.html")
        self.print_header(f, "ownership.html")
        self.print_nav(f, "ownership.html")
        f.write("<h1>Code Ownership</h1>")

        current = head_files(data)
        ownership = head_ownership(data)

        if not ownership["files"]:
            f.write(
                '<p class="section-note">No ownership data available. '
                "Ownership is derived from which files each author changes; try "
                "analyzing a repository with commit history.</p>"
            )
            self.print_footer(f)
            f.write("</body></html>")
            f.close()
            return

        total = ownership["total_files"]
        single = ownership["single_owner_files"]
        single_pct = (100.0 * single / total) if total else 0.0

        # Summary
        f.write(
            '<p class="section-note">'
            "Ownership is measured by how many commits each author made to each "
            "file in the current tree. It highlights <strong>bus-factor risk</strong> "
            "(files only one person has ever touched) and where knowledge is concentrated. "
            "The <strong>bus factor</strong> is the smallest number of people who are, "
            "between them, primary owner of more than half of the files.</p>"
        )
        bus_factor = ownership["bus_factor"]
        bus_owned = (
            f"primary owner of {format_int(ownership['bus_factor_files'])} "
            f"of {format_int(total)} files"
        )
        f.write(
            stat_tiles_html(
                [
                    (
                        "Files Tracked",
                        format_int(total),
                        "in the current tree" if current is not None else "every file changed",
                    ),
                    (
                        "Bus Factor",
                        format_int(bus_factor),
                        f"{author_html(ownership['bus_factor_authors'][0])} is {bus_owned}"
                        if bus_factor == 1
                        else f"{format_int(bus_factor)} authors are {bus_owned}",
                    ),
                    (
                        "Single-Owner Files",
                        format_int(single),
                        f"{single_pct:.1f}% of tracked files",
                    ),
                    (
                        "Contributors",
                        format_int(len(ownership["authors"])),
                        "authors who changed files",
                    ),
                ]
            )
        )

        # Bus-factor risk: single-owner files, most-changed first
        f.write(html_header(2, "Bus factor risk — single-owner files"))
        f.write(
            '<p class="section-note">'
            "Files only one author has ever changed. The more a file has "
            "changed, the more knowledge is at risk if that person leaves.</p>"
        )
        risk_files = [fs for fs in ownership["files"] if fs["contributors"] == 1]
        if risk_files:

            def risk_table(table_id: str, rows: list[dict]) -> str:
                return (
                    f'<div class="table-scroll"><table class="sortable {FILE_TABLE}" id="{table_id}">'
                    '<tr><th>File</th><th>Sole owner</th><th class="num">Commits</th></tr>'
                    + "".join(
                        f'<tr><td class="path">{html.escape(fs["path"])}</td>'
                        f'<td data-label="Sole owner">{author_html(fs["owner"])}</td>'
                        f'<td class="num" data-label="Commits">{format_int(fs["edits"])}</td></tr>'
                        for fs in rows
                    )
                    + "</table></div>"
                )

            # The ten most-changed are shown; the full list (up to 100) is folded away
            f.write(risk_table("ownership-busfactor", risk_files[:10]))
            if len(risk_files) > 10:
                count = len(risk_files)
                what = (
                    f"all {format_int(count)} single-owner files"
                    if count <= 100
                    else f"the 100 most-changed of {format_int(count)} single-owner files"
                )
                f.write(f'<details class="table-details"><summary>Table: {what}</summary>')
                f.write(risk_table("ownership-busfactor-all", risk_files[:100]))
                f.write("</details>")
        else:
            f.write("<p>No single-owner files — every file has multiple contributors.</p>")

        # Ownership concentration by author
        f.write(html_header(2, "Ownership by author"))
        f.write(
            '<p class="section-note">'
            "Primary owner = the author with the most commits to a file. "
            "Solely owned = files only that author has touched.</p>"
        )
        f.write(
            '<div class="table-scroll"><table class="sortable" id="ownership-by-author">'
            '<tr><th>Author</th><th class="num">Files owned</th><th class="num">Solely owned</th>'
            '<th class="num">Files touched</th></tr>'
        )
        for a in ownership["authors"][:25]:
            f.write(
                '<tr><td>%s</td><td class="num">%s</td><td class="num">%s</td><td class="num">%s</td></tr>'
                % (
                    author_html(a["author"]),
                    format_int(a["files_owned"]),
                    format_int(a["files_solely_owned"]),
                    format_int(a["files_touched"]),
                )
            )
        f.write("</table></div>")
        if len(ownership["authors"]) > 25:
            f.write(
                '<p class="moreauthors">Showing top 25 of %d contributors.</p>'
                % len(ownership["authors"])
            )

        # Coordination hotspots: files with the most contributors
        f.write(html_header(2, "Most shared files"))
        f.write(
            '<p class="section-note">'
            "Files touched by the most people — shared code where changes "
            "are most likely to need coordination.</p>"
        )
        shared = sorted(
            (fs for fs in ownership["files"] if fs["contributors"] >= 2),
            key=lambda x: (x["contributors"], x["edits"]),
            reverse=True,
        )
        if shared:
            f.write(
                f'<div class="table-scroll"><table class="sortable {FILE_TABLE}" id="ownership-shared">'
                '<tr><th>File</th><th class="num">Contributors</th><th>Primary owner</th>'
                '<th class="num">Owner share</th></tr>'
            )
            for fs in shared[:20]:
                f.write(
                    '<tr><td class="path">%s</td><td class="num" data-label="Contributors">%s</td>'
                    '<td data-label="Primary owner">%s</td>'
                    '<td class="num" data-label="Owner share">%.1f%%</td></tr>'
                    % (
                        html.escape(fs["path"]),
                        format_int(fs["contributors"]),
                        author_html(fs["owner"]),
                        fs["ownership_pct"],
                    )
                )
            f.write("</table></div>")
        else:
            f.write("<p>No files have more than one contributor yet.</p>")

        self.print_footer(f)
        f.write("</body></html>")
        f.close()

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
                f"{format_int(median_lines)} line{'' if median_lines == 1 else 's'}",
                "half of the files are at least this large",
            ),
            (
                "Median Changes",
                f"{format_int(median_churn)} commit{'' if median_churn == 1 else 's'}",
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
        f.write(
            '<p class="section-note">'
            "Each dot is a file; a bigger dot is a higher score. The dashed lines mark "
            "the median file size and the median number of changes, so the large files "
            f"that change often are in the top right. Both axes are logarithmic.{shown}</p>"
        )
        page_data = {
            "medianLines": median_lines,
            "medianChurn": median_churn,
            "points": [[fs["path"], fs["lines"], fs["churn"], fs["score"]] for fs in plotted],
        }
        f.write(
            '<div class="chart-box has-legend" style="--chart-ratio: 2.4">'
            '<canvas id="chart-hotspots"></canvas></div>'
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

        def hotspot_table(table_id: str, rows: list[dict]) -> str:
            return (
                f'<div class="table-scroll"><table class="sortable share-table {FILE_TABLE}" '
                f'id="{table_id}">'
                '<tr><th>File</th><th class="num">Lines</th><th class="num">Changes</th>'
                + ('<th class="num">Authors</th>' if authors_of else "")
                + '<th class="num">Score</th><th class="unsortable"></th></tr>'
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
                f"all {format_int(count)} files"
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

    _ERA_DESCRIPTIONS = {
        "birth": "first commits",
        "peak": "busiest year",
        "surge": "well above the usual pace",
        "revival": "active again after a lull",
        "quiet": "well below the usual pace",
        "dormant": "no commits",
        "steady": "",
    }

    def create_history_html(self, data: Any, path: str) -> None:
        """Create the History page: the project's life, one year at a time.

        A deterministic timeline derived entirely from already-collected data:
        each year is classified against the repository's own baseline (birth,
        peak, surge, quiet, dormant, revival), and carries its commit volume,
        the year's leading author, the contributors who made their first
        commit that year, and the releases tagged in it.
        """
        f = self._open_report_file(path, "history.html")
        self.print_header(f, "history.html")
        self.print_nav(f, "history.html")
        f.write("<h1>History</h1>")

        history = compute_project_history(data)
        years = history["years"]

        if not years:
            f.write(
                '<p class="section-note">No history to tell yet — '
                "this repository has no commits in the analyzed range.</p>"
            )
            self.print_footer(f)
            f.write("</body></html>")
            f.close()
            return

        span = history["last_year"] - history["first_year"] + 1
        peak_commits = next(y["commits"] for y in years if y["year"] == history["peak_year"])
        release_years = [y["year"] for y in years if y["releases"]]
        f.write(
            '<p class="section-note">'
            "The project's life, one year at a time, told from the commit "
            "record: how activity rose and fell against the project's own "
            "baseline, who arrived when, and what was released.</p>"
        )
        f.write(
            stat_tiles_html(
                [
                    (
                        "Span",
                        f"{history['first_year']} – {history['last_year']}",
                        f"{span} year{'s' if span != 1 else ''}",
                    ),
                    (
                        "Peak Year",
                        str(history["peak_year"]),
                        f"{format_int(peak_commits)} commits",
                    ),
                    (
                        "Releases",
                        format_int(history["total_releases"]),
                        f"latest in {release_years[-1]}" if release_years else "none tagged",
                    ),
                ]
            )
        )

        # Optional AI narration: parsed into per-year chapters and laid over
        # the deterministic facts, which stay visible either way so the story
        # can always be checked against the record it was written from.
        ai_summaries = getattr(data, "ai_summaries", {}) or {}
        chronicle_text = (ai_summaries.get("chronicle") or {}).get("summary") or ""
        chronicle = parse_chronicle(chronicle_text) if chronicle_text else None

        if chronicle and chronicle["prologue"]:
            f.write(
                '<div class="history-prologue"><p>%s</p>'
                '<p class="history-ai-note">AI narration, generated from the facts below.</p></div>'
                % html.escape(chronicle["prologue"])
            )
        if chronicle_text and (not chronicle or not chronicle["chapters"]):
            # The model ignored the format: show its text whole rather than lose it.
            f.write(
                '<div class="history-prologue"><p>%s</p>'
                '<p class="history-ai-note">AI narration, generated from the facts below.</p></div>'
                % html.escape(chronicle_text)
            )

        # Runs of dormant years read as one stretch ("2016–2023, 8 years without
        # commits") instead of a row per empty year; a year the AI narration wrote
        # a chapter for keeps its own row.
        def own_row(entry: dict) -> bool:
            has_chapter = bool(chronicle and chronicle["chapters"].get(entry["year"]))
            return entry["era"] != "dormant" or entry["commits"] > 0 or has_chapter

        rows: list[list[dict]] = []
        for entry in years:
            if not own_row(entry) and rows and not own_row(rows[-1][-1]):
                rows[-1].append(entry)
            else:
                rows.append([entry])

        max_commits = max(y["commits"] for y in years)
        for row in rows:
            if len(row) > 1:
                first, last = row[0]["year"], row[-1]["year"]
                f.write(
                    '<div class="history-year history-gap">'
                    '<div class="history-year-head">'
                    f'<span class="history-year-num">{first}–{last}</span>'
                    '<span class="history-era history-era-dormant">DORMANT</span>'
                    f'<span class="history-era-desc">{len(row)} years without commits</span>'
                    "</div>"
                    f'<p class="history-facts">No commits from {first} to {last}.</p>'
                    "</div>"
                )
                continue
            entry = row[0]
            era = entry["era"]
            desc = self._ERA_DESCRIPTIONS.get(era, "")
            bar_pct = round(100.0 * entry["commits"] / max_commits, 1) if max_commits else 0.0
            chapter = chronicle["chapters"].get(entry["year"]) if chronicle else None

            f.write('<div class="history-year">')
            f.write(
                '<div class="history-year-head">'
                '<span class="history-year-num">%d</span>'
                '<span class="history-era history-era-%s">%s</span>'
                "%s%s</div>"
                % (
                    entry["year"],
                    era,
                    era.upper(),
                    '<span class="history-chapter-title">%s</span>' % html.escape(chapter["title"])
                    if chapter and chapter["title"]
                    else "",
                    f'<span class="history-era-desc">{desc}</span>'
                    if desc and not (chapter and chapter["title"])
                    else "",
                )
            )
            if chapter and chapter["story"]:
                f.write('<p class="history-story">%s</p>' % html.escape(chapter["story"]))
            f.write(
                '<div class="history-bar-track"><div class="history-bar" '
                'style="width:%s%%"></div></div>' % bar_pct
            )

            if entry["commits"]:
                facts = "%s commits (%s%%) &middot; +%s / &minus;%s lines &middot; %s author%s" % (
                    format_int(entry["commits"]),
                    entry["commits_pct"],
                    format_int(entry["lines_added"]),
                    format_int(entry["lines_removed"]),
                    format_int(entry["active_authors"]),
                    "s" if entry["active_authors"] != 1 else "",
                )
                f.write(f'<p class="history-facts">{facts}</p>')
                if entry["top_author"]:
                    f.write(
                        '<p class="history-people">Led by <strong>%s</strong> (%s commit%s)</p>'
                        % (
                            html.escape(entry["top_author"]),
                            format_int(entry["top_author_commits"]),
                            "" if entry["top_author_commits"] == 1 else "s",
                        )
                    )
                if entry["newcomers"]:
                    f.write(
                        '<p class="history-people">First commits: %s%s</p>'
                        % (
                            ", ".join(html.escape(n) for n in entry["newcomers"][:6]),
                            " (+%d more)" % (len(entry["newcomers"]) - 6)
                            if len(entry["newcomers"]) > 6
                            else "",
                        )
                    )
                if entry["releases"]:
                    f.write(
                        '<p class="history-people">Released: %s%s</p>'
                        % (
                            ", ".join(html.escape(t) for t in entry["releases"][:5]),
                            " (+%d more)" % (len(entry["releases"]) - 5)
                            if len(entry["releases"]) > 5
                            else "",
                        )
                    )
                card = self.wrapped_card
                if card and card.get("year") == entry["year"]:
                    f.write(
                        '<p class="history-people">'
                        f'<a href="{html.escape(str(card["file"]))}">Wrapped card &rarr;</a></p>'
                    )
            else:
                f.write('<p class="history-facts">No commits this year.</p>')
            f.write("</div>")

        self.print_footer(f)
        f.write("</body></html>")
        f.close()

    def create_ai_insights_html(self, data: Any, path: str) -> None:
        """
        Create a dedicated AI Insights page with all AI-generated summaries.
        """
        # Get language from config
        language = load_config().get("ai_language", "en")

        f = open(path + "/ai-insights.html", "w", encoding="utf-8")
        self.print_header(f, "ai-insights.html")
        self.print_nav(f, "ai-insights.html")
        f.write(f"<h1>{get_i18n_text('ai_insights_title', language)}</h1>")

        f.write(f"""
        <div class="ai-insights-intro">
            <p>{get_i18n_text("ai_insights_intro", language)}</p>
        </div>
        """)

        # Get all AI summaries
        summaries = data.ai_summaries

        # Define sections with titles and descriptions
        sections = [
            {
                "key": "index",
                "title": get_i18n_text("project_overview", language),
                "description": get_i18n_text("project_overview_desc", language),
            },
            {
                "key": "activity",
                "title": get_i18n_text("activity_patterns", language),
                "description": get_i18n_text("activity_patterns_desc", language),
            },
            {
                "key": "lines",
                "title": get_i18n_text("code_evolution", language),
                "description": get_i18n_text("code_evolution_desc", language),
            },
        ]

        # Generate sections
        for section in sections:
            key = section["key"]
            if key not in summaries:
                continue

            summary_data = summaries[key]
            summary_text = summary_data.get("summary", "")
            error = summary_data.get("error")

            f.write('<div class="ai-insight-section">')
            f.write(f'<h2 id="{key}">{section["title"]}</h2>')
            f.write(f'<p class="section-description"><em>{section["description"]}</em></p>')

            if error:
                f.write(f"""
                <div class="ai-summary-error">
                    <p><strong>{get_i18n_text("analysis_unavailable", language)}</strong></p>
                    <p><em>{error}</em></p>
                </div>
                """)
            elif summary_text:
                f.write(f"""
                <div class="ai-summary-content">
                    {summary_text}
                </div>
                """)
            else:
                f.write(f"<p><em>{get_i18n_text('no_analysis', language)}</em></p>")

            f.write("</div>")

        # Add disclaimer
        f.write(f"""
        <div class="ai-disclaimer">
            <h3>{get_i18n_text("about_ai_insights", language)}</h3>
            <p>{get_i18n_text("ai_disclaimer", language)}</p>
            <p>{get_i18n_text("bot_note", language)}</p>
        </div>
        """)

        self.print_footer(f)
        f.write("</body></html>")
        f.close()

    # Multi-series colors are the CSS variables --series-1 .. --series-6, so
    # they switch with the theme (see applyChartTheme)
    SERIES_COLORS = 6
    # Series outside the highlighted top N: a neutral grey readable on both themes
    OTHER_SERIES_COLOR = "rgba(128, 128, 128, 0.45)"

    def _top_authors_table(
        self, table_id: str, period: str, authors_by_period: dict, commits_by_period: dict
    ) -> str:
        """A sortable table of each period's top author, newest period first."""
        top = load_config()["authors_top"]
        rows = [
            f'<div class="table-scroll"><table class="sortable" id="{table_id}">'
            f'<tr><th>{period}</th><th>Author</th><th class="num">Commits (%)</th>'
            f'<th class="unsortable">Next top {top}</th><th class="num">Authors</th></tr>'
        ]
        for key in sorted(authors_by_period, reverse=True):
            authors = get_keys_sorted_by_values(authors_by_period[key])
            authors.reverse()
            commits = authors_by_period[key][authors[0]]
            total = commits_by_period[key]
            rows.append(
                f"<tr><td>{key}</td><td>{author_html(authors[0])}</td>"
                f'<td class="num">{format_int(commits)} ({100.0 * commits / total:.1f}% of {format_int(total)})</td>'
                f"<td>{', '.join(author_html(a) for a in authors[1 : top + 1])}</td>"
                f'<td class="num">{len(authors)}</td></tr>'
            )
        rows.append("</table></div>")
        return "".join(rows)

    def _render_chartjs(
        self,
        chart_id,
        chart_type,
        labels,
        datasets,
        x_ticks_rotate=False,
        aspect_ratio=3,
        max_bar_thickness=None,
        time_axis=False,
        highlight=None,
        annotations=None,
        tooltip_share=False,
        month_axis=False,
        diverging=False,
    ):
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

        js_datasets = []
        for i, ds in enumerate(datasets):
            series = i % self.SERIES_COLORS + 1
            entry = dict(ds)
            if "colorVar" in entry:
                entry["backgroundColor"] = entry["borderColor"] = f"__CSSVAR:{entry['colorVar']}__"
            if is_multi and highlight is not None and i >= highlight:
                entry.setdefault("borderColor", self.OTHER_SERIES_COLOR)
                entry.setdefault("backgroundColor", self.OTHER_SERIES_COLOR)
                entry.setdefault("fill", False)
                entry.setdefault("pointRadius", 0)
                entry.setdefault("borderWidth", 1)
                entry.setdefault("order", 1)  # higher order is drawn first, i.e. behind
            elif is_multi:
                entry.setdefault("borderColor", f"__CSS_SERIES_{series}__")
                entry.setdefault("backgroundColor", f"__CSS_SERIES_{series}_FILL__")
                if "colorVar" not in entry:
                    entry["series"] = series
                entry.setdefault("fill", False)
                entry.setdefault("tension", 0.1)
                entry.setdefault("pointRadius", 0)
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
                    entry.setdefault("pointRadius", 0)
                    entry.setdefault("pointHoverRadius", 3)
            if time_axis and chart_type == "line":
                entry.setdefault("stepped", True)
            js_datasets.append(entry)

        gap_json = "null"
        if time_axis:
            labels = [int(stamp) * 1000 for stamp in labels]
            if annotations:
                annotations, gap = collapse_gap_time(labels, annotations)
                gap_json = json.dumps(gap)
        elif annotations:
            labels, js_datasets, annotations = collapse_gap_categories(
                labels, js_datasets, annotations
            )
        collapsed = bool(annotations) and any(
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
                x_ticks = "maxRotation: 45, minRotation: 45" if x_ticks_rotate else "maxRotation: 0"
                if collapsed:
                    x_ticks += ", callback: categoryTick"
                # each bar is its own category: a gridline per bar is only noise
                x_grid = ", grid: { display: false }" if chart_type == "bar" else ""
                x_scale_js = f"{{ ticks: {{ {x_ticks} }}{x_grid} }}"
            tooltip_callbacks = []
            if tooltip_share:
                tooltip_callbacks.append(
                    """label: function(item) {
          const total = item.dataset.data.reduce(function(a, b) { return a + b; }, 0) || 1;
          return item.parsed.y + ' commits (' + (100 * item.parsed.y / total).toFixed(1) + '%)';
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
        return f"""<div class="{box_class}" style="--chart-ratio: {aspect_ratio}"><canvas id="{chart_id}"></canvas></div>
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

    def print_footer(self, file: Any) -> None:
        """
        Write the HTML page footer with a "Generated by gitstats" link.

        Parameters:
            file: A writable file-like object opened in text mode.
        """
        file.write(
            '<div class="footer">'
            '<span class="footer-generated">Generated by '
            '<a href="https://github.com/shenxianpeng/gitstats" target="_blank" rel="noopener">gitstats</a>'
            "</span>"
            "</div>\n"
        )

    def print_header(self, file: Any, page: str = "index.html") -> None:
        """
        Write the HTML document header and opening body tag into the provided writable file.

        This writes the DOCTYPE, head section (title from self.title), the tags a link to ``page`` is previewed by where it is shared, a link to the configured stylesheet, a generator meta tag, an inclusion of sortable.js, an embedded client-side theme toggle script (init, toggle, and icon update handlers using localStorage), and the opening <body> tag.

        Parameters:
                file: A writable file-like object opened for text output where the HTML header will be written.
                page: The file name of the page, such as ``"authors.html"``.
        """
        label = dict(NAV_PAGES).get(page, "")
        title = self.title if page == "index.html" or not label else f"{self.title}: {label}"
        share = share_meta_html(
            title,
            getattr(self, "share_description", ""),
            self.site_url,
            page,
            "share-card.png" if load_config().get("share_card") else "",
        )
        file.write(
            """<!DOCTYPE html>
<html lang="en">
<head>
	<meta charset="UTF-8">
	<meta name="viewport" content="width=device-width, initial-scale=1.0">
	<title>GitStats - {}</title>
	{}
	<!-- Apply theme before CSS loads to prevent flash of unstyled content -->
	{}
	<link rel="stylesheet" href="{}" type="text/css">
	<meta name="generator" content="GitStats {}">
	<script type="text/javascript" src="sortable.js"></script>
	<script type="text/javascript" src="chart.umd.min.js"></script>
	{}
	{}
</head>
<body>
""".format(
                html.escape(self.title),
                share,
                THEME_INIT_SCRIPT,
                load_config()["style"],
                get_version(),
                THEME_SCRIPT,
                CHART_SCRIPT,
            )
        )

    def print_nav(self, file: Any, current: str | None = None) -> None:
        """
        Write the navigation bar HTML (page links and a client-side theme-toggle button) to the given writable file-like object.

        Parameters:
            file: A writable file-like object opened in text mode where the navigation HTML will be written.
            current: File name of the page being written (e.g. ``"authors.html"``); its link is marked as the current page.
        """
        # Check if AI insights are available
        has_ai = hasattr(self.data, "ai_summaries") and self.data.ai_summaries

        links = "\n            ".join(nav_link(href, label, current) for href, label in NAV_PAGES)
        ai_link = nav_link("ai-insights.html", "AI Insights", current) if has_ai else ""

        github_icon = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="20" height="20" '
            'fill="currentColor" aria-hidden="true">'
            '<path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 '
            "0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15"
            "-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07"
            "-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 "
            ".67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82"
            ".44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25"
            ".54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8"
            'c0-4.42-3.58-8-8-8z"/></svg>'
        )

        file.write(
            f"""
            <div class="nav">
            <a href="index.html" class="nav-brand">GitStats</a>
            <ul>
            {links}
            {ai_link}
            </ul>
            <div class="nav-right">
            <a href="https://github.com/shenxianpeng/gitstats" class="nav-github" target="_blank" rel="noopener" aria-label="GitHub">{github_icon}</a>
            {THEME_TOGGLE_BUTTON}
            </div>
            </div>
            """
        )

    def get_ai_summary_html(self, page_type: str) -> str:
        """
        Generate HTML for AI-powered summary section.

        Args:
            page_type: The type of page (index, activity, authors, lines)

        Returns:
            HTML string for the AI summary section
        """
        if not hasattr(self.data, "ai_summaries") or not self.data.ai_summaries:
            return ""

        summary_data = self.data.ai_summaries.get(page_type, {})
        summary_text = summary_data.get("summary", "")
        error = summary_data.get("error")

        if error:
            # Show error message with graceful degradation
            return f"""
            <div class="ai-summary ai-summary-error">
                <h3>AI Insights</h3>
                <p><em>AI analysis is currently unavailable: {error}</em></p>
            </div>
            """

        if not summary_text:
            return ""

        return f"""
        <div class="ai-summary">
            <h3>AI-Powered Insights</h3>
            <div class="ai-summary-content">
                {summary_text}
            </div>
        </div>
        """


def compute_code_ownership(author_files: dict[str, dict[str, int]]) -> dict[str, Any]:
    """Derive per-file ownership and per-author stats from author edit counts.

    Args:
        author_files: mapping of author -> file path -> number of commits that
            author made touching the file.

    Bot accounts (names ending in ``[bot]``) are excluded so ownership reflects
    human contributors. Returns a dict with:
        files:   per-file stats (path, edits, owner, owner_edits, ownership_pct,
                 contributors), sorted by edits descending;
        authors: per-author stats (author, files_owned, files_solely_owned,
                 files_touched), sorted by files owned then files touched;
        total_files, single_owner_files;
        bus_factor: the fewest authors who are, between them, primary owner
                 of more than half of the files (0 when there are no files),
                 with bus_factor_authors, their names, largest owner first,
                 and bus_factor_files, how many files they own.
    """
    # Invert to file -> {author: edits}, dropping bots.
    file_authors: dict[str, dict[str, int]] = {}
    for author, files in author_files.items():
        if is_bot(author):
            continue
        for filepath, count in files.items():
            file_authors.setdefault(filepath, {})[author] = count

    files_stats: list[dict[str, Any]] = []
    author_owned: dict[str, int] = {}
    author_solely: dict[str, int] = {}
    author_touched: dict[str, int] = {}
    for filepath, authors in file_authors.items():
        edits = sum(authors.values())
        # Primary owner: most edits; ties broken alphabetically for determinism.
        owner = max(zip(authors.values(), authors.keys()))[1]
        contributors = len(authors)
        files_stats.append(
            {
                "path": filepath,
                "edits": edits,
                "owner": owner,
                "owner_edits": authors[owner],
                "ownership_pct": round(100.0 * authors[owner] / edits, 1) if edits else 0.0,
                "contributors": contributors,
            }
        )
        author_owned[owner] = author_owned.get(owner, 0) + 1
        if contributors == 1:
            author_solely[owner] = author_solely.get(owner, 0) + 1
        for a in authors:
            author_touched[a] = author_touched.get(a, 0) + 1

    files_stats.sort(key=lambda x: x["edits"], reverse=True)

    authors_stats = [
        {
            "author": a,
            "files_owned": author_owned.get(a, 0),
            "files_solely_owned": author_solely.get(a, 0),
            "files_touched": author_touched[a],
        }
        for a in author_touched
    ]
    authors_stats.sort(key=lambda x: (x["files_owned"], x["files_touched"]), reverse=True)

    # Bus factor: take the largest owners until they hold more than half
    bus_authors: list[str] = []
    bus_files = 0
    for stats in authors_stats:
        if not files_stats or 2 * bus_files > len(files_stats):
            break
        author = str(stats["author"])
        bus_authors.append(author)
        bus_files += author_owned.get(author, 0)

    return {
        "files": files_stats,
        "authors": authors_stats,
        "total_files": len(files_stats),
        "single_owner_files": sum(1 for fs in files_stats if fs["contributors"] == 1),
        "bus_factor": len(bus_authors),
        "bus_factor_authors": bus_authors,
        "bus_factor_files": bus_files,
    }


def compute_hotspots(hotspot_files: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Derive the hotspot view from per-file size, churn and score.

    Args:
        hotspot_files: mapping of file path -> ``{"lines", "churn", "score"}``,
            where the score is ``churn * sqrt(lines)``.

    Only files with at least one line and one change can be placed on the
    (logarithmic) size and change axes, so the rest are left out. Returns a
    dict with:
        files:    per-file stats (path, lines, churn, score rounded to one
                  decimal), sorted by score descending;
        median_lines, median_churn: the upper medians over those files, which
                  split the plot into quadrants (0 when there are no files).
    """
    files = []
    for filepath, info in hotspot_files.items():
        lines = info.get("lines", 0)
        churn = info.get("churn", 0)
        if lines > 0 and churn > 0:
            files.append(
                {
                    "path": filepath,
                    "lines": lines,
                    "churn": churn,
                    "score": round(info.get("score", 0.0), 1),
                }
            )
    # ties broken by path for determinism
    files.sort(key=lambda fs: (-fs["score"], fs["path"]))

    if files:
        median_lines = statistics.median_high(fs["lines"] for fs in files)
        median_churn = statistics.median_high(fs["churn"] for fs in files)
    else:
        median_lines = median_churn = 0

    return {
        "files": files,
        "median_lines": median_lines,
        "median_churn": median_churn,
    }


def _classify_eras(year_commits: dict[int, int]) -> dict[int, str]:
    """Assign each year of the project's span one era label.

    Labels are relative to the repository's own baseline (the median of its
    non-zero years), so a "surge" in a small project and in a huge one mean
    the same thing: well above what is normal *for that project*. The span is
    contiguous — years without commits appear as "dormant" instead of being
    skipped, because silence is part of the story.

    Priority per year: birth > dormant > peak > revival > surge > quiet > steady.
    """
    if not year_commits:
        return {}
    first, last = min(year_commits), max(year_commits)
    span = {y: year_commits.get(y, 0) for y in range(first, last + 1)}
    active = [c for c in span.values() if c > 0]
    med = sorted(active)[len(active) // 2]
    peak_year = max(span, key=lambda y: (span[y], y))
    # With under three active years there is no meaningful baseline to
    # compare against, so only the structural labels apply.
    tiny = len(active) < 3

    eras: dict[int, str] = {}
    prev = ""
    for y in sorted(span):
        c = span[y]
        if y == first:
            era = "birth"
        elif c == 0:
            era = "dormant"
        elif y == peak_year and not tiny:
            era = "peak"
        elif prev in ("dormant", "quiet") and c >= med:
            era = "revival"
        elif not tiny and c >= 1.6 * med:
            era = "surge"
        elif not tiny and c <= 0.35 * med:
            era = "quiet"
        else:
            era = "steady"
        eras[y] = era
        prev = era
    return eras


def compute_project_history(data: Any) -> dict[str, Any]:
    """Derive a chronological, per-year account of the project from collected data.

    Everything here is computed from data the collector already gathered —
    no extra git traffic. Bot accounts (names ending in ``[bot]``) are left
    out of the people-facing fields. Returns a dict with:
        years: one entry per calendar year of the span (gap years included),
               each carrying commits, line deltas, author counts, the top
               author, newcomers (authors whose first commit fell in that
               year, most active first) and the releases tagged that year;
        first_year, last_year, peak_year, total_releases.
    """
    year_commits: dict[int, int] = dict(getattr(data, "commits_by_year", {}) or {})
    if not year_commits:
        return {
            "years": [],
            "first_year": None,
            "last_year": None,
            "peak_year": None,
            "total_releases": 0,
        }

    eras = _classify_eras(year_commits)
    author_of_year = getattr(data, "author_of_year", {}) or {}
    lines_added = getattr(data, "lines_added_by_year", {}) or {}
    lines_removed = getattr(data, "lines_removed_by_year", {}) or {}

    # Authors whose first commit fell in each year (bots excluded).
    newcomers_by_year: dict[int, list[str]] = {}
    for name, info in (getattr(data, "authors", {}) or {}).items():
        stamp = info.get("first_commit_stamp") if isinstance(info, dict) else None
        if not stamp or is_bot(name):
            continue
        yy = datetime.datetime.fromtimestamp(stamp).year
        newcomers_by_year.setdefault(yy, []).append(name)

    # Releases (tags) by the year they were made.
    releases_by_year: dict[int, list[tuple[str, str]]] = {}
    total_releases = 0
    for tag, info in (getattr(data, "tags", {}) or {}).items():
        date = str(info.get("date", ""))
        if len(date) >= 4 and date[:4].isdigit():
            releases_by_year.setdefault(int(date[:4]), []).append((date, tag))
            total_releases += 1

    total_commits = sum(year_commits.values())
    years: list[dict[str, Any]] = []
    for y in sorted(eras):
        commits = year_commits.get(y, 0)
        year_authors = author_of_year.get(y, {})
        humans = {a: c for a, c in year_authors.items() if not a.endswith("[bot]")}
        ranked = sorted(humans or year_authors, key=lambda a: (year_authors[a], a), reverse=True)
        top_author = ranked[0] if ranked else ""
        newcomers = sorted(
            newcomers_by_year.get(y, []),
            key=lambda a: (year_authors.get(a, 0), a),
            reverse=True,
        )
        years.append(
            {
                "year": y,
                "era": eras[y],
                "commits": commits,
                "commits_pct": round(100.0 * commits / total_commits, 1) if total_commits else 0.0,
                "lines_added": lines_added.get(y, 0),
                "lines_removed": lines_removed.get(y, 0),
                "active_authors": len(year_authors),
                "top_author": top_author,
                "top_author_commits": year_authors.get(top_author, 0),
                "newcomers": newcomers,
                "releases": [t for _, t in sorted(releases_by_year.get(y, []))],
            }
        )

    return {
        "years": years,
        "first_year": years[0]["year"],
        "last_year": years[-1]["year"],
        "peak_year": max(year_commits, key=lambda y: (year_commits[y], y)),
        "total_releases": total_releases,
    }


def parse_chronicle(text: str) -> dict[str, Any]:
    """Split AI chronicle text into a prologue and per-year chapters.

    Expects ``[PROLOGUE]`` and ``[YEAR <n>] <title>`` marker lines; everything
    between markers belongs to the preceding one. Tolerant by design: years
    the model skipped simply have no chapter, and text with no markers at all
    yields no chapters so the caller can fall back to showing it whole.
    """
    prologue = ""
    chapters: dict[int, dict[str, str]] = {}
    current: dict[str, str] | None = None
    in_prologue = False
    prologue_lines: list[str] = []
    marker = re.compile(r"^\[YEAR\s+(\d{4})\]\s*(.*)$")

    for raw_line in text.splitlines():
        line = raw_line.strip()
        m = marker.match(line)
        if m:
            in_prologue = False
            current = {"title": m.group(2).strip(), "story": ""}
            chapters[int(m.group(1))] = current
        elif line == "[PROLOGUE]":
            in_prologue = True
            current = None
        elif in_prologue:
            prologue_lines.append(line)
        elif current is not None and line:
            current["story"] = (current["story"] + " " + line).strip()

    prologue = " ".join(line for line in prologue_lines if line).strip()
    return {"prologue": prologue, "chapters": chapters}


def is_bot(name: str) -> bool:
    """Bot accounts are named like ``dependabot[bot]``."""
    return name.endswith("[bot]")


def head_ownership(data: Any) -> dict[str, Any]:
    """compute_code_ownership() over the files that still exist.

    A deleted file carries no bus-factor risk, so when the data knows the
    files at HEAD only those are counted.
    """
    author_files = getattr(data, "author_files", {})
    if not isinstance(author_files, dict):
        author_files = {}
    current = head_files(data)
    if current is not None:
        author_files = {
            author: {p: n for p, n in files.items() if p in current}
            for author, files in author_files.items()
        }
    return compute_code_ownership(author_files)


def head_files(data: Any) -> set[str] | None:
    """Paths of the files at HEAD, or None when the data predates head_files."""
    paths = getattr(data, "head_files", None)
    if isinstance(paths, (list, tuple, set)) and paths:
        return set(paths)
    return None


def author_html(name: str) -> str:
    """An author's name, HTML-escaped; a bot account shows a BOT badge in place
    of its "[bot]" suffix, with the full name kept as the badge's tooltip."""
    if not is_bot(name):
        return html.escape(name)
    return (
        f"{html.escape(name[: -len('[bot]')])} "
        f'<span class="badge" title="{html.escape(name)}">bot</span>'
    )


def longest_zero_run(values: list[int]) -> tuple[int, int] | None:
    """Index range (inclusive) of the longest run of zeros, or None if there is none."""
    best: tuple[int, int] | None = None
    start: int | None = None
    for i, value in enumerate(values):
        if value:
            start = None
            continue
        if start is None:
            start = i
        if best is None or i - start > best[1] - best[0]:
            best = (start, i)
    return best


def gap_annotations(labels: list[Any], values: list[int], min_gap: int) -> dict[str, Any]:
    """Chart annotations for the longest stretch without commits.

    When the longest run of empty buckets is at least ``min_gap`` long, it is
    shaded ("No commits 2016 – 2023") and the busiest bucket on each side of
    it is labelled ("2007 · 107"). Otherwise there is nothing to annotate.
    """
    gap = longest_zero_run(values)
    if gap is None or gap[1] - gap[0] + 1 < min_gap:
        return {}
    start, end = gap
    peaks = []
    for lo, hi in ((0, start), (end + 1, len(values))):
        segment = values[lo:hi]
        if segment and max(segment) > 0:
            i = lo + segment.index(max(segment))
            peaks.append({"index": i, "text": f"{labels[i]} \u00b7 {values[i]}"})
    return {
        "bands": [
            {
                "from": start,
                "to": end,
                "text": f"No commits {labels[start]} \u2013 {labels[end]}",
                "short": "no commits",
            }
        ],
        "peaks": peaks,
    }


# A stretch without commits that takes up at least this share of a time axis
# is cut out of it, and drawn as a break this share of what is left of the
# axis wide. Under the first, a stretch is only shaded and keeps its width.
GAP_COLLAPSE_MIN_SHARE = 0.25
GAP_BREAK_SHARE = 0.05


def collapsed_width(total: float, gap: float) -> float | None:
    """How wide a quiet stretch ``gap`` long is drawn on an axis ``total`` long.

    None when it is left alone: it covers less than GAP_COLLAPSE_MIN_SHARE
    of the axis, so the years around it are not short of room. Otherwise
    GAP_BREAK_SHARE of the rest of the axis, in the units of ``total``: a
    repository silent for nine of its twenty years gives those nine the
    width of half a year, and the eleven with commits almost all of the plot.
    """
    if total <= 0 or gap < GAP_COLLAPSE_MIN_SHARE * total:
        return None
    return GAP_BREAK_SHARE * (total - gap)


def collapsed_slots(total: int, gap: int) -> int | None:
    """collapsed_width() for an axis of categories: whole slots, at least one.

    None too when the stretch is no longer than the slots it would be given.
    """
    width = collapsed_width(total, gap)
    if width is None:
        return None
    slots = max(1, round(width))
    return slots if gap > slots else None


def year_span(first: Any, last: Any) -> str:
    """The years from ``first`` to ``last`` as a short axis label: "2016\u201324".

    Each is a year or anything that starts with one, such as "2016-01".
    """
    a, b = str(first)[:4], str(last)[:4]
    if a == b:
        return a
    return f"{a}\u2013{b[2:] if a[:2] == b[:2] else b}"


def collapse_gap_categories(
    labels: list[Any], datasets: list[dict[str, Any]], annotations: dict[str, Any]
) -> tuple[list[Any], list[dict[str, Any]], dict[str, Any]]:
    """Cut a long shaded stretch out of a category axis.

    When the one band in ``annotations`` is long enough (collapsed_slots()),
    its categories are replaced by a few slots named after the whole stretch
    ("2016 \u2013 2023"), which keep the values the stretch began with: zeros
    on a bar chart, the level a cumulative line stays at. The band is narrowed
    to those slots and flagged ``collapsed``, with the ``axis`` label the
    chart draws under it, and the peaks after it move up. Everything is
    returned unchanged when there is nothing to collapse.
    """
    bands = annotations.get("bands") or []
    if len(bands) != 1:
        return labels, datasets, annotations
    band = bands[0]
    start, end = band["from"], band["to"]
    gap = end - start + 1
    slots = collapsed_slots(len(labels), gap)
    if slots is None:
        return labels, datasets, annotations
    cut = gap - slots

    name = f"{labels[start]} \u2013 {labels[end]}"
    new_labels = [*labels[:start], *([name] * slots), *labels[end + 1 :]]
    new_datasets = []
    for dataset in datasets:
        entry = dict(dataset)
        for key in ("data", "notes"):
            if isinstance(entry.get(key), list):
                entry[key] = entry[key][: start + slots] + entry[key][end + 1 :]
        new_datasets.append(entry)
    new_annotations = {
        **annotations,
        "bands": [
            {
                **band,
                "to": start + slots - 1,
                "collapsed": True,
                "axis": year_span(labels[start], labels[end]),
            }
        ],
    }
    if "peaks" in annotations:
        new_annotations["peaks"] = [
            {**peak, "index": peak["index"] - cut} if peak["index"] > end else peak
            for peak in annotations["peaks"]
        ]
    return new_labels, new_datasets, new_annotations


def collapse_gap_time(
    stamps: list[int], annotations: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, int] | None]:
    """Cut a long shaded stretch out of a time axis.

    ``stamps`` are the chart's x values in milliseconds, in order. When the
    one band in ``annotations`` is long enough (collapsed_width()), returns
    the annotations with that band narrowed to the break and flagged
    ``collapsed``, and the gap ``{"from", "to", "width"}`` the chart's
    squeezeTime() needs. Otherwise the annotations as they were, and None.
    """
    bands = annotations.get("bands") or []
    if len(bands) != 1 or len(stamps) < 2:
        return annotations, None
    band = bands[0]
    if band["from"] < stamps[0] or band["to"] > stamps[-1]:
        return annotations, None  # not a stretch between two of the chart's points
    width = collapsed_width(stamps[-1] - stamps[0], band["to"] - band["from"])
    if width is None:
        return annotations, None
    gap = {"from": band["from"], "to": band["to"], "width": round(width)}
    first = datetime.datetime.fromtimestamp(band["from"] / 1000)
    # the band ends on the first day after its last quiet month
    last = datetime.datetime.fromtimestamp(band["to"] / 1000) - datetime.timedelta(days=1)
    collapsed = {
        **band,
        "to": band["from"] + gap["width"],
        "collapsed": True,
        "axis": year_span(first.year, last.year),
    }
    return {**annotations, "bands": [collapsed]}, gap


def quiet_months(data: Any, min_months: int = 12) -> tuple[str, str] | None:
    """First and last "YYYY-MM" of the longest stretch without commits, when it
    lasts at least ``min_months`` (the monthly chart's threshold), else None."""
    by_month = getattr(data, "commits_by_month", None)
    if not isinstance(by_month, dict) or not by_month:
        return None
    months = month_range(by_month)
    gap = longest_zero_run([by_month.get(m, 0) for m in months])
    if gap is None or gap[1] - gap[0] + 1 < min_months:
        return None
    return months[gap[0]], months[gap[1]]


def quiet_band(first: str, last: str, start: Any, end: Any) -> dict[str, Any]:
    """A gsAnnotations band from ``start`` to ``end`` captioned with the quiet months."""
    return {
        "from": start,
        "to": end,
        "text": f"No commits {first} \u2013 {last}",
        "short": "no commits",
    }


def time_gap_annotations(data: Any) -> dict[str, Any]:
    """Annotations for a time-axis chart: the longest stretch without commits,
    shaded from its first month's first day to the day after its last month
    (timestamps in milliseconds, like the chart's x values)."""
    quiet = quiet_months(data)
    if quiet is None:
        return {}
    first, last = quiet
    year, month = map(int, first.split("-"))
    start = datetime.datetime(year, month, 1)
    year, month = map(int, last.split("-"))
    end = datetime.datetime(year + month // 12, month % 12 + 1, 1)
    return {
        "bands": [
            quiet_band(first, last, int(start.timestamp() * 1000), int(end.timestamp() * 1000))
        ]
    }


def month_range(months: Any) -> list[str]:
    """Return every ``"YYYY-MM"`` month from the earliest to the latest in ``months``.

    Monthly charts use a category axis, so months without commits must be
    present (as zeros) or a long quiet period collapses to nothing.
    """
    keys = sorted(months)
    if not keys:
        return []
    year, month = map(int, keys[0].split("-"))
    last = tuple(map(int, keys[-1].split("-")))
    result = []
    while (year, month) <= last:
        result.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return result


# What makes a commit AI-assisted, folded under the numbers that count them
AI_ASSISTED_COUNTED = (
    '<details class="table-details"><summary>What is counted</summary>'
    "<ul>"
    "<li>The author is an assistant's own account, such as the Copilot coding agent, "
    "Devin or Cursor's agent.</li>"
    "<li>A <code>Co-authored-by:</code> line names an assistant, as Claude Code, "
    "Copilot, Cursor, Codex, Aider and others add when they commit for a person. A "
    "review bot whose suggestion was applied is named the same way.</li>"
    "<li>An <code>Assisted-by:</code> or <code>Generated-by:</code> line names an "
    "assistant.</li>"
    "<li>The message has the line an assistant leaves in it, such as "
    "&ldquo;Generated with [Claude Code]&rdquo; or the link to a Devin or Codex "
    "session.</li>"
    "</ul>"
    "<p>Accounts and addresses are matched, not first names: a person called Claude, "
    "Devin or Jules is not an assistant.</p>"
    "</details>"
)


# A share card is what a link shows where it is posted, at the size those
# places ask for. gitstats writes it as an HTML page; the pages point to it as
# an image (share-card.png) when the report is published with share_card on.
SHARE_CARD_WIDTH = 1200
SHARE_CARD_HEIGHT = 630
_CARD_MONO = 'ui-monospace, SFMono-Regular, Menlo, "DejaVu Sans Mono", monospace'
SHARE_CARD_CSS = f"""
*{{box-sizing:border-box}}
html,body{{margin:0}}
body{{width:{SHARE_CARD_WIDTH}px;height:{SHARE_CARD_HEIGHT}px;background:#ffffff;color:#211e1e;
font:24px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI","DejaVu Sans",sans-serif}}
main{{height:{SHARE_CARD_HEIGHT}px;padding:54px 64px 44px;display:flex;flex-direction:column}}
.brand{{font:600 22px {_CARD_MONO};color:#716b6b;letter-spacing:.04em}}
h1{{font:700 72px/1.1 {_CARD_MONO};margin:14px 0 8px;white-space:nowrap;overflow:hidden;
text-overflow:ellipsis}}
.sub{{margin:0 0 30px;color:#716b6b}}
.tiles{{display:grid;grid-template-columns:repeat(4,1fr);margin:0;border:2px solid #cfcecd}}
.tiles div{{padding:16px 22px;border-left:2px solid #cfcecd}}
.tiles div:first-child{{border-left:0}}
.tiles dt{{font:15px {_CARD_MONO};letter-spacing:.08em;text-transform:uppercase;color:#716b6b}}
.tiles dd{{margin:6px 0 0;font:700 40px {_CARD_MONO};white-space:nowrap}}
.note{{margin:20px 0 0}}
.names{{margin:8px 0 0;font:600 30px/1.5 {_CARD_MONO};display:-webkit-box;-webkit-line-clamp:5;
-webkit-box-orient:vertical;overflow:hidden}}
.history{{margin:26px 0 0}}
.history .columns{{display:flex;align-items:flex-end;gap:2px;height:88px}}
.history i{{flex:1;background:#4a7ab5;border-radius:2px 2px 0 0;min-height:1px}}
.history .axis{{display:flex;justify-content:space-between;margin-top:6px;color:#716b6b;
font:16px {_CARD_MONO}}}
.bars{{display:grid;gap:12px;margin:4px 0 0}}
.bars div{{display:grid;grid-template-columns:240px 1fr 120px;align-items:center;gap:18px}}
.bars b{{font:600 26px {_CARD_MONO};white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.bars i{{display:block;height:26px;background:#4a7ab5;border-radius:0 4px 4px 0}}
.bars span{{font:700 28px {_CARD_MONO};text-align:right}}
footer{{margin-top:auto;display:flex;justify-content:space-between;color:#716b6b;
font:20px {_CARD_MONO}}}
"""


def share_meta_html(title: str, description: str, site_url: str, page: str, image: str) -> str:
    """The tags a page is previewed by where a link to it is shared (Open
    Graph, and X's own). ``image`` is the card's file name next to the page,
    or "" for none; places that show a link want absolute addresses, so
    without ``site_url`` there is neither an address nor an image."""
    tags = [
        ("name", "description", description),
        ("property", "og:type", "website"),
        ("property", "og:site_name", "GitStats"),
        ("property", "og:title", title),
        ("property", "og:description", description),
    ]
    picture = site_url + image if site_url and image else ""
    if site_url:
        tags.append(("property", "og:url", site_url + ("" if page == "index.html" else page)))
    if picture:
        tags += [
            ("property", "og:image", picture),
            ("property", "og:image:width", str(SHARE_CARD_WIDTH)),
            ("property", "og:image:height", str(SHARE_CARD_HEIGHT)),
            ("property", "og:image:alt", title),
        ]
    tags.append(("name", "twitter:card", "summary_large_image" if picture else "summary"))
    tags += [("name", "twitter:title", title), ("name", "twitter:description", description)]
    if picture:
        tags.append(("name", "twitter:image", picture))
    return "\n\t".join(
        f'<meta {attribute}="{key}" content="{html.escape(value, quote=True)}">'
        for attribute, key, value in tags
        if value
    )


def share_card_page(title: str, body: str, footer: str = "made with gitstats") -> str:
    """A share card: ``body`` on a page of the card's size, with the footer
    every card has."""
    return (
        f'<!DOCTYPE html>\n<html lang="en"><head><meta charset="UTF-8">'
        f"<title>{html.escape(title)}</title><style>{SHARE_CARD_CSS}</style></head>"
        f"<body><main>{body}<footer><span>{footer}</span>"
        "<span>github.com/shenxianpeng/gitstats</span></footer></main></body></html>\n"
    )


def _last_twelve_months(data: Any) -> tuple[int, int]:
    """(commits that name an AI coding assistant, all commits) in the twelve
    months that end with the last commit."""
    by_month = getattr(data, "commits_by_month", None)
    if not isinstance(by_month, dict) or not by_month:
        return 0, 0
    since = months_back(max(by_month), 11)
    assisted = getattr(data, "ai_assisted_by_month", None)
    return (
        sum_since(assisted, since) if isinstance(assisted, dict) else 0,
        sum_since(by_month, since),
    )


def report_share_description(data: Any) -> str:
    """One sentence about the repository, for the pages' share tags."""
    commits, authors = data.get_total_commits(), data.get_total_authors()
    first, last = data.get_first_commit_date(), data.get_last_commit_date()
    text = (
        f"{data.project_name}: {format_int(commits)} commit{'' if commits == 1 else 's'} by "
        f"{format_int(authors)} author{'' if authors == 1 else 's'}"
    )
    if isinstance(first, datetime.datetime) and isinstance(last, datetime.datetime):
        text += f", {first.year}" + (f" to {last.year}" if last.year != first.year else "")
    return text + ". A report made with gitstats."


def report_share_card_html(data: Any) -> str:
    """The report's share card: the repository, its years, four numbers, and
    the share of its recent commits that name an AI coding assistant."""
    first, last = data.get_first_commit_date(), data.get_last_commit_date()
    span = ""
    if isinstance(first, datetime.datetime) and isinstance(last, datetime.datetime):
        span = f"{first.strftime('%Y-%m-%d')} &rarr; {last.strftime('%Y-%m-%d')}"
    tiles = "".join(
        f"<div><dt>{label}</dt><dd>{format_int(value)}</dd></div>"
        for label, value in (
            ("Commits", data.get_total_commits()),
            ("Authors", data.get_total_authors()),
            ("Lines of code", data.get_total_loc()),
            ("Files", data.get_total_files()),
        )
    )
    history = _share_card_history(data)
    assisted, recent = _last_twelve_months(data)
    note = (
        f'<p class="note"><strong>{share_text(assisted, recent)}</strong> of the commits of the '
        "last 12 months name an AI coding assistant.</p>"
        if assisted
        else ""
    )
    name = html.escape(data.project_name)
    return share_card_page(
        f"{data.project_name}: GitStats",
        f'<div class="brand">// GitStats report</div><h1>{name}</h1>'
        f'<p class="sub">{span}</p><dl class="tiles">{tiles}</dl>{history}{note}',
    )


def _share_card_history(data: Any) -> str:
    """Commits per year as a row of columns, or per month for a history of
    less than three years; nothing without commits to show."""
    by_year = getattr(data, "commits_by_year", None)
    by_month = getattr(data, "commits_by_month", None)
    if isinstance(by_year, dict) and by_year and max(by_year) - min(by_year) >= 2:
        keys: list[Any] = list(range(min(by_year), max(by_year) + 1))
        counts, unit = [int(by_year.get(year, 0)) for year in keys], "year"
    elif isinstance(by_month, dict) and by_month:
        keys = month_range(by_month)
        counts, unit = [int(by_month.get(month, 0)) for month in keys], "month"
    else:
        return ""
    top = max(counts) or 1
    columns = "".join(f'<i style="height:{100 * count / top:.1f}%"></i>' for count in counts)
    return (
        f'<div class="history"><div class="columns">{columns}</div><div class="axis">'
        f"<span>{keys[0]}</span><span>commits per {unit}</span><span>{keys[-1]}</span>"
        "</div></div>"
    )


def ai_assisted_count(data: Any) -> int:
    """How many commits name an AI coding assistant; none for data collected
    before that was counted."""
    count = getattr(data, "ai_assisted_commits", 0)
    return count if isinstance(count, int) else 0


def months_back(month: str, count: int) -> str:
    """The "YYYY-MM" month ``count`` months before ``month``."""
    year, number = map(int, month.split("-"))
    year, number = divmod(year * 12 + number - 1 - count, 12)
    return f"{year:04d}-{number + 1:02d}"


def sum_since(by_month: dict[str, int], month: str) -> int:
    """What ``by_month`` ("YYYY-MM" -> count) adds up to from ``month`` on."""
    return sum(count for key, count in by_month.items() if key >= month)


def share_text(part: int, whole: int) -> str:
    """``part`` as a percentage of ``whole``, to one decimal; a share too small
    to show that way is "&lt;0.1%", not "0.0%"."""
    if not part or not whole:
        return "0%"
    share = 100.0 * part / whole
    return "&lt;0.1%" if share < 0.05 else f"{share:.1f}%"


def stat_tiles_html(tiles: list[tuple[str, str, str]]) -> str:
    """Render headline numbers as a grid of stat tiles (KPI cards).

    Each tile is ``(label, value, note)``; ``value`` and ``note`` are inserted
    as HTML, so callers escape any user-controlled text. An empty note is
    left out.

    Wide, medium (<=1024px) and narrow (<=560px) screens get up to 6, 3 and
    2 columns: the largest divisor of the tile count when that gives at least
    two columns (6 tiles -> 6/3/2, 4 -> 4/2/2), otherwise as many columns as
    fit with the last tile spanning the rest of its row (3 tiles on a phone:
    two, then one full width) instead of stacking one per row.
    """

    def columns(limit: int) -> tuple[int, int]:
        """(columns, span of the last tile) for up to ``limit`` columns."""
        n = max(len(tiles), 1)
        cols = next(c for c in range(min(n, limit), 0, -1) if n % c == 0)
        if cols > 1 or n == 1:
            return cols, 1
        cols = min(n, limit)
        return cols, cols - n % cols + 1 if n % cols else 1

    def phrases(note: str) -> str:
        # a note wraps after a " · " between its phrases, never inside one ("per active / day")
        parts = note.split(" &middot; ")
        if len(parts) == 1:
            return note
        return "&nbsp;&middot; ".join(f'<span class="nowrap">{part}</span>' for part in parts)

    items = "".join(
        '<div class="stat-tile">'
        f"<dt>{label}</dt>"
        f'<dd class="stat-value">{value}</dd>'
        + (f'<dd class="stat-note">{phrases(note)}</dd>' if note else "")
        + "</div>"
        for label, value, note in tiles
    )
    style = "; ".join(
        f"--cols{suffix}: {cols}" + (f"; --span{suffix}: {span}" if span > 1 else "")
        for suffix, (cols, span) in (("", columns(6)), ("-md", columns(3)), ("-sm", columns(2)))
    )
    return f'<dl class="stat-tiles" style="{style}">{items}</dl>'


def html_header(level: int, text: str) -> str:
    name = html_linkify(text)
    return '\n<h%d id="%s"><a href="#%s">%s</a></h%d>\n\n' % (
        level,
        name,
        name,
        text,
        level,
    )


def html_linkify(text: str) -> str:
    return text.lower().replace(" ", "_")


def get_keys_sorted_by_values(d: dict[str, int]) -> list[str]:
    return [el[1] for el in sorted([(el[1], el[0]) for el in d.items()])]


# dict['author'] = { 'commits': 512 } - ...key(dict, 'commits')
def get_keys_sorted_by_value_key(d: dict[str, dict[str, Any]], key: str) -> list[str]:
    return [el[1] for el in sorted([(d[el][key], el) for el in d.keys()])]
