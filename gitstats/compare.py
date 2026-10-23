"""How one repository of a portfolio compares with the others.

A number alone says little: 600 commits a year is a lot for a library and
little for a compiler. Next to the same number for the projects around it, it
says where a project stands. This module works out a few measures from each
repository's summary.json, ranks every repository on each, and says in a
sentence where one stands out.

The measures are chosen to be hard to game and plain to read, and none of
them is called good or bad: more commits, or a larger share of AI-assisted
ones, is a position among peers, not a score. Ranks are among the projects
of the same group (an ecosystem of the Gallery) and among all of them.
"""

from __future__ import annotations

import html
import math
from dataclasses import dataclass
from typing import Any

# fewer repositories than this, and a rank says nothing
MIN_REPOSITORIES = 5


@dataclass(frozen=True)
class Measure:
    """One measure: how a value is shown and said."""

    id: str
    label: str
    # how sentences name it: "had <more> than any other ...", "is 2nd for <short>",
    # "also had <most>"
    more: str
    short: str
    most: str
    # "had <fewer> than any other ...", for a project last on its best measure
    fewer: str
    definition: str
    share: bool = False  # a fraction, shown as a percentage, on a linear scale


MEASURES: tuple[Measure, ...] = (
    Measure(
        "commits",
        "Commits",
        "more commits in the last 12 months",
        "commits",
        "the most commits",
        "fewer commits in the last 12 months",
        "Commits in the 12 months up to the last one.",
    ),
    Measure(
        "authors",
        "Contributors",
        "more contributors in the last 12 months",
        "contributors",
        "the most contributors",
        "fewer contributors in the last 12 months",
        "People who made a commit in those 12 months; bots are left out.",
    ),
    Measure(
        "new_authors",
        "New contributors",
        "more new contributors in the last 12 months",
        "new contributors",
        "the most new contributors",
        "fewer new contributors in the last 12 months",
        "Of them, those whose first commit to the project was in those 12 months.",
    ),
    Measure(
        "half_of_commits",
        "Half the commits by",
        "more people behind half of its commits",
        "how widely its commits are spread",
        "the most people behind half of its commits",
        "fewer people behind half of its commits",
        "The fewest people whose commits add up to half of those 12 months': "
        "how far the work is spread.",
    ),
    Measure(
        "organizations",
        "Organizations",
        "more organizations committing to it",
        "organizations committing",
        "the most organizations committing",
        "fewer organizations committing to it",
        "Organizations whose addresses committed in those 12 months, by email domain; "
        "a domain only one person uses is not one.",
    ),
    Measure(
        "ai_share",
        "AI-assisted",
        "a larger share of commits that name an AI coding assistant",
        "AI-assisted commits",
        "the largest share of AI-assisted commits",
        "a smaller share of commits that name an AI coding assistant",
        "The share of the last four quarters' commits that name an AI coding assistant; "
        "a lower bound.",
        share=True,
    ),
)
MEASURE_IDS = tuple(measure.id for measure in MEASURES)

# The order a sentence prefers measures in, when two places are as high: who
# works on a project first, how much after. The AI-assisted share is named
# only for a first place, or it would crowd out the rest: its small
# differences put some project near the top of almost every group.
SENTENCE_ORDER = (
    "new_authors",
    "half_of_commits",
    "organizations",
    "authors",
    "commits",
    "ai_share",
)
FIRST_ONLY = ("ai_share",)
# Measures that rise and fall together: a second sentence about another of
# them would say nothing new.
FAMILIES = ({"commits", "authors", "new_authors"},)


def _related(first: str, second: str) -> bool:
    return any(first in family and second in family for family in FAMILIES)


