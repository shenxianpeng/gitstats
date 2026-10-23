"""The gallery's ecosystem pages: each group of gallery/repos.yml ranked by
its AI-assisted commits, at a fixed address, with its data as JSON.

Writes, under ``<gallery_root>/ecosystems/``:

- ``<group>.html`` and ``<group>.json``: the group's repositories, ranked by
  the share of the last complete quarter's commits that name an AI coding
  assistant, with their commits and active authors of the last 12 months and
  their health;
- ``index.html`` and ``index.json``: every group, side by side;
- ``<group>-card.html`` and ``index-card.html``: their share cards, left to
  render as images (``-card.png``) when the pages point to them;

and ``<gallery_root>/sitemap.xml`` when the gallery's address is known.

The fields the JSON files keep from one version to the next are listed in
docs/source/gallery.rst. Called by generate_gallery_portfolio.py, which has
read the summaries and the list.
"""

import datetime
import html
import json
import os
import statistics
from collections.abc import Iterable
from typing import Any

from gallery_repos import Group, Repo

from gitstats.aggregate import last_quarters, quarter_id
from gitstats.report_creator import (
    AI_ASSISTED_COUNTED,
    THEME_INIT_SCRIPT,
    THEME_SCRIPT,
    THEME_TOGGLE_BUTTON,
    nav_link,
    share_card_page,
    share_meta_html,
    stat_tiles_html,
)
from gitstats.utils import format_int

FOLDER = "ecosystems"
INDEX = "index.html"
SCHEMA_VERSION = 1
ASSISTANT = "an AI coding assistant"


# ── the numbers ──────────────────────────────────────────────────────────


def quarter_counts(ai: Any, months: list[str]) -> tuple[int, int] | None:
    """(commits that name an assistant, all commits) in these months, or None
    when the summary does not cover all of them."""
    if not isinstance(ai, dict):
        return None
    by_month, all_by_month = ai.get("by_month") or {}, ai.get("commits_by_month") or {}
    if any(month not in all_by_month for month in months):
        return None
    return (
        sum(int(by_month.get(month, 0)) for month in months),
        sum(int(all_by_month[month]) for month in months),
    )


def share_of(counts: tuple[int, int] | None) -> float | None:
    """The share counts make, or None without commits to make one of."""
    if not counts or not counts[1]:
        return None
    return counts[0] / counts[1]


def percent(share: float | None) -> str:
    """A share as the pages write it, a plain number so that a table sorts
    by it: "4.1%", "0.04%" (two decimals under 0.1%), "0%"; "–" for none."""
    if share is None:
        return "–"
    if not share:
        return "0%"
    value = 100 * share
    return f"{value:.2f}%" if value < 0.1 else f"{value:.1f}%"


def _quarter_json(counts: tuple[int, int] | None) -> dict[str, Any] | None:
    if counts is None:
        return None
    share = share_of(counts)
    return {
        "commits": counts[1],
        "ai_assisted": counts[0],
        "share": None if share is None else round(share, 4),
    }


def rank_rows(
    repos: list[Repo], summaries: dict[str, dict[str, Any]], now: datetime.datetime
) -> list[dict[str, Any]]:
    """The rows of one group's table, ranked: the largest share in the last
    complete quarter first, then by that quarter's commits, then by name;
    repositories without a share in that quarter last. Repositories without a
    report are left out."""
    (_, previous), (_, latest) = last_quarters(now, 2)
    rows = []
    for repo in repos:
        summary = summaries.get(repo.id)
        if summary is None:
            continue
        ai = summary.get("ai_assisted")
        counts = quarter_counts(ai, latest)
        rows.append(
            {
                "id": repo.id,
                "name": str(summary.get("name") or repo.name),
                "repository": repo.url,
                "report": f"../{repo.id}/",
                "quarter": counts,
                "previous_quarter": quarter_counts(ai, previous),
                "commits_last_12mo": int(summary.get("commits_last_12mo", 0) or 0),
                "active_authors_12mo": int(summary.get("active_authors_12mo", 0) or 0),
                "health": str(summary.get("era", "") or ""),
                "last_commit": str(summary.get("last_commit", "") or "")[:10],
                "assistants": list((ai or {}).get("assistants") or {})[:3]
                if isinstance(ai, dict)
                else [],
            }
        )

    def order(row: dict[str, Any]) -> tuple[bool, float, int, str]:
        share = share_of(row["quarter"])
        return (share is None, -(share or 0.0), -(row["quarter"] or (0, 0))[1], row["name"].lower())

    rows.sort(key=order)
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
    return rows


