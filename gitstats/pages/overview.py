# Copyright (c) 2007-2014 Heikki Hokkanen <hoxu@users.sf.net> & others contributors
# GPLv2 / GPLv3
# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
"""The General page (index.html): the headline numbers, the years, the top
contributors and the latest releases.
"""

import datetime
import html
import time
from typing import Any

from gitstats.markup import (
    BAR_HEADER,
    INSIGHTS_END,
    INSIGHTS_START,
    author_html,
    html_header,
    plural,
    stat_tiles_html,
)
from gitstats.pages.base import PageWriter
from gitstats.periods import gap_annotations
from gitstats.utils import format_int, get_git_version, get_version, tags_newest_first


class OverviewPage(PageWriter):
    """Writes index.html."""

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
        # where a portfolio of repositories writes what stands out about this one
        f.write(INSIGHTS_START + INSIGHTS_END)
        if getattr(data, "shallow", False) is True:
            f.write(
                '<p class="section-note shallow-note"><strong>Shallow clone:</strong> this '
                "report only covers the commits that were fetched. Clone the full history "
                "(for example <code>git fetch --unshallow</code>) and generate it again.</p>"
            )

        total_commits = data.get_total_commits()
        active_days = len(data.get_active_days())
        delta_days = data.get_commit_delta_days()
        # the "no extension" row is not an extension
        extensions = len([ext for ext in data.extensions if ext])
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
                        plural(extensions, "extension"),
                    ),
                    (
                        "Active Days",
                        format_int(active_days),
                        f"of {plural(delta_days, 'day')} &middot; {100.0 * active_days / delta_days:.1f}%",
                    ),
                    (
                        "Longest Streak",
                        plural(streak, "day"),
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
        # "All 1 author" would point to the one already listed
        more = f"All {format_int(total)} authors" if total > 1 else "The author in detail"
        return (
            "<section>"
            + html_header(2, "Top contributors")
            + '<div class="table-scroll"><table class="share-table">'
            '<tr><th>Author</th><th class="num">Commits</th><th class="num">Share</th>'
            f"{BAR_HEADER}</tr>" + "".join(rows) + "</table></div>"
            f'<p class="more-link"><a href="authors.html">{more} &rarr;</a></p>'
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
        more = f"All {format_int(total)} tags" if total > 1 else "The tag in detail"
        return (
            "<section>"
            + html_header(2, "Latest releases")
            + '<div class="table-scroll"><table class="share-table">'
            '<tr><th>Tag</th><th>Date</th><th class="num">Commits</th><th>Authors</th></tr>'
            + "".join(rows)
            + "</table></div>"
            f'<p class="more-link"><a href="tags.html">{more} &rarr;</a></p>'
            "</section>"
        )
