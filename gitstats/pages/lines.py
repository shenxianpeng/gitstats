# Copyright (c) 2007-2014 Heikki Hokkanen <hoxu@users.sf.net> & others contributors
# GPLv2 / GPLv3
# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
"""The Lines page: the lines of code over time, added and removed per month."""

from typing import Any

from gitstats.markup import html_header, plural, stat_tiles_html
from gitstats.pages.base import PageWriter
from gitstats.periods import month_range, quiet_band, quiet_months, time_gap_annotations
from gitstats.utils import format_int


class LinesPage(PageWriter):
    """Writes lines.html."""

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
                        f"in {plural(data.get_total_files(), 'file')}",
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
