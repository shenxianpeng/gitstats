# Copyright (c) 2007-2014 Heikki Hokkanen <hoxu@users.sf.net> & others contributors
# GPLv2 / GPLv3
# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
"""The Tags page: every tag with its commits and its authors."""

import html
from typing import Any

from gitstats import load_config
from gitstats.markup import html_header, plural, stat_tiles_html, tag_authors_html
from gitstats.pages.base import PageWriter
from gitstats.utils import format_int, get_keys_sorted_by_values, tags_newest_first


class TagsPage(PageWriter):
    """Writes tags.html."""

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
                            f"{plural(data.get_total_commits(), 'commit')} in total",
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
                '<tr><th data-sort-as="text">Name</th><th>Date</th><th class="num">Commits</th>'
                '<th class="unsortable">Authors</th></tr>'
            )
            max_tags_authors = load_config()["max_tags_authors"]
            for tag in tags_newest_first(data.tags):
                self.authors_by_commits = get_keys_sorted_by_values(data.tags[tag]["authors"])
                f.write(
                    '<tr><td class="nowrap">%s</td><td class="nowrap">%s</td><td class="num">%s</td><td>%s</td></tr>'
                    % (
                        html.escape(tag),
                        data.tags[tag]["date"],
                        format_int(data.tags[tag]["commits"]),
                        tag_authors_html(
                            list(reversed(self.authors_by_commits)),
                            data.tags[tag]["authors"],
                            max_tags_authors,
                        ),
                    )
                )
            f.write("</table></div>")

        self.print_footer(f)
        f.write("</body></html>")
        f.close()
