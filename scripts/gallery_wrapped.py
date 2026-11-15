"""The gallery's Repo Wrapped page: one year in every repository of the
gallery, each with its card.

Writes, under ``<gallery_root>/wrapped/``:

- ``index.html``: the year's commits in all of them, what stands out, the
  repositories in a table that sorts, and their cards, each leading to the
  repository's own Wrapped page;
- ``index.json``: the same numbers as data;
- ``index-card.html``: the page's share card, left to render as an image
  (``index-card.png``) when the page points to it.

Each repository's numbers are those of the card its report was made with
(``gitstats --wrapped``), read from the ``wrapped-<year>.json`` next to it.
The year of the page is the one most of the cards are for: a report kept
from an earlier build, with the card of another year, is left out.

The fields ``index.json`` keeps from one version to the next are listed in
docs/source/gallery.rst. Called by generate_gallery_portfolio.py, which has
read the summaries.
"""

import datetime
import html
import json
import os
import re
import sys
from collections import Counter
from typing import Any

from gitstats.report_creator import (
    FOOTER,
    NAV_END,
    NAV_START,
    SKIP_LINK,
    THEME_INIT_SCRIPT,
    THEME_SCRIPT,
    THEME_TOGGLE_BUTTON,
    nav_link,
    plural,
    share_card_page,
    share_meta_html,
    stat_tiles_html,
)
from gitstats.utils import format_int
from gitstats.wrapped import COMPARED, PAGE, change

FOLDER = "wrapped"
INDEX = "index.html"
# The version of what index.json holds: a field that changes its name, type
# or meaning comes with a new one
SCHEMA_VERSION = 1
# The commits a repository needs in the days of the year before for its growth
# to be ranked: 12 commits that became 60 are five times as many, and say little
MIN_BASE_COMMITS = 100
_CARD_DATA = re.compile(r"wrapped-(\d{4})\.json")
# what the page keeps of the year before
_BEFORE = ("year", "through", *COMPARED)


# ── the numbers ──────────────────────────────────────────────────────────


def _count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _card_of(data: Any) -> dict[str, Any] | None:
    """What the page keeps of a card's data, or None when it is not the data
    of a card: a year, the numbers that are compared, and the same numbers of
    the year before when the card has one."""
    if not isinstance(data, dict) or not _count(data.get("year")):
        return None
    if not all(_count(data.get(key)) for key in COMPARED):
        return None
    if not isinstance(data.get("card"), str) or not isinstance(data.get("through"), str):
        return None
    before = data.get("previous")
    if before is not None:
        if not isinstance(before, dict) or not all(_count(before.get(key)) for key in COMPARED):
            return None
        if not _count(before.get("year")) or not isinstance(before.get("through"), str):
            return None
        before = {key: before[key] for key in _BEFORE}
    return {
        "year": data["year"],
        "complete": bool(data.get("complete")),
        "through": data["through"],
        # the file's name only: it is looked for next to the data
        "card": os.path.basename(data["card"]),
        **{key: data[key] for key in COMPARED},
        "previous": before,
    }