def group_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The numbers the sentence at the top of a page says."""
    ranked = [row for row in rows if share_of(row["quarter"]) is not None]
    shares = [share_of(row["quarter"]) or 0.0 for row in ranked]
    top = ranked[0] if ranked and shares[0] > 0 else None
    return {
        "repositories": len(rows),
        "with_commits": len(ranked),
        "naming": sum(1 for share in shares if share > 0),
        "median_share": round(statistics.median(shares), 4) if shares else None,
        "highest": None
        if top is None
        else {"id": top["id"], "name": top["name"], "share": round(shares[0], 4)},
    }


def in_a_sentence(title: str) -> str:
    """A group's title inside a sentence: "open source projects from China",
    but "Python open source projects" and "CNCF graduated projects"."""
    first, _, rest = title.partition(" ")
    return f"{first.lower()} {rest}".strip() if first == "Open" else title


def summary_sentence(group: Group, summary: dict[str, Any], label: str) -> str:
    """What the page shows, in a sentence or two, as plain text."""
    projects = in_a_sentence(group.title)
    if not summary["with_commits"]:
        return f"None of the {summary['repositories']} {projects} in the Gallery has commits in {label}."
    text = (
        f"In {label}, the median project among {summary['with_commits']} {projects} had "
        f"{percent(summary['median_share'])} of its commits name {ASSISTANT}"
    )
    highest = summary["highest"]
    if highest is None:
        return text + "; none of them named one."
    return (
        f"{text}; the highest was {highest['name']}, at {percent(highest['share'])}. "
        f"{summary['naming']} of {summary['with_commits']} named one at least once."
    )


def page_title(group: Group, quarter: str) -> str:
    """The <title> of a group's page: what a search shows."""
    return f"{group.title} ranked by AI-assisted commits – {quarter.replace('-', ' ')}"


# ── the data ─────────────────────────────────────────────────────────────


def group_json(
    group: Group,
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    quarters: list[tuple[str, list[str]]],
    meta: dict[str, str],
) -> dict[str, Any]:
    """A group's page as data: see docs/source/gallery.rst."""
    (previous_label, previous), (label, latest) = quarters
    return {
        "schema_version": SCHEMA_VERSION,
        **meta,
        "ecosystem": {"id": group.id, "name": group.name, "title": group.title},
        "quarter": {"id": quarter_id(latest), "label": label},
        "previous_quarter": {"id": quarter_id(previous), "label": previous_label},
        "summary": summary,
        "repositories": [
            {
                "rank": row["rank"],
                "id": row["id"],
                "name": row["name"],
                "repository": row["repository"],
                "report": row["report"],
                "quarter": _quarter_json(row["quarter"]),
                "previous_quarter": _quarter_json(row["previous_quarter"]),
                "commits_last_12mo": row["commits_last_12mo"],
                "active_authors_12mo": row["active_authors_12mo"],
                "health": row["health"],
                "last_commit": row["last_commit"],
                "assistants": row["assistants"],
            }
            for row in rows
        ],
    }


# ── the pages ────────────────────────────────────────────────────────────


def _header(title: str, share: str, canonical: str) -> str:
    link = (
        f'<link rel="canonical" href="{html.escape(canonical, quote=True)}">' if canonical else ""
    )
    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n\t<meta charset="UTF-8">\n'
        '\t<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        f"\t<title>{html.escape(title)}</title>\n\t{share}\n\t{link}\n\t{THEME_INIT_SCRIPT}\n"
        '\t<link rel="stylesheet" href="../gitstats.css" type="text/css">\n'
        '\t<script type="text/javascript" src="../sortable.js"></script>\n'
        f"\t{THEME_SCRIPT}\n</head>\n<body>\n"
    )


