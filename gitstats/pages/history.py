# Copyright (c) 2007-2014 Heikki Hokkanen <hoxu@users.sf.net> & others contributors
# GPLv2 / GPLv3
# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
"""The History page: the project one year at a time, with optional AI narration."""

import html
from typing import Any

from gitstats.history import compute_project_history, parse_chronicle
from gitstats.markup import FIRST_PARENT_LINES, lines_uncounted, plural, stat_tiles_html
from gitstats.pages.base import PageWriter
from gitstats.utils import format_int


class HistoryPage(PageWriter):
    """Writes history.html."""

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
                        plural(span, "year"),
                    ),
                    (
                        "Peak Year",
                        str(history["peak_year"]),
                        plural(peak_commits, "commit"),
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
        def own_row(entry: dict[str, Any]) -> bool:
            has_chapter = bool(chronicle and chronicle["chapters"].get(entry["year"]))
            return entry["era"] != "dormant" or entry["commits"] > 0 or has_chapter

        rows: list[list[dict[str, Any]]] = []
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
                uncounted = lines_uncounted(
                    entry["commits"], entry["lines_added"], entry["lines_removed"]
                )
                lines = (
                    "lines &mdash;"
                    if uncounted
                    else f"+{format_int(entry['lines_added'])} / "
                    f"&minus;{format_int(entry['lines_removed'])} lines"
                )
                facts = (
                    f"{plural(entry['commits'], 'commit')} ({entry['commits_pct']}%) &middot; "
                    f"{lines} &middot; {plural(entry['active_authors'], 'author')}"
                )
                f.write(f'<p class="history-facts">{facts}</p>')
                if uncounted:
                    f.write(f'<p class="history-people">{FIRST_PARENT_LINES}</p>')
                if entry["top_author"]:
                    f.write(
                        '<p class="history-people">Led by <strong>%s</strong> (%s)</p>'
                        % (
                            html.escape(entry["top_author"]),
                            plural(entry["top_author_commits"], "commit"),
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
                        '<a href="wrapped.html">Wrapped card &rarr;</a></p>'
                    )
            else:
                f.write('<p class="history-facts">No commits this year.</p>')
            f.write("</div>")

        self.print_footer(f)
        f.write("</body></html>")
        f.close()
