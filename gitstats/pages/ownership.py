# Copyright (c) 2007-2014 Heikki Hokkanen <hoxu@users.sf.net> & others contributors
# GPLv2 / GPLv3
# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
"""The Code Ownership page: the bus factor, the files one person alone has
changed, and who owns what.
"""

import html
from typing import Any

from gitstats.markup import FILE_TABLE, author_html, html_header, plural, stat_tiles_html
from gitstats.ownership import head_files, head_ownership
from gitstats.pages.base import PageWriter
from gitstats.utils import format_int


class OwnershipPage(PageWriter):
    """Writes ownership.html."""

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
            f"of {plural(total, 'file')}"
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
                        plural(len(ownership["authors"]), "author", number=False)
                        + " who changed files",
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

            def risk_table(table_id: str, rows: list[dict[str, Any]]) -> str:
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
