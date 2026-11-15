# Copyright (c) 2007-2014 Heikki Hokkanen <hoxu@users.sf.net> & others contributors
# GPLv2 / GPLv3
# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
"""The Activity page: commits by week, by hour and day of the week, by month
and year, and by timezone.
"""

import datetime
import html
from typing import Any

from gitstats import WEEKDAYS
from gitstats.markup import (
    BAR_HEADER,
    FIRST_PARENT_LINES,
    html_header,
    html_linkify,
    lines_uncounted,
    plural,
    stat_tiles_html,
)
from gitstats.pages.base import PageWriter
from gitstats.periods import gap_annotations, month_range
from gitstats.utils import WEEK_KEY, format_int


class ActivityPage(PageWriter):
    """Writes activity.html."""

    def create_activity_html(self, data: Any, path: str) -> None:
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

    def _write_activity_intro(self, f: Any, data: Any) -> None:
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
                f"on {plural(active, 'active day')}",
            ),
            (
                "Longest Streak",
                plural(streak, "day"),
                "consecutive active days",
            ),
        ]
        if hours:
            hour = max(hours, key=lambda h: (hours[h], -h))
            tiles.append(("Busiest Hour", f"{hour:02d}:00", plural(hours[hour], "commit")))
        if days:
            day = max(days, key=lambda d: (days[d], -d))
            tiles.append(("Busiest Day", full_days[day], plural(days[day], "commit")))
        f.write(stat_tiles_html(tiles))
        links = "".join(
            f'<a href="#{html_linkify(title)}">{label}</a>'
            for title, label in self.ACTIVITY_SECTIONS
        )
        f.write(
            '<nav class="page-toc" aria-label="On this page">'
            f"<span>On this page</span>{links}</nav>"
        )

    def _write_weekly_activity_section(self, f: Any, data: Any) -> None:
        """Commits per week for the last 32 weeks, up to the week of the last
        commit when that is earlier: a repository without commits for months
        would show 32 empty weeks.

        Weeks are labelled by the Monday they start on ("Feb 16"), with the
        year ("Dec 26, 2022") when the weeks are not all in this one; the
        ISO weeks the data is stored under (WEEK_KEY) read like months ("2026-07").
        """
        weeks_count = 32
        f.write(html_header(2, "Weekly activity"))

        now = datetime.datetime.now()
        stamp = getattr(data, "last_commit_stamp", 0)
        last_commit = (
            datetime.datetime.fromtimestamp(stamp) if isinstance(stamp, int) and stamp else now
        )
        week = WEEK_KEY  # the key the commits of a week are kept under
        quiet = last_commit.strftime(week) < now.strftime(week)
        deltaweek = datetime.timedelta(7)
        weeks: list[str] = []
        mondays: list[datetime.date] = []
        stampcur = last_commit if quiet else now
        for _ in range(weeks_count):
            weeks.insert(0, stampcur.strftime(week))
            mondays.insert(0, (stampcur - datetime.timedelta(days=stampcur.weekday())).date())
            stampcur -= deltaweek

        def day(d: datetime.date) -> str:
            return f"{d:%b} {d.day}"

        span = (
            f"from the week of {day(mondays[0])}, {mondays[0].year} "
            f"to the week of {day(mondays[-1])}, {mondays[-1].year}"
        )
        f.write(
            '<p class="section-note">'
            + (
                f"The {weeks_count} weeks up to the last commit, {span}: there has been none since."
                if quiet
                else f"Last {weeks_count} weeks, {span}."
            )
            + "</p>"
        )
        weekly_values = [data.activity_by_year_week.get(w, 0) for w in weeks]
        # "Dec 26" alone could be any year's, in the axis and in the tooltip
        with_year = any(m.year != now.year for m in mondays)
        f.write(
            self._render_chartjs(
                "chart-weekly-activity",
                "bar",
                [f"{day(m)}, {m.year}" if with_year else day(m) for m in mondays],
                [{"label": "Commits", "data": weekly_values}],
                aspect_ratio=5,
            )
        )

    def _write_punch_card_section(self, f: Any, data: Any) -> None:
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
                f'<td title="{hour:02d}:00 &middot; {plural(commits, "commit")} &middot; '
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

    def _write_month_of_year_section(self, f: Any, data: Any) -> None:
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

    def _write_commits_by_year_month_section(self, f: Any, data: Any) -> None:
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

    def _write_commits_by_year_section(self, f: Any, data: Any) -> None:
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
        uncounted_years = 0
        for yy in years:
            commits = data.commits_by_year.get(yy, 0)
            added = data.lines_added_by_year.get(yy, 0)
            removed = data.lines_removed_by_year.get(yy, 0)
            if lines_uncounted(commits, added, removed):
                uncounted_years += 1
                lines = '<td class="num">&mdash;</td><td class="num">&mdash;</td>'
            else:
                lines = (
                    f'<td class="num">{format_int(added)}</td>'
                    f'<td class="num">{format_int(removed)}</td>'
                )
            f.write(
                f'<tr><td>{yy}</td><td class="num">{format_int(commits)} '
                f"({100.0 * commits / total:.1f}%)</td>{lines}</tr>"
            )
        note = (
            f'<p class="section-note">&mdash;: {FIRST_PARENT_LINES}</p>' if uncounted_years else ""
        )
        f.write(f"</table></div>{note}</details>")

    def _write_commits_by_timezone_section(self, f: Any, data: Any) -> None:
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
            f"{BAR_HEADER}</tr>" + "".join(rows) + "</table></div>"
        )