def load_cards(gallery_root: str, summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The numbers of each report's card, with the report it belongs to
    (``id``, ``name``, ``group``), in the order of ``summaries``.

    A report has a card when its folder has the data of one, the latest
    year's if it has several, with the card and its page next to it. One
    without, or whose data cannot be read, is left out. Nothing outside the
    gallery's folder is read.
    """
    base = os.path.realpath(gallery_root)
    cards = []
    for summary in summaries:
        report_id = str(summary["report_path"]).split("/", 1)[0]
        folder = os.path.realpath(os.path.join(base, os.path.basename(report_id)))
        if os.path.dirname(folder) != base or not os.path.isdir(folder):
            continue
        names = sorted(name for name in os.listdir(folder) if _CARD_DATA.fullmatch(name))
        if not names:
            continue
        try:
            with open(os.path.join(folder, names[-1]), encoding="utf-8") as f:
                card = _card_of(json.load(f))
        except (OSError, ValueError) as error:
            print(
                f"Skipping unreadable card data: {report_id}/{names[-1]} ({error})", file=sys.stderr
            )
            continue
        if card is None:
            print(f"Skipping data that is not a card's: {report_id}/{names[-1]}", file=sys.stderr)
            continue
        if not all(os.path.isfile(os.path.join(folder, name)) for name in (card["card"], PAGE)):
            continue
        cards.append(
            {
                "id": report_id,
                "name": str(summary.get("name") or report_id),
                "group": str(summary.get("group", "")),
                "data": names[-1],
                **card,
            }
        )
    return cards


def cards_of_the_year(cards: list[dict[str, Any]]) -> tuple[int | None, list[dict[str, Any]]]:
    """The year most of the cards are for, the later one when two years have
    as many, and the cards of that year, the most commits first. (None, [])
    without a card."""
    if not cards:
        return None, []
    years = Counter(card["year"] for card in cards)
    year = max(years, key=lambda candidate: (years[candidate], candidate))
    kept = [card for card in cards if card["year"] == year]
    kept.sort(key=lambda card: (-card["commits"], card["name"].lower()))
    return year, kept


def totals(cards: list[dict[str, Any]]) -> dict[str, Any]:
    """The commits of all the cards, and, of those with a year before to
    compare with, their commits and those of the year before: like with like."""
    compared = [card for card in cards if card["previous"]]
    return {
        "repositories": len(cards),
        "commits": sum(card["commits"] for card in cards),
        "compared": {
            "repositories": len(compared),
            "commits": sum(card["commits"] for card in compared),
            "previous_commits": sum(card["previous"]["commits"] for card in compared),
        },
    }


def growth(card: dict[str, Any]) -> float | None:
    """How many times the commits of the year before a repository's commits
    are, less one; None for one with too few then to rank it by."""
    before = card["previous"]
    if not before or before["commits"] < MIN_BASE_COMMITS:
        return None
    return card["commits"] / before["commits"] - 1


def standing_out(cards: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any], str]]:
    """What stands out among the cards, as (what, the card, its number): the
    most commits, the largest growth of them, the longest streak and the most
    new contributors. A measure nobody has a number above zero for is left
    out; a tie goes to the repository with more commits."""
    found = []

    def first(key: Any) -> dict[str, Any] | None:
        # the cards come with the most commits first, and max() keeps the first
        best = max(cards, key=key)
        return best if key(best) > 0 else None

    most = first(lambda card: card["commits"])
    if most:
        found.append(("Most commits", most, format_int(most["commits"])))
    fastest = first(lambda card: growth(card) or 0)
    if fastest:
        _, text = change(fastest["commits"], fastest["previous"]["commits"], True) or (0, "")
        found.append(("Fastest growing", fastest, text))
    streak = first(lambda card: card["longest_streak"])
    if streak:
        found.append(("Longest streak", streak, f"{format_int(streak['longest_streak'])} days"))
    arrivals = first(lambda card: card["new_contributors"])
    if arrivals:
        found.append(("Most new contributors", arrivals, format_int(arrivals["new_contributors"])))
    return found


def period(year: int, cards: list[dict[str, Any]]) -> tuple[str, str]:
    """The year in a sentence ("2026 so far" while any card's year is under
    way), and what its numbers are compared with ("" when no card has a year
    before)."""
    complete = all(card["complete"] for card in cards)
    compared = ""
    if any(card["previous"] for card in cards):
        compared = f"{year - 1}" if complete else f"the same days of {year - 1}"
    return (f"{year}" if complete else f"{year} so far"), compared


def index_json(year: int, cards: list[dict[str, Any]], meta: dict[str, str]) -> dict[str, Any]:
    """What index.json holds: the year, the totals and each repository's numbers."""
    return {
        "schema_version": SCHEMA_VERSION,
        **meta,
        "year": year,
        "complete": all(card["complete"] for card in cards),
        "totals": totals(cards),
        "repositories": [
            {
                "id": card["id"],
                "name": card["name"],
                "group": card["group"],
                # from the gallery's own address
                "page": f"{card['id']}/{PAGE}",
                "card": f"{card['id']}/{card['card']}",
                "data": f"{card['id']}/{card['data']}",
                "through": card["through"],
                **{key: card[key] for key in COMPARED},
                "previous": card["previous"],
            }
            for card in cards
        ],
    }


# ── the page ─────────────────────────────────────────────────────────────


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
        f"\t{THEME_SCRIPT}\n</head>\n<body>\n{SKIP_LINK}\n"
    )


def _nav(tabs: list[tuple[str, str]], label: str) -> str:
    """The gallery's nav, as its other pages have it: ``tabs`` are the pages
    that come before this one, as (address from the gallery, label)."""
    return (
        f'{NAV_START}<a href="../index.html" class="nav-brand">GitStats</a><ul>'
        + nav_link("../index.html", "GitStats Gallery")
        + "".join(
            nav_link(html.escape(f"../{href}", quote=True), html.escape(name))
            for href, name in tabs
        )
        + nav_link(INDEX, html.escape(label), current=INDEX)
        + f'</ul><div class="nav-right">{THEME_TOGGLE_BUTTON}</div>{NAV_END}'
    )