def measures_of(summary: dict[str, Any], quarters: list[list[str]]) -> dict[str, float | None]:
    """A repository's value of each measure, None where its summary doesn't
    have what the measure needs. ``quarters`` are the months of the last
    four complete quarters, for the AI-assisted share."""
    block = summary.get("people_last_12mo")
    people: dict[str, Any] = block if isinstance(block, dict) else {}
    organizations = summary.get("organizations")
    values: dict[str, float | None] = {
        "commits": float(summary.get("commits_last_12mo", 0) or 0),
        # summaries from before people_last_12mo counted the active authors
        "authors": _number(people, "authors")
        if "authors" in people
        else _number(summary, "active_authors_12mo"),
        "new_authors": _number(people, "new_authors"),
        "half_of_commits": _number(people, "half_of_commits") if people.get("commits") else None,
        "organizations": None,
        "ai_share": None,
    }
    if isinstance(organizations, dict):
        values["organizations"] = float(
            sum(1 for row in organizations.get("top") or [] if row.get("commits_last_12mo"))
        )
    ai = summary.get("ai_assisted")
    if isinstance(ai, dict):
        by_month, all_by_month = ai.get("by_month") or {}, ai.get("commits_by_month") or {}
        months = [month for quarter in quarters for month in quarter]
        assisted = sum(int(by_month.get(month, 0)) for month in months)
        total = sum(int(all_by_month.get(month, 0)) for month in months)
        values["ai_share"] = assisted / total if total else None
    return values


def _number(block: dict[str, Any], key: str) -> float | None:
    value = block.get(key)
    return float(value) if isinstance(value, int | float) else None


def rank(value: float | None, values: list[float | None]) -> tuple[int, int] | None:
    """(rank, of how many) of ``value`` among ``values``, the largest first;
    equal values share a rank. None when there is no value."""
    known = [other for other in values if other is not None]
    if value is None or not known:
        return None
    return 1 + sum(1 for other in known if other > value), len(known)


def ordinal(number: int) -> str:
    """1 -> "1st", 12 -> "12th", 22 -> "22nd"."""
    if 10 <= number % 100 <= 20:
        return f"{number}th"
    return f"{number}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(number % 10, 'th') }"


def shared(value: float | None, values: list[float | None]) -> bool:
    """Whether another of ``values`` (``value`` among them) equals ``value``."""
    return value is not None and sum(1 for other in values if other == value) > 1


def _alone(value: float | None, values: list[float | None]) -> bool:
    """Whether ``value`` is above zero and no other of ``values`` equals it."""
    return value is not None and value > 0 and not shared(value, values)


def comparisons(summaries: list[dict[str, Any]], quarters: list[list[str]]) -> list[dict[str, Any]]:
    """Each repository's values, and its rank on each measure among its
    group's repositories and among all."""
    values = [measures_of(summary, quarters) for summary in summaries]
    rows = []
    for summary, own in zip(summaries, values):
        group = summary.get("group") or ""
        peers = [
            other for other_summary, other in zip(summaries, values)
            if group and other_summary.get("group") == group
        ]  # fmt: skip
        # the repositories a sentence about it compares it with
        around = peers if group else values
        alone = {
            measure: _alone(own[measure], [other[measure] for other in around])
            for measure in MEASURE_IDS
        }
        rows.append(
            {
                "summary": summary,
                "values": own,
                # a place it holds alone, with a value above zero: one a sentence can name
                "alone": alone,
                "ranks": {
                    measure: {
                        "group": rank(own[measure], [peer[measure] for peer in peers])
                        if group
                        else None,
                        "all": rank(own[measure], [other[measure] for other in values]),
                    }
                    for measure in MEASURE_IDS
                },
            }
        )
    return rows