def _nav(current: str) -> str:
    return (
        '<div class="nav"><a href="../index.html" class="nav-brand">GitStats</a><ul>'
        + nav_link("../index.html", "GitStats Gallery")
        + nav_link("../ai.html", "AI-assisted commits")
        + nav_link(INDEX, "Ecosystems", current=INDEX if current == "index" else "")
        + f'</ul><div class="nav-right">{THEME_TOGGLE_BUTTON}</div></div>'
    )


_FOOTER = (
    '<div class="footer"><span class="footer-generated">Generated by '
    '<a href="https://github.com/shenxianpeng/gitstats" target="_blank" rel="noopener">'
    "gitstats</a></span></div>\n</body>\n</html>\n"
)


def _health(era: str) -> str:
    if not era:
        return ""
    era = html.escape(era)
    return f'<span class="history-era history-era-{era}">{era}</span>'


def _share_cell(counts: tuple[int, int] | None) -> str:
    """A share, alone in its cell so that the column sorts by it; the counts
    it is made of show on hover."""
    hint = f' title="{format_int(counts[0])} of {format_int(counts[1])} commits"' if counts else ""
    return f'<td class="num"{hint}>{percent(share_of(counts))}</td>'


def _row_html(row: dict[str, Any]) -> str:
    named = ", ".join(html.escape(name) for name in row["assistants"][:2])
    link = html.escape(row["report"], quote=True)
    return (
        f'<tr><td class="num">{row["rank"]}</td>'
        f'<td><a href="{link}">{html.escape(row["name"])}</a></td>'
        f"{_share_cell(row['quarter'])}{_share_cell(row['previous_quarter'])}"
        f'<td class="num">{format_int(row["commits_last_12mo"])}</td>'
        f'<td class="num">{format_int(row["active_authors_12mo"])}</td>'
        f"<td>{_health(row['health'])}</td>"
        f"<td>{named or '&ndash;'}</td></tr>"
    )


def group_page(
    group: Group,
    groups: list[Group],
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    quarters: list[tuple[str, list[str]]],
    site_url: str,
    card: bool,
    generated: str,
) -> str:
    """A group's page: the sentence, the headline numbers, and the table."""
    (previous_label, _), (label, latest) = quarters
    title = page_title(group, quarter_id(latest))
    sentence = summary_sentence(group, summary, label)
    page = f"{group.id}.html"
    folder_url = f"{site_url}{FOLDER}/" if site_url else ""
    parts = [
        _header(
            f"{title} | GitStats Gallery",
            share_meta_html(
                title, sentence, folder_url, page, f"{group.id}-card.png" if card else ""
            ),
            folder_url + page if folder_url else "",
        ),
        _nav(group.id),
        f"<h1>{html.escape(group.name)}: ranked by AI-assisted commits</h1>",
        f'<p class="portfolio-subtitle">{html.escape(label)} &middot; '
        f"{summary['repositories']} repositories &middot; updated {generated} &middot; "
        f'<a href="{group.id}.json">data</a></p>',
        f'<p class="section-note">{html.escape(sentence)}</p>',
    ]
    highest = summary["highest"]
    tiles = [
        ("Median Share", percent(summary["median_share"]), f"{ASSISTANT}, {label}"),
        (
            "Highest Share",
            percent(highest["share"]) if highest else "–",
            html.escape(highest["name"]) if highest else "none names one",
        ),
        (
            "Naming One",
            f"{summary['naming']} of {summary['with_commits']}",
            "projects with commits that quarter",
        ),
    ]
    parts.extend(
        [
            stat_tiles_html(tiles),
            '<div class="table-scroll"><table class="sortable" id="ecosystem">'
            '<tr><th class="num">#</th><th>Repository</th>'
            f'<th class="num">{html.escape(label)}</th>'
            f'<th class="num">{html.escape(previous_label)}</th><th class="num">Commits (12 mo)</th>'
            '<th class="num">Active authors (12 mo)</th><th>Health</th><th>Named most</th></tr>'
            + "".join(_row_html(row) for row in rows)
            + "</table></div>",
            '<p class="section-note">The share of each quarter&rsquo;s commits that name '
            f"{ASSISTANT}: as their author, as a co-author, or in the line it signs with. A lower "
            "bound: an assistant that leaves no mark is not counted. Commits and active authors "
            "are those of the last 12 months; health is the project's pace of the last year.</p>",
            AI_ASSISTED_COUNTED,
        ]
    )
    others = " &middot; ".join(
        f'<a href="{other.id}.html">{html.escape(other.name)}</a>'
        for other in groups
        if other.id != group.id
    )
    parts.extend([f'<p class="more-link">Other ecosystems: {others}</p>', _FOOTER])
    return "".join(parts)