def _moved_cell(card: dict[str, Any], key: str) -> str:
    """How one number of a repository moved, alone in its cell so that the
    column sorts by it: by how many times as many for a percentage, by the
    difference for the others. Empty without a year before, or without a
    number then to take a percentage of."""
    before = card["previous"]
    moved = change(card[key], before[key], COMPARED[key]) if before else None
    if not moved:
        return '<td class="num"></td>'
    direction, text = moved
    by = card[key] / before[key] - 1 if COMPARED[key] else card[key] - before[key]
    name = {1: "wrapped-up", -1: "wrapped-down"}.get(direction, "wrapped-same")
    return (
        f'<td class="num" data-sort="{by:.6f}"><span class="{name}">{html.escape(text)}</span></td>'
    )


def _page_link(card: dict[str, Any]) -> str:
    """The address of a repository's own Wrapped page, from this one."""
    return html.escape(f"../{card['id']}/{PAGE}", quote=True)


def _row_html(card: dict[str, Any], groups: dict[str, str]) -> str:
    group = f"<td>{html.escape(groups.get(card['group'], ''))}</td>" if groups else ""
    return (
        f'<tr><td><a href="{_page_link(card)}">{html.escape(card["name"])}</a></td>{group}'
        f'<td class="num">{format_int(card["commits"])}</td>{_moved_cell(card, "commits")}'
        f'<td class="num">{format_int(card["contributors"])}</td>'
        f"{_moved_cell(card, 'contributors')}"
        f'<td class="num">{format_int(card["new_contributors"])}</td>'
        f'<td class="num">{format_int(card["active_days"])}</td>'
        f'<td class="num">{format_int(card["longest_streak"])}</td>'
        f'<td class="num">{format_int(card["lines_changed"])}</td>'
        f'<td class="num">{format_int(card["releases"])}</td></tr>'
    )


