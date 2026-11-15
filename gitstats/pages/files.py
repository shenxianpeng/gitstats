# Copyright (c) 2007-2014 Heikki Hokkanen <hoxu@users.sf.net> & others contributors
# GPLv2 / GPLv3
# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
"""The Files page: the files over time, the extensions, and the files changed most."""

import datetime
import html
from typing import Any

from gitstats.markup import BAR_HEADER, FILE_TABLE, html_header, plural, stat_tiles_html
from gitstats.ownership import head_files
from gitstats.pages.base import PageWriter
from gitstats.periods import time_gap_annotations
from gitstats.utils import format_bytes, format_int


class FilesPage(PageWriter):
    """Writes files.html."""

    def create_files_html(self, data: Any, path: str) -> None:
        ###
        # Files
        f = open(path + "/files.html", "w", encoding="utf-8")
        self.print_header(f, "files.html")
        self.print_nav(f, "files.html")
        f.write("<h1>Files</h1>")

        total_files = data.get_total_files()
        # the "no extension" row is not an extension
        extensions = len([ext for ext in data.extensions if ext])
        tiles = [
            (
                "Files",
                format_int(total_files),
                plural(extensions, "extension"),
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
            f"{BAR_HEADER}</tr>" + "".join(rows) + "</table></div>"
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
                f'<tr><th>File</th><th class="num">Times Changed</th>{BAR_HEADER}</tr>'
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