def index_page(
    groups: list[tuple[Group, dict[str, Any]]],
    label: str,
    quarter: str,
    site_url: str,
    card: bool,
    generated: str,
) -> str:
    """Every group side by side."""
    title = f"Open source ecosystems ranked by AI-assisted commits – {quarter.replace('-', ' ')}"
    description = (
        f"{label}: the median share of commits that name {ASSISTANT} in "
        + ", ".join(
            f"{group.name} ({percent(summary['median_share'])})" for group, summary in groups
        )
        + "."
    )
    folder_url = f"{site_url}{FOLDER}/" if site_url else ""
    rows = "".join(
        f'<tr><td><a href="{group.id}.html">{html.escape(group.name)}</a></td>'
        f'<td class="num">{summary["repositories"]}</td>'
        f'<td class="num">{percent(summary["median_share"])}</td>'
        f'<td class="num">{percent(summary["highest"]["share"]) if summary["highest"] else "&ndash;"}</td>'
        f"<td>{html.escape(summary['highest']['name']) if summary['highest'] else '&ndash;'}</td>"
        f'<td class="num">{summary["naming"]} / {summary["with_commits"]}</td></tr>'
        for group, summary in groups
    )
    return "".join(
        [
            _header(
                f"{title} | GitStats Gallery",
                share_meta_html(
                    title, description, folder_url, INDEX, "index-card.png" if card else ""
                ),
                folder_url,
            ),
            _nav("index"),
            "<h1>Ecosystems, ranked by AI-assisted commits</h1>",
            f'<p class="portfolio-subtitle">{html.escape(label)} &middot; {len(groups)} '
            f'ecosystems &middot; updated {generated} &middot; <a href="index.json">data</a></p>',
            f'<p class="section-note">{html.escape(description)} Each ecosystem has its page, '
            "its projects ranked.</p>",
            '<div class="table-scroll"><table class="sortable" id="ecosystems">'
            '<tr><th>Ecosystem</th><th class="num">Repositories</th>'
            '<th class="num">Median share</th><th class="num">Highest share</th>'
            '<th>Highest</th><th class="num">Naming one</th></tr>',
            rows,
            "</table></div>",
            AI_ASSISTED_COUNTED,
            _FOOTER,
        ]
    )


def group_card(
    group: Group, rows: list[dict[str, Any]], summary: dict[str, Any], label: str
) -> str:
    """A group's share card: its largest shares of the quarter, as bars."""
    top = [row for row in rows if share_of(row["quarter"])][:6]
    return _bars_card(
        f"{group.name}: AI-assisted commits",
        f"// {group.name}",
        label,
        f"The median project&rsquo;s share of commits that name {ASSISTANT}: "
        f"{percent(summary['median_share'])}, of {summary['with_commits']} projects. A lower bound.",
        [(row["name"], share_of(row["quarter"]) or 0.0) for row in top],
    )


def index_card(groups: list[tuple[Group, dict[str, Any]]], label: str) -> str:
    """The share card of the index: each group's median, as bars."""
    bars = [
        (group.name, summary["median_share"])
        for group, summary in groups
        if summary["median_share"]
    ]
    bars.sort(key=lambda bar: -bar[1])
    return _bars_card(
        "Ecosystems: AI-assisted commits",
        "// Ecosystems",
        label,
        f"The median project&rsquo;s share of commits that name {ASSISTANT}, by ecosystem. "
        "A lower bound.",
        bars[:6],
    )