def headline(row: dict[str, Any], projects: str) -> str:
    """One or two sentences on where a repository stands out most, among its
    group's ``projects`` ("Python open source projects"), or among all when
    "". Plain facts: "most" is a place, not praise."""
    name = row["summary"].get("name", "")
    scope = "group" if projects else "all"
    projects = projects or "repositories"
    standing = []
    for measure in MEASURES:
        place = row["ranks"][measure.id][scope]
        if place and place[1] >= MIN_REPOSITORIES and row["alone"][measure.id]:
            standing.append(((place[0] - 1) / (place[1] - 1), place, measure))
    if not standing:
        return ""
    standing.sort(key=lambda item: (item[0], SENTENCE_ORDER.index(item[2].id)))
    high = [
        item
        for item in standing
        if item[0] <= 0.25 and (item[1][0] == 1 or item[2].id not in FIRST_ONLY)
    ]
    top = high[:1]
    for item in high[1:]:
        if not _related(top[0][2].id, item[2].id):
            top.append(item)
            break
    if not top:
        # its best place, on a measure a sentence names at any place
        position, (place, of), measure = next(
            (item for item in standing if item[2].id not in FIRST_ONLY), standing[0]
        )
        if place == of:
            # last even on its best measure: say so plainly
            return f"{name} had {measure.fewer} than any other of the {of} {projects}."
        where = (
            f"sits in the middle of the {of} {projects}"
            if position <= 0.6
            else f"ranks below most of the {of} {projects} on every measure here"
        )
        return f"{name} {where}; its highest place is {ordinal(place)}, for {measure.short}."
    _, (place, of), measure = top[0]
    if place == 1:
        text = f"{name} had {measure.more} than any other of the {of} {projects}."
    else:
        text = f"{name} is {ordinal(place)} of the {of} {projects} for {measure.short}."
    if len(top) > 1:
        _, (place, _), measure = top[1]
        if place == 1:
            text += f" It also had {measure.most}."
        else:
            text += f" It is also {ordinal(place)} for {measure.short}."
    return text


def show(value: float | None, measure: Measure) -> str:
    """A value as the page shows it."""
    if value is None:
        return "&ndash;"
    if measure.share:
        if value and value < 0.0005:
            return "&lt;0.1%"
        return f"{100 * value:.1f}%"
    return f"{int(value):,}"


def _position(value: float, top: float, measure: Measure) -> float:
    """Where a value sits on a strip, 0 to 1: shares on a straight scale,
    counts on a logarithmic one, so that 50 and 5,000 both have room."""
    if top <= 0:
        return 0.0
    if measure.share:
        return value / top
    return math.log1p(value) / math.log1p(top)


STRIP_WIDTH = 600
STRIP_HEIGHT = 32


def strip_svg(
    measure: Measure,
    own: float | None,
    group: list[float | None],
    others: list[float | None],
) -> str:
    """Every repository as a dot on one line: all of them faint, the group's
    darker, this one in the accent color and larger. Colors come from the
    stylesheet, so the strip follows the theme."""
    known = [value for value in (*group, *others) if value is not None]
    if own is None or not known:
        return ""
    top = max(known)
    pad = 8
    width = STRIP_WIDTH - 2 * pad
    middle = STRIP_HEIGHT / 2

    def x(value: float) -> float:
        return pad + width * _position(value, top, measure)

    dots = [
        f'<circle class="strip-all" cx="{x(value):.1f}" cy="{middle}" r="4"/>'
        for value in others
        if value is not None
    ]
    dots += [
        f'<circle class="strip-group" cx="{x(value):.1f}" cy="{middle}" r="4"/>'
        for value in group
        if value is not None
    ]
    dots.append(f'<circle class="strip-own" cx="{x(own):.1f}" cy="{middle}" r="7"/>')
    return (
        '<div class="compare-strip">'
        f'<svg class="strip" viewBox="0 0 {STRIP_WIDTH} {STRIP_HEIGHT}" role="img" '
        f'aria-label="{html.escape(measure.label)}: {show(own, measure)} among {len(known)}">'
        f'<line class="strip-axis" x1="{pad}" y1="{middle}" x2="{STRIP_WIDTH - pad}" '
        f'y2="{middle}"/>' + "".join(dots) + "</svg>"
        # the scale's two ends, as text that keeps its size on a phone
        f'<div class="strip-scale"><span>{"0%" if measure.share else "0"}</span>'
        f"<span>{show(top, measure)}</span></div></div>"
    )


def card_rows(row: dict[str, Any], scope: str) -> list[tuple[str, float, str]]:
    """The share card's rows: each measure, how far up its peers it is (1 for
    the first, 0 for the last), and its rank."""
    rows = []
    for measure in MEASURES:
        place = row["ranks"][measure.id][scope]
        if place and place[1] > 1:
            rows.append(
                (
                    measure.label,
                    1 - (place[0] - 1) / (place[1] - 1),
                    f"{ordinal(place[0])} / {place[1]}",
                )
            )
    return rows
