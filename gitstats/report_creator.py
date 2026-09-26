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
import time
from typing import Any

from gitstats import WEEKDAYS, get_i18n_text, load_config
from gitstats.badge import create_badges
from gitstats.utils import (
    format_bytes,
    format_duration,
    format_int,
    get_git_version,
    get_version,
)

# A table with its chart beside it; the chart wraps below on narrow screens.
_FLEX_CONTAINER = '<div class="table-with-chart">'
_FLEX_CHILD = '<div class="chart-pane">'
_FLEX_CLOSE = "</div></div>"

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
	// Colors are read from CSS at draw time, so they follow the theme.
	const chartAnnotations = {
		id: 'gsAnnotations',
		beforeDatasetsDraw: function(chart, args, opts) {
			const x = chart.scales.x, area = chart.chartArea, ctx = chart.ctx;
			const half = x.type === 'category' && chart.data.labels.length > 1
				? (x.getPixelForValue(1) - x.getPixelForValue(0)) / 2 : 0;
			(opts.bands || []).forEach(function(band) {
				const left = x.getPixelForValue(band.from) - half;
				const right = x.getPixelForValue(band.to) + half;
				ctx.save();
				ctx.fillStyle = getCSSVar('--surface-color');
				ctx.fillRect(left, area.top, right - left, area.bottom - area.top);
				ctx.strokeStyle = getCSSVar('--border-strong');
				ctx.setLineDash([3, 3]);
				ctx.beginPath();
				ctx.moveTo(left, area.top); ctx.lineTo(left, area.bottom);
				ctx.moveTo(right, area.top); ctx.lineTo(right, area.bottom);
				ctx.stroke();
				ctx.fillStyle = getCSSVar('--chart-text');
				ctx.font = '11px ' + getCSSVar('--font-mono');
				ctx.textAlign = 'center';
				let text = band.text;
				if (ctx.measureText(text).width > right - left - 8) text = band.short || '';
				if (ctx.measureText(text).width <= right - left - 4) {
					ctx.fillText(text, (left + right) / 2, area.top + (area.bottom - area.top) / 2);
				}
				ctx.restore();
			});
		},
		afterDatasetsDraw: function(chart, args, opts) {
			const meta = chart.getDatasetMeta(0), ctx = chart.ctx, area = chart.chartArea;
			const marks = (opts.peaks || []).slice();
			if (opts.values) {
				chart.data.datasets[0].data.forEach(function(v, i) {
					if (v) marks.push({ index: i, text: String(v), plain: true });
				});
			}
			marks.forEach(function(mark) {
				const bar = meta.data[mark.index];
				if (!bar) return;
				ctx.save();
				ctx.fillStyle = getCSSVar(mark.plain ? '--chart-text' : '--text-color');
				ctx.font = (mark.plain ? '' : '600 ') + '11px ' + getCSSVar('--font-mono');
				ctx.textAlign = 'center';
				// keep labels on the first and last bars inside the plot area
				const w = ctx.measureText(mark.text).width / 2;
				const cx = Math.min(Math.max(bar.x, area.left + w), area.right - w);
				ctx.fillText(mark.text, cx, bar.y - 6);
				ctx.restore();
			});
		}
	};

	// Ticks for a category axis of "YYYY-MM" months: the year at each January,
	// thinned so labels never collide; short spans label every few months.
	function monthAxisTick(value) {
		const label = this.getLabelForValue(value);
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

	// A linear x-axis over millisecond timestamps, ticked on year (or month)
	// boundaries, so gaps in history take up the space they really span.
	function timeAxis(xs) {
		return {
			type: 'linear',
			min: xs.length ? xs[0] : undefined,
			max: xs.length ? xs[xs.length - 1] : undefined,
			afterBuildTicks: function(scale) {
				const from = new Date(scale.min), to = new Date(scale.max);
				const ticks = [];
				let unit = 'year';
				if (to.getFullYear() - from.getFullYear() >= 2) {
					for (let y = from.getFullYear() + 1; y <= to.getFullYear(); y++) {
						ticks.push({ value: new Date(y, 0, 1).getTime() });
					}
				} else {
					unit = 'month';
					const d = new Date(from.getFullYear(), from.getMonth() + 1, 1);
					for (; d.getTime() <= scale.max; d.setMonth(d.getMonth() + 1)) {
						ticks.push({ value: d.getTime() });
					}
				}
				scale.dateUnit = ticks.length >= 2 ? unit : 'day';
				if (ticks.length >= 2) scale.ticks = ticks;
			},
			ticks: {
				maxRotation: 0,
				autoSkipPadding: 12,
				callback: function(value) { return formatChartDate(value, this.dateUnit); }
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

NAV_PAGES = (
    ("index.html", "General"),
    ("activity.html", "Activity"),
    ("authors.html", "Authors"),
    ("files.html", "Files"),
    ("lines.html", "Lines"),
    ("tags.html", "Tags"),
    ("ownership.html", "Code Ownership"),
    ("history.html", "History"),
)


def nav_link(href: str, label: str, current: str | None = None) -> str:
    """Return a nav ``<li>``, marking it as the current page when ``href == current``."""
    if href == current:
        return f'<li><a href="{href}" class="active" aria-current="page">{label}</a></li>'
    return f'<li><a href="{href}">{label}</a></li>'


class ReportCreator:
    """Creates the actual report based on given data."""

    def __init__(self):
        self.data = None
        self.path = None

    def create(self, data, path):
        self.data = data
        self.path = path


class HTMLReportCreator(ReportCreator):
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

        self.create_index_html(data, path)
        self.create_activity_html(data, path)
        self.create_authors_html(data, path)
        self.create_files_html(data, path)
        self.create_lines_html(data, path)
        self.create_tags_html(data, path)
        self.create_ownership_html(data, path)
        self.create_history_html(data, path)

        # Create AI Insights page if AI is enabled
        if hasattr(data, "ai_summaries") and data.ai_summaries:
            self.create_ai_insights_html(data, path)

    def create_index_html(self, data: Any, path: str) -> None:
        f = open(path + "/index.html", "w", encoding="utf-8")
        format = "%Y-%m-%d %H:%M:%S"
        self.print_header(f)

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
            "</p>"
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
        latest = sorted(data.tags, key=lambda t: (data.tags[t]["date"], t), reverse=True)[:5]
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
        self.print_header(f)
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
        """A one-line summary of the page's numbers, then links to its sections."""
        full_days = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
        streak = data.get_longest_streak()
        hours = data.get_activity_by_hour_of_day()
        days = data.get_activity_by_day_of_week()
        parts = [
            f"{format_int(data.get_total_commits())} commits",
            f"{format_int(len(data.get_active_days()))} active days",
            f"longest streak {streak} day{'' if streak == 1 else 's'}",
        ]
        if hours:
            parts.append(f"busiest hour {max(hours, key=lambda h: (hours[h], -h)):02d}:00")
        if days:
            parts.append(f"busiest day {full_days[max(days, key=lambda d: (days[d], -d))]}")
        f.write('<p class="page-meta">' + " &middot; ".join(parts) + "</p>")
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
        """Write commits by year section with table and chart.

        It also carries the anchor of the former Yearly activity section, whose
        chart showed the same numbers.
        """
        f.write('<span id="yearly_activity"></span>')
        f.write(html_header(2, "Commits by year"))
        f.write(_FLEX_CONTAINER)
        f.write(
            '<div class="table-scroll"><table><tr><th>Year</th><th class="num">Commits (% of all)</th><th class="num">Lines added</th><th class="num">Lines removed</th></tr>'
        )
        total = data.get_total_commits()
        for yy in sorted(data.commits_by_year.keys(), reverse=True):
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
        f.write("</table></div>")
        if data.commits_by_year:
            cby_all_years = list(
                range(
                    min(data.commits_by_year.keys()),
                    max(data.commits_by_year.keys()) + 1,
                )
            )
        else:
            cby_all_years = []
        cby_values = [data.commits_by_year.get(y, 0) for y in cby_all_years]
        f.write(_FLEX_CHILD)
        f.write(
            self._render_chartjs(
                "chart-commits-by-year",
                "bar",
                cby_all_years,
                [{"label": "Commits", "data": cby_values}],
                annotations=gap_annotations(cby_all_years, cby_values, min_gap=2),
            )
        )
        f.write(_FLEX_CLOSE)

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

    def _contributor_timeline_html(self, data: Any, authors: list[str]) -> str:
        """One row per author on a shared, real time axis.

        A square marks each month with commits (bigger = more commits) and a thin
        line runs from the author's first to last active month, so who was
        active when, and for how long, reads at a glance. Plain HTML/CSS: it
        follows the theme without any script.
        """
        months = month_range(data.author_of_month.keys())
        if not months or not authors:
            return ""
        index = {month: i for i, month in enumerate(months)}
        n = len(months)

        def left(i: float) -> str:
            return f"{100.0 * i / n:.3f}%"

        per_author: dict[str, dict[str, int]] = {a: {} for a in authors}
        for month, counts in data.author_of_month.items():
            for author, commits in counts.items():
                if author in per_author:
                    per_author[author][month] = commits

        # Year boundaries as gridlines; label every year, or every 2nd/5th on long histories
        first_year, last_year = int(months[0][:4]), int(months[-1][:4])
        span = last_year - first_year + 1
        every = 1 if span <= 12 else 2 if span <= 24 else 5
        grid = []
        for year in range(first_year + 1, last_year + 1):
            pos = left(index[f"{year}-01"])
            label = str(year) if year % every == 0 else ""
            grid.append(f'<span class="timeline-year" style="left: {pos}">{label}</span>')

        rows = []
        for author in authors:
            active = sorted(per_author[author])
            name = html.escape(author)
            commits = data.get_author_info(author)["commits"]
            if active:
                start, end = index[active[0]], index[active[-1]]
                marks = [
                    f'<span class="timeline-span" style="left: {left(start + 0.5)}; '
                    f'width: {left(end - start)}"></span>'
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
            "One row per author: a square marks each month with commits (bigger means "
            "more), and the line runs from their first to their last active month. "
            "Bot accounts are grey.</p>"
            '<div class="timeline-scroll"><div class="timeline">'
            f'<div class="timeline-grid" aria-hidden="true">{"".join(grid)}</div>'
            + "".join(rows)
            + f'<div class="timeline-axis" aria-hidden="true">{ends}</div>'
            "</div></div>"
        )

    def _authors_summary_html(self, data: Any) -> str:
        """One line under the Authors heading: how many, how concentrated, how many bots."""
        everyone = data.get_authors()
        parts = [f"{format_int(len(everyone))} author{'' if len(everyone) == 1 else 's'}"]
        top = everyone[:2]
        if top:
            share = sum(data.get_author_info(a)["commits_frac"] for a in top)
            who = "top author" if len(top) == 1 else "top 2"
            parts.append(f"{who} wrote {share:.1f}% of commits")
        bots = sum(1 for a in everyone if is_bot(a))
        if bots:
            parts.append(f"{bots} bot account{'' if bots == 1 else 's'}")
        return '<p class="page-meta">' + " &middot; ".join(parts) + "</p>"

    def create_authors_html(self, data: Any, path: str) -> None:
        ###
        # Authors
        f = open(path + "/authors.html", "w", encoding="utf-8")
        self.print_header(f)

        self.print_nav(f, "authors.html")
        f.write("<h1>Authors</h1>")
        f.write(self._authors_summary_html(data))

        # Authors :: List of authors
        f.write(html_header(2, "List of authors"))

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

        allauthors = data.get_authors()
        if len(allauthors) > load_config()["max_authors"]:
            rest = allauthors[load_config()["max_authors"] :]
            max_list = load_config()["max_authors_list"]
            if len(rest) > max_list:
                shown = ", ".join(author_html(a) for a in rest[:max_list])
                more = len(rest) - max_list
                f.write(
                    f'<p class="moreauthors">These didn\'t make it to the top:'
                    f" {shown}<em>, and {more} more authors</em></p>"
                )
            else:
                f.write(
                    '<p class="moreauthors">These didn\'t make it to the top: {}</p>'.format(
                        ", ".join(author_html(a) for a in rest)
                    )
                )

        # Build per-author time series data for Chart.js
        time_labels, loc_datasets = self._build_author_time_series(data)

        f.write(html_header(2, "Cumulated added lines of code per author"))
        f.write(
            self._render_chartjs(
                "chart-loc-by-author",
                "line",
                time_labels,
                loc_datasets,
                time_axis=True,
                highlight=5,
            )
        )
        note = "The top 5 authors are in color, the others in grey."
        if len(allauthors) > load_config()["max_authors"]:
            note += " Only the top %d authors are shown." % load_config()["max_authors"]
        f.write(f'<p class="moreauthors">{note}</p>')

        # Replaces the former "Commits per Author" line chart; its anchor still lands here
        f.write('<span id="commits_per_author"></span>')
        f.write(html_header(2, "Contributor timeline"))
        f.write(
            self._contributor_timeline_html(data, data.get_authors(load_config()["max_authors"]))
        )
        if len(allauthors) > load_config()["max_authors"]:
            f.write(
                '<p class="moreauthors">Only top %d authors shown</p>'
                % load_config()["max_authors"]
            )

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

        # Domains: a bar table (the numbers used to be shown twice, as a table and a chart)
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
            f.write(
                self._render_chartjs(
                    "chart-contributor-growth",
                    "line",
                    growth_months,
                    [{"label": "Contributors", "data": totals, "stepped": True, "notes": notes}],
                    month_axis=True,
                    aspect_ratio=4,
                )
            )

        self.print_footer(f)
        f.write("</body></html>")
        f.close()

    def create_files_html(self, data: Any, path: str) -> None:
        ###
        # Files
        f = open(path + "/files.html", "w", encoding="utf-8")
        self.print_header(f)
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
                f'<td class="num">{format_int(count)}</td>'
                '<td class="share-cell"><span class="share-bar" aria-hidden="true">'
                f'<span style="width: {100.0 * count / max_churn:.1f}%"></span></span></td></tr>'
                for filepath, count in top_churn
            ]
            f.write(
                '<div class="table-scroll"><table class="sortable share-table" id="churn">'
                '<tr><th>File</th><th class="num">Times Changed</th><th class="unsortable"></th></tr>'
                + "".join(rows)
                + "</table></div>"
            )

        self.print_footer(f)
        f.write("</body></html>")
        f.close()

    def create_lines_html(self, data: Any, path: str) -> None:
        ###
        # Lines
        f = open(path + "/lines.html", "w", encoding="utf-8")
        self.print_header(f)
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
            )
        )

        self.print_footer(f)
        f.write("</body></html>")
        f.close()

    def create_tags_html(self, data: Any, path: str) -> None:
        ###
        # tags.html
        f = open(path + "/tags.html", "w", encoding="utf-8")
        self.print_header(f)
        self.print_nav(f, "tags.html")
        f.write("<h1>Tags</h1>")

        if data.tags:
            latest = max(data.tags, key=lambda t: (data.tags[t]["date"], t))
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

        f.write('<div class="table-scroll"><table class="tags">')
        f.write('<tr><th>Name</th><th>Date</th><th class="num">Commits</th><th>Authors</th></tr>')
        # sort the tags by date desc
        tags_sorted_by_date_desc = [
            el[1]
            for el in sorted([(el[1]["date"], el[0]) for el in data.tags.items()], reverse=True)
        ]
        max_tags_authors = load_config()["max_tags_authors"]
        for tag in tags_sorted_by_date_desc:
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
        self.print_header(f)
        self.print_nav(f, "ownership.html")
        f.write("<h1>Code Ownership</h1>")

        author_files = getattr(data, "author_files", {})
        if not isinstance(author_files, dict):
            author_files = {}
        # Only files that still exist: a deleted file carries no bus-factor risk
        current = head_files(data)
        if current is not None:
            author_files = {
                author: {p: n for p, n in files.items() if p in current}
                for author, files in author_files.items()
            }
        ownership = compute_code_ownership(author_files)

        if not ownership["files"]:
            f.write(
                '<div class="ownership-summary"><p>No ownership data available. '
                "Ownership is derived from which files each author changes; try "
                "analyzing a repository with commit history.</p></div>"
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
            '<div class="ownership-summary">'
            "<p>Ownership is measured by how many commits each author made to each "
            "file in the current tree. It highlights <strong>bus-factor risk</strong> (files only one "
            "person has ever touched) and where knowledge is concentrated.</p>"
            "</div>"
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
                    f'<div class="table-scroll"><table class="sortable" id="{table_id}">'
                    '<tr><th>File</th><th>Sole owner</th><th class="num">Commits</th></tr>'
                    + "".join(
                        f'<tr><td class="path">{html.escape(fs["path"])}</td>'
                        f"<td>{author_html(fs['owner'])}</td>"
                        f'<td class="num">{format_int(fs["edits"])}</td></tr>'
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
                '<div class="table-scroll"><table class="sortable" id="ownership-shared">'
                '<tr><th>File</th><th class="num">Contributors</th><th>Primary owner</th>'
                '<th class="num">Owner share</th></tr>'
            )
            for fs in shared[:20]:
                f.write(
                    '<tr><td class="path">%s</td><td class="num">%s</td><td>%s</td><td class="num">%.1f%%</td></tr>'
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
        self.print_header(f)
        self.print_nav(f, "history.html")
        f.write("<h1>History</h1>")

        history = compute_project_history(data)
        years = history["years"]

        if not years:
            f.write(
                '<div class="history-summary"><p>No history to tell yet — '
                "this repository has no commits in the analyzed range.</p></div>"
            )
            self.print_footer(f)
            f.write("</body></html>")
            f.close()
            return

        span = history["last_year"] - history["first_year"] + 1
        peak_commits = next(y["commits"] for y in years if y["year"] == history["peak_year"])
        release_years = [y["year"] for y in years if y["releases"]]
        f.write(
            '<div class="history-summary">'
            "<p>The project's life, one year at a time, told from the commit "
            "record: how activity rose and fell against the project's own "
            "baseline, who arrived when, and what was released.</p>"
            "</div>"
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
        self.print_header(f)
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
    ):
        """Render a Chart.js chart as inline HTML.

        With ``time_axis=True``, ``labels`` are Unix timestamps (seconds) and the
        x-axis is linear in time, so quiet periods keep their real width instead
        of collapsing between two adjacent points. Line series are drawn as steps
        because each point holds its value until the next one.

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
        tooltip line (e.g. "+2 new"); empty strings add nothing.
        """
        is_multi = len(datasets) > 1

        js_datasets = []
        for i, ds in enumerate(datasets):
            series = i % self.SERIES_COLORS + 1
            entry = dict(ds)
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

        if time_axis:
            labels = [int(stamp) * 1000 for stamp in labels]
        labels_json = json.dumps(labels).replace("</", "<\\/")
        datasets_json = json.dumps(js_datasets).replace("</", "<\\/")
        # Replace quoted placeholders with JS expressions
        datasets_json = datasets_json.replace('"__CSS_BAR_COLOR__"', "getCSSVar('--bar-color')")
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
          ds.data = ds.data.map(function(y, i) {{ return {{ x: xs[i], y: y }}; }});
        }});
        return sets;
      }})(labels, {datasets_json})"""
            x_scale_js = "timeAxis(labels)"
            tooltip_callbacks = [
                """title: function(items) {
          return items.length ? formatChartDate(items[0].parsed.x) : '';
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
            elif x_ticks_rotate:
                x_scale_js = "{ ticks: { maxRotation: 45, minRotation: 45 } }"
            else:
                x_scale_js = "{ ticks: { maxRotation: 0 } }"
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
            grace_js = ", grace: '10%'"
        else:
            plugins_js = register_js = grace_js = ""

        # The chart fills a .chart-box that keeps aspect_ratio on wide screens
        # but has a minimum height, so phones don't get a flattened plot.
        box_class = "chart-box has-legend" if is_multi else "chart-box"
        return f"""<div class="{box_class}" style="--chart-ratio: {aspect_ratio}"><canvas id="{chart_id}"></canvas></div>
<script>
(function() {{
  var ctx = document.getElementById('{chart_id}').getContext('2d');
  var labels = {labels_json};
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
        y: {{ beginAtZero: true{grace_js}, ticks: {{ precision: 0 }} }}
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

    def print_header(self, file: Any) -> None:
        """
        Write the HTML document header and opening body tag into the provided writable file.

        This writes the DOCTYPE, head section (title from self.title), a link to the configured stylesheet, a generator meta tag, an inclusion of sortable.js, an embedded client-side theme toggle script (init, toggle, and icon update handlers using localStorage), and the opening <body> tag.

        Parameters:
                file: A writable file-like object opened for text output where the HTML header will be written.
        """
        file.write(
            """<!DOCTYPE html>
<html lang="en">
<head>
	<meta charset="UTF-8">
	<meta name="viewport" content="width=device-width, initial-scale=1.0">
	<title>GitStats - {}</title>
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
        total_files, single_owner_files.
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

    return {
        "files": files_stats,
        "authors": authors_stats,
        "total_files": len(files_stats),
        "single_owner_files": sum(1 for fs in files_stats if fs["contributors"] == 1),
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


def stat_tiles_html(tiles: list[tuple[str, str, str]]) -> str:
    """Render headline numbers as a grid of stat tiles (KPI cards).

    Each tile is ``(label, value, note)``; ``value`` and ``note`` are inserted
    as HTML, so callers escape any user-controlled text. An empty note is
    left out.

    Column counts for wide, medium (<=1024px) and narrow (<=560px) screens
    are the largest divisors of the tile count up to 6, 3 and 2, so every
    row is full: 6 tiles -> 6/3/2, 3 -> 3/3/1, 2 -> 2/2/2.
    """

    def columns(limit: int) -> int:
        n = max(len(tiles), 1)
        return next(c for c in range(min(n, limit), 0, -1) if n % c == 0)

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
    style = f"--cols: {columns(6)}; --cols-md: {columns(3)}; --cols-sm: {columns(2)}"
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