def _bars_card(title: str, brand: str, label: str, sub: str, bars: list[tuple[str, float]]) -> str:
    top = max((share for _, share in bars), default=1.0) or 1.0
    body = "".join(
        f"<div><b>{html.escape(name)}</b>"
        f'<i style="width:{100 * share / top:.1f}%"></i><span>{percent(share)}</span></div>'
        for name, share in bars
    )
    return share_card_page(
        title,
        f'<div class="brand">{html.escape(brand)}</div><h1>{html.escape(label)}</h1>'
        f'<p class="sub">{sub}</p><div class="bars">{body}</div>',
    )


def sitemap(site_url: str, pages: Iterable[str], day: str) -> str:
    """sitemap.xml of the gallery's pages, given relative to its address."""
    urls = "".join(
        f"<url><loc>{html.escape(site_url + page)}</loc><lastmod>{day}</lastmod></url>"
        for page in pages
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n'
    )


# ── writing them ─────────────────────────────────────────────────────────


def _write(base: str, name: str, text: str) -> None:
    """Write ``text`` to ``name`` under the directory ``base``, never outside."""
    base = os.path.realpath(base)
    target = os.path.realpath(os.path.join(base, name))
    if os.path.commonpath([base, target]) != base or target == base:
        raise ValueError(f"Refusing to write outside the gallery: {name}")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(text)


def _dump(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def write_ecosystems(
    gallery_root: str,
    groups: list[Group],
    repos: list[Repo],
    summaries: list[dict[str, Any]],
    site_url: str = "",
    card: bool = False,
    version: str = "",
    now: datetime.datetime | None = None,
) -> list[Group]:
    """Write the ecosystem pages, their data and cards, and the sitemap when
    ``site_url`` (the gallery's address, ending in "/") is known. ``card``:
    the pages point to their cards as images. The groups that have a page:
    those with a report."""
    now = now or datetime.datetime.now()
    quarters = last_quarters(now, 2)
    label, latest = quarters[-1]
    quarter = quarter_id(latest)
    generated = now.strftime("%Y-%m-%d")
    meta = {
        "generated_by": f"gitstats {version}".strip(),
        "generated_at": now.astimezone().isoformat(timespec="seconds"),
    }
    by_id = {summary["report_path"].split("/", 1)[0]: summary for summary in summaries}
    ranked = []
    for group in groups:
        rows = rank_rows([repo for repo in repos if repo.group == group.id], by_id, now)
        if rows:
            ranked.append((group, rows, group_summary(rows)))
    if not ranked:
        return []
    pages = [group for group, _, _ in ranked]
    for group, rows, summary in ranked:
        data = group_json(group, rows, summary, quarters, meta)
        _write(gallery_root, f"{FOLDER}/{group.id}.json", _dump(data))
        page = group_page(group, pages, rows, summary, quarters, site_url, card, generated)
        _write(gallery_root, f"{FOLDER}/{group.id}.html", page)
        _write(
            gallery_root, f"{FOLDER}/{group.id}-card.html", group_card(group, rows, summary, label)
        )
    written = [(group, summary) for group, _, summary in ranked]
    index = {
        "schema_version": SCHEMA_VERSION,
        **meta,
        "quarter": {"id": quarter, "label": label},
        "ecosystems": [
            {
                "id": group.id,
                "name": group.name,
                "title": group.title,
                "page": f"{group.id}.html",
                "data": f"{group.id}.json",
                "summary": summary,
            }
            for group, summary in written
        ],
    }
    _write(gallery_root, f"{FOLDER}/index.json", _dump(index))
    _write(
        gallery_root,
        f"{FOLDER}/index.html",
        index_page(written, label, quarter, site_url, card, generated),
    )
    _write(gallery_root, f"{FOLDER}/index-card.html", index_card(written, label))
    if site_url:
        urls = ["", "ai.html", f"{FOLDER}/"]
        urls += [f"{FOLDER}/{group.id}.html" for group in pages]
        urls += [f"{repo.id}/" for repo in repos if repo.id in by_id]
        _write(gallery_root, "sitemap.xml", sitemap(site_url, urls, generated))
    return pages
