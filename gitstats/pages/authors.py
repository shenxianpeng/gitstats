# Copyright (c) 2007-2014 Heikki Hokkanen <hoxu@users.sf.net> & others contributors
# GPLv2 / GPLv3
# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
"""The Authors page: every author, a contributor timeline, the lines each has
added over time, the organizations their addresses belong to, and the
commits that name an AI coding assistant.
"""

import datetime
import html
import math
from typing import Any

from gitstats import load_config
from gitstats.employers import KIND_LABELS, KINDS, ORGANIZATION
from gitstats.employers import summarize as summarize_organizations
from gitstats.markup import (
    AI_ASSISTED_COUNTED,
    BAR_HEADER,
    author_html,
    html_header,
    plural,
    share_text,
    stat_tiles_html,
)
from gitstats.pages.base import PageWriter
from gitstats.periods import (
    collapsed_slots,
    month_range,
    months_back,
    quiet_band,
    quiet_months,
    sum_since,
    time_gap_annotations,
    year_span,
)
from gitstats.utils import (
    format_duration,
    format_int,
    get_keys_sorted_by_value_key,
    get_keys_sorted_by_values,
    is_bot,
)


def ai_assisted_count(data: Any) -> int:
    """How many commits name an AI coding assistant; none for data collected
    before that was counted."""
    count = getattr(data, "ai_assisted_commits", 0)
    return count if isinstance(count, int) else 0


class AuthorsPage(PageWriter):
    """Writes authors.html."""

    def _build_author_time_series(self, data: Any) -> tuple[list[int], list[dict[str, Any]]]:
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
        time_labels: list[int] = []
        per_author_lines: dict[str, list[int]] = {a: [] for a in authors_to_plot}

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
                        f'--size: {size:.1f}px" title="{month}: {plural(count, "commit")}"></span>'
                    )
                label = f"{name}: {plural(commits, 'commit')}, {active[0]} to {active[-1]}"
            else:
                marks = []
                label = f"{name}: {plural(commits, 'commit')}"
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
                f"incl. {plural(bots, 'bot account')}" if bots else "no bot accounts",
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
                    f"at least {format_int(assisted)} of all "
                    f"{plural(data.get_total_commits(), 'commit')}",
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
            f"{format_int(assisted)} of {plural(total, 'commit')} "
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
            f'<tr><th>Assistant</th><th class="num">Commits</th>{BAR_HEADER}'
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
            f'<p class="section-note">{format_int(from_orgs)} of {plural(total, "commit")} '
            f"({share_text(from_orgs, total)}) come from an address at "
            f"{plural(count, 'organization')}, counted by the "
            "domain of the address and committed from by two people or more. Domains of "
            "one person (most often that person's own), personal mail providers, hidden "
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
            f'{BAR_HEADER}<th class="num">Last 12 months</th><th class="num">Addresses</th>'
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
            '<tr><th>Author</th><th class="num">Commits (%)</th><th class="num">+ lines</th><th class="num">- lines</th><th>First commit</th><th>Last commit</th><th class="num">Age</th><th class="num">Active days</th><th class="num"># by commits</th></tr>'
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
                '<tr><td>%s</td><td class="num">%s (%.1f%%)%s</td><td class="num stat-added">%s</td><td class="num stat-removed">%s</td><td class="nowrap">%s</td><td class="nowrap">%s</td><td class="nowrap num" title="%s" data-sort="%d">%s</td><td class="num">%s</td><td class="num">%d</td></tr>'
                % (
                    author_html(author),
                    format_int(info["commits"]),
                    info["commits_frac"],
                    share_bar,
                    format_int(info["lines_added"]),
                    format_int(info["lines_removed"]),
                    info["date_first"],
                    info["date_last"],
                    plural(info["timedelta"].days, "day"),
                    info["timedelta"].days,
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
            f'<tr><th>Domain</th><th class="num">Commits</th><th class="num">Share</th>{BAR_HEADER}</tr>'
            + "".join(rows)
            + "</table></div>"
        )

        self.print_footer(f)
        f.write("</body></html>")
        f.close()

    def _top_authors_table(
        self,
        table_id: str,
        period: str,
        authors_by_period: dict[Any, dict[str, int]],
        commits_by_period: dict[Any, int],
    ) -> str:
        """A sortable table of each period's top author, newest period first."""
        top = load_config()["authors_top"]
        rows = [
            f'<div class="table-scroll"><table class="sortable period-table" id="{table_id}">'
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