def _tiles(year: int, cards: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    """The headline numbers: the commits of all the repositories, and what
    stands out among them."""
    total = totals(cards)
    like = total["compared"]["repositories"]
    note = _against(year, cards)
    if not note:
        note = f"in {plural(total['repositories'], 'project')}"
    elif like < total["repositories"]:
        # like with like: the projects that had commits in those days
        note += f" &middot; in the {format_int(like)} with commits then"
    tiles = [("Commits", format_int(total["commits"]), note)]
    for what, card, number in standing_out(cards):
        name = html.escape(card["name"])
        # the number is the tile's, the project under it, as on the ecosystems' pages
        tiles.append((what, html.escape(number), f'<a href="{_page_link(card)}">{name}</a>'))
    return tiles


def _against(year: int, cards: list[dict[str, Any]]) -> str:
    """How the commits of the cards that have a year before moved from it:
    "+4% on 2025", "level with 2025"; "" when none has one."""
    _, compared = period(year, cards)
    like = totals(cards)["compared"]
    moved = change(like["commits"], like["previous_commits"], True)
    if not moved:
        return ""
    return f"{moved[1]} on {compared}" if moved[0] else f"level with {compared}"


def _wall_card(card: dict[str, Any], year: int) -> str:
    """A repository's card, small, leading to its own page."""
    name = html.escape(card["name"], quote=True)
    image = html.escape(f"../{card['id']}/{card['card']}", quote=True)
    return (
        f'<a href="{_page_link(card)}" title="{name}"><img loading="lazy" src="{image}" '
        f'width="270" height="270" alt="Repo Wrapped card for {name} in {year}"></a>'
    )


def description(year: int, cards: list[dict[str, Any]]) -> str:
    """The page in a sentence, for where a link to it is shared."""
    when, _ = period(year, cards)
    against = _against(year, cards)
    return (
        f"{when} in {plural(len(cards), 'open source project')}: "
        f"{format_int(totals(cards)['commits'])} commits{', ' + against if against else ''}. "
        "Each project's year on a card."
    )


def index_page(
    year: int,
    cards: list[dict[str, Any]],
    groups: dict[str, str],
    tabs: list[tuple[str, str]],
    site_url: str,
    card: bool,
    generated: str,
) -> str:
    """The page: the totals, what stands out, the table and the cards.
    ``groups`` are the ecosystems, as id -> name; ``tabs`` the gallery's
    other pages, for the nav."""
    when, compared = period(year, cards)
    title = f"Repo Wrapped {year}: {plural(len(cards), 'open source project')}"
    sentence = description(year, cards)
    folder_url = f"{site_url}{FOLDER}/" if site_url else ""
    against = f", compared with {compared}" if compared else ""
    wall = "".join(_wall_card(entry, year) for entry in cards)
    return "".join(
        [
            _header(
                f"{title} | GitStats Gallery",
                share_meta_html(
                    title, sentence, folder_url, INDEX, "index-card.png" if card else ""
                ),
                folder_url,
            ),
            _nav(tabs, f"Wrapped {year}"),
            f"<h1>Repo Wrapped {year}</h1>",
            f'<p class="portfolio-subtitle">{plural(len(cards), "project")} &middot; {when} &middot; '
            f'updated {generated} &middot; <a href="index.json">data</a></p>',
            f'<p class="section-note">One year in each project of the Gallery{against}: its '
            "commits, the people who made them and the days they were made on. Each project "
            "has its card, to save and to share. The numbers describe activity, not worth: a "
            "project is not better for having more commits.</p>",
            stat_tiles_html(_tiles(year, cards)),
            '<div class="table-scroll"><table class="sortable" id="wrapped">'
            "<tr><th>Project</th>"
            + ("<th>Ecosystem</th>" if groups else "")
            + '<th class="num">Commits</th><th class="num">Change</th>'
            '<th class="num">Contributors</th><th class="num">Change</th>'
            '<th class="num">New contributors</th><th class="num">Active days</th>'
            '<th class="num">Longest streak</th><th class="num">Lines changed</th>'
            '<th class="num">Releases</th></tr>'
            + "".join(_row_html(entry, groups) for entry in cards)
            + "</table></div>",
            '<p class="section-note">Commits and lines move by a percentage, people by a '
            f"difference. The fastest growing is looked for among the projects with "
            f"{MIN_BASE_COMMITS} commits or more to grow from. Bots&rsquo; commits are counted; "
            "a bot is not a new contributor.</p>",
            "<h2>The cards</h2>",
            f'<div class="wrapped-wall">{wall}</div>',
            f"{FOOTER}</body>\n</html>\n",
        ]
    )


def index_card(year: int, cards: list[dict[str, Any]]) -> str:
    """The page's share card: the projects with the most commits, as bars."""
    when, _ = period(year, cards)
    top = cards[:6]
    most = max((entry["commits"] for entry in top), default=0) or 1
    bars = "".join(
        f"<div><b>{html.escape(entry['name'])}</b>"
        f'<i style="width:{100 * entry["commits"] / most:.1f}%"></i>'
        f"<span>{format_int(entry['commits'])}</span></div>"
        for entry in top
    )
    return share_card_page(
        f"Repo Wrapped {year}",
        f'<div class="brand">// Repo Wrapped {year}</div>'
        f"<h1>{plural(len(cards), 'open source project')}</h1>"
        f'<p class="sub">Commits in {when}. Each project has its card.</p>'
        f'<div class="bars">{bars}</div>',
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


def write_wrapped(
    gallery_root: str,
    cards: list[dict[str, Any]],
    groups: dict[str, str] | None = None,
    tabs: list[tuple[str, str]] | None = None,
    site_url: str = "",
    card: bool = False,
    version: str = "",
    now: datetime.datetime | None = None,
) -> int | None:
    """Write the page, its data and its share card for ``cards`` (see
    load_cards()); the year they are for, or None, and nothing written,
    without a card. ``groups`` are the ecosystems as id -> name, ``tabs`` the
    gallery's other pages as (address from the gallery, label), ``site_url``
    the gallery's address, ending in "/"; with ``card`` the page points to
    its share card as an image."""
    year, kept = cards_of_the_year(cards)
    if year is None:
        return None
    now = now or datetime.datetime.now()
    meta = {
        "generated_by": f"gitstats {version}".strip(),
        "generated_at": now.astimezone().isoformat(timespec="seconds"),
    }
    data = json.dumps(index_json(year, kept, meta), indent=2, ensure_ascii=False) + "\n"
    _write(gallery_root, f"{FOLDER}/index.json", data)
    page = index_page(
        year, kept, groups or {}, tabs or [], site_url, card, now.strftime("%Y-%m-%d")
    )
    _write(gallery_root, f"{FOLDER}/{INDEX}", page)
    _write(gallery_root, f"{FOLDER}/index-card.html", index_card(year, kept))
    return year
