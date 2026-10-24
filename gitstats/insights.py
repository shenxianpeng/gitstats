"""What stands out about a repository, next to the others of a portfolio.

Up to three facts a maintainer may not know about their own project, each a
sentence with one number, and how it compares: "Node.js has had a commit by a
person on 95% of the days since its first one, 6,110 days in 18 years."

A fact is said only where the project is unusual: in the top or bottom 15%
of the portfolio's projects on it. Six kinds are looked at, chosen by reading
a first set of candidates over the Gallery's 107 projects and keeping those
that told maintainers something new (the share of one-time contributors, for
one, is high everywhere and surprised no one):

- the AI-assisted share, from a year ago to now;
- the days with a commit by a person, of all days;
- the last 12 months against the busiest year, people's commits only;
- how much of the project's own source ever written is still there;
- how much of its history comes from one time zone;
- how much of its organizations' commits come from one company.

Bots are left out where they would fill the calendar or a year, and
vendored, generated and lock files where they would swamp the lines. A fact
whose data is known to mislead is not said: a time zone that is UTC+0 for
most commits is more likely a tool's setting than a place.
"""

from __future__ import annotations

import html
import statistics
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from gitstats.compare import ordinal
from gitstats.report_creator import html_header

EXTREME = 0.85  # in the top or bottom 15% of the portfolio
MIN_VALUES = 10  # fewer projects with a value, and a place says nothing
MOST = 3

# Domains of foundations and of open source projects themselves: an address
# there says who the person works with, not who pays them.
FOUNDATION_DOMAINS = frozenset(
    {
        "apache.org", "cncf.io", "eclipse.org", "freebsd.org", "gnu.org", "golang.org",
        "kernel.org", "linuxfoundation.org", "mozilla.org", "nodejs.org", "numfocus.org",
        "openjsf.org", "openssf.org", "postgresql.org", "python.org", "rust-lang.org",
    }
)  # fmt: skip


def pct(value: float) -> str:
    """0.954 -> "95%", 0.004 -> "0.4%"."""
    return f"{100 * value:.0f}%" if value >= 0.01 or value == 0 else f"{100 * value:.1f}%"


def _year(text: Any) -> int | None:
    try:
        return int(str(text)[:4])
    except ValueError:
        return None


def _flat(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


# ── the measures: one value per summary, None when it can't be worked out ──


def ai_change(summary: dict[str, Any]) -> tuple[float, float] | None:
    """The AI-assisted share of the first three of the last twelve months, and
    of the last three: each with 30 commits at least."""
    ai = summary.get("ai_assisted")
    if not isinstance(ai, dict):
        return None
    by_month, all_by_month = ai.get("by_month") or {}, ai.get("commits_by_month") or {}
    months = sorted(all_by_month)
    if len(months) < 12:
        return None
    first, last = months[:3], months[-3:]
    before = sum(int(all_by_month[m]) for m in first)
    after = sum(int(all_by_month[m]) for m in last)
    if before < 30 or after < 30:
        return None
    return (
        sum(int(by_month.get(m, 0)) for m in first) / before,
        sum(int(by_month.get(m, 0)) for m in last) / after,
    )


def ai_rise(summary: dict[str, Any]) -> float | None:
    found = ai_change(summary)
    return found[1] - found[0] if found and found[1] > found[0] else None


def active_days(summary: dict[str, Any]) -> float | None:
    """Days with a commit by a person, of all days from the first commit."""
    humans = summary.get("humans")
    age = int(summary.get("age_days", 0) or 0)
    if not isinstance(humans, dict) or age < 3 * 365:
        return None
    return int(humans.get("active_days", 0)) / age


def busiest_year(summary: dict[str, Any]) -> tuple[int, int] | None:
    """The busiest full year by people's commits, before the last commit's
    year; with four full years at least."""
    humans = summary.get("humans")
    last = _year(summary.get("last_commit", ""))
    if not isinstance(humans, dict) or last is None:
        return None
    years = {
        int(year): int(commits)
        for year, commits in (humans.get("commits_by_year") or {}).items()
        if int(year) < last
    }
    if len(years) < 4:
        return None
    year = max(years, key=lambda y: (years[y], -y))
    return year, years[year]


def recent_commits(summary: dict[str, Any]) -> int | None:
    people = summary.get("people_last_12mo")
    if not isinstance(people, dict) or people.get("commits") is None:
        return None
    return int(people["commits"])


def versus_peak(summary: dict[str, Any]) -> float | None:
    """People's commits of the last 12 months, against their busiest year."""
    peak = busiest_year(summary)
    recent = recent_commits(summary)
    if not peak or recent is None or peak[1] < 50:
        return None
    return recent / peak[1]


def source_kept(summary: dict[str, Any]) -> float | None:
    """Of all the lines ever added to the project's own source, those still
    there. Above 90%, the code was most likely brought in whole, not written
    here, and the measure says nothing."""
    source = summary.get("source_lines")
    if not isinstance(source, dict) or int(summary.get("age_days", 0) or 0) < 3 * 365:
        return None
    added = int(source.get("added", 0))
    if added < 1000:
        return None
    kept = int(source.get("current", 0)) / added
    return kept if kept <= 0.9 else None


def _utc(zone: str) -> bool:
    return zone.replace("UTC", "").replace(":", "") in ("+0000", "-0000", "")


def top_zone(summary: dict[str, Any]) -> tuple[str, float, int] | None:
    """The time zone with the most commits, its share, and how many zones
    have commits; None for fewer than 500 commits, or when UTC+0 holds most
    of them (a tool's setting, more likely than a place)."""
    zones = {k: int(v) for k, v in (summary.get("timezones") or {}).items() if int(v)}
    total = sum(zones.values())
    if total < 500:
        return None
    if sum(v for k, v in zones.items() if _utc(k)) / total > 0.6:
        return None
    zone = max(zones, key=lambda k: (zones[k], k))
    if _utc(zone):
        return None
    return zone, zones[zone] / total, len(zones)


def zone_share(summary: dict[str, Any]) -> float | None:
    found = top_zone(summary)
    return found[1] if found else None


def own_domain(summary: dict[str, Any], domain: str) -> bool:
    """Whether a domain is a foundation's or the project's own (cilium.io for
    Cilium, pytorch.org for PyTorch, curl.se for curl), not an employer."""
    if domain in FOUNDATION_DOMAINS:
        return True
    label = _flat(domain.split(".")[0])
    names = {
        _flat(str(summary.get("name", ""))),
        _flat(str(summary.get("report_path", "")).split("/")[0]),
    }
    owner, _, repository = str(summary.get("repository", "")).partition("/")
    names |= {_flat(owner), _flat(repository)} - {""}
    return label in names or any(name.startswith(label) for name in names if len(label) >= 4)


def employers(summary: dict[str, Any]) -> list[dict[str, Any]]:
    """The organizations with commits in the last 12 months, not the
    project's own or a foundation's, the most first."""
    block = summary.get("organizations")
    if not isinstance(block, dict):
        return []
    rows = [
        row
        for row in block.get("top") or []
        if row.get("commits_last_12mo") and not own_domain(summary, row["organization"])
    ]
    return sorted(rows, key=lambda row: -int(row["commits_last_12mo"]))


def one_employer(summary: dict[str, Any]) -> float | None:
    """The share of one company in the commits from companies' addresses of
    the last 12 months; with 100 of them, a fifth of all commits, at least."""
    rows = employers(summary)
    total = sum(int(row["commits_last_12mo"]) for row in rows)
    recent = int(summary.get("commits_last_12mo", 0) or 0)
    if total < 100 or total < 0.2 * max(recent, 1):
        return None
    return int(rows[0]["commits_last_12mo"]) / total


# ── the facts ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Kind:
    id: str
    label: str
    measure: Callable[[dict[str, Any]], float | None]
    tail: str  # "high", "low" or "both": which end of the portfolio is news
    weight: float  # how often it told maintainers something new
    big: Callable[[dict[str, Any], float], str]  # the number shown large
    say: Callable[[dict[str, Any], float], str]
    median: Callable[[float], str]


def _name(summary: dict[str, Any]) -> str:
    return str(summary.get("name", "") or "")


def _owns(summary: dict[str, Any]) -> str:
    """ "Kubernetes's": a name is singular, whatever its last letter."""
    return f"{_name(summary)}'s"


def _zone(zone: str) -> str:
    """ "+0800" -> "UTC+08:00"."""
    raw = zone.replace("UTC", "")
    if len(raw) == 5 and raw[0] in "+-":
        return f"UTC{raw[:3]}:{raw[3:]}"
    return zone


def _say_ai(s: dict[str, Any], v: float) -> str:
    before, after = ai_change(s)  # type: ignore[misc]
    return (
        f"The share of {_owns(s)} commits that name an AI coding assistant went from "
        f"{pct(before)} to {pct(after)} in a year."
    )


def _say_days(s: dict[str, Any], v: float) -> str:
    humans = s["humans"]
    years = int(s["age_days"]) / 365.25
    return (
        f"{_name(s)} has had a commit by a person on {pct(v)} of the days since its first "
        f"one: {int(humans['active_days']):,} days in {years:.0f} years."
    )


def _say_peak(s: dict[str, Any], v: float) -> str:
    year, commits = busiest_year(s)  # type: ignore[misc]
    recent = recent_commits(s)
    if v >= 1:
        return (
            f"{_owns(s)} last 12 months were its busiest yet: {recent:,} commits by people, "
            f"more than in any full year before ({commits:,} in {year})."
        )
    return (
        f"People made {pct(v)} as many commits to {_name(s)} in the last 12 months as in "
        f"{year}, its busiest year ({recent:,} against {commits:,})."
    )


def _say_source(s: dict[str, Any], v: float) -> str:
    added = int(s["source_lines"]["added"])
    if v < 0.5:
        return (
            f"Of the {added:,} lines ever written into {_owns(s)} own source, {pct(v)} are "
            "still there; the rest were rewritten or removed."
        )
    return (
        f"{pct(v)} of the {added:,} lines ever written into {_owns(s)} own source are still there."
    )


def _say_zone(s: dict[str, Any], v: float) -> str:
    zone, share, count = top_zone(s)  # type: ignore[misc]
    return (
        f"{pct(share)} of {_owns(s)} commits were made in one time zone, {_zone(zone)}, "
        f"of the {count} it has commits from."
    )


def _say_employer(s: dict[str, Any], v: float) -> str:
    return (
        f"Of {_owns(s)} commits from company addresses in the last 12 months, {pct(v)} "
        f"came from one company: {employers(s)[0]['organization']}."
    )


KINDS: tuple[Kind, ...] = (
    Kind("ai", "AI-assisted commits", ai_rise, "high", 1.0,
         lambda s, v: pct(ai_change(s)[1]),  # type: ignore[index]
         _say_ai, lambda m: f"in the median project it rose by {100 * m:.0f} points"),
    Kind("days", "Days with a commit", active_days, "high", 1.0,
         lambda s, v: pct(v), _say_days, lambda m: f"the median project: {pct(m)} of days"),
    Kind("employer", "One company", one_employer, "high", 1.0,
         lambda s, v: pct(v), _say_employer, lambda m: f"the median project: {pct(m)}"),
    Kind("zone", "One time zone", zone_share, "high", 0.9,
         lambda s, v: pct(v), _say_zone, lambda m: f"the median project: {pct(m)}"),
    Kind("peak", "Against its busiest year", versus_peak, "both", 0.85,
         # more than in its busiest year reads as a multiple: 1.6×, not 164%
         lambda s, v: f"{v:.1f}×" if v >= 1 else pct(v), _say_peak,
         lambda m: f"the median project made {pct(m)} of its busiest year"),
    Kind("source", "Code still there", source_kept, "both", 0.8,
         lambda s, v: pct(v), _say_source, lambda m: f"the median project: {pct(m)}"),
)  # fmt: skip


def _place(value: float, values: list[float]) -> float:
    """Where a value sits among values, 0 (lowest) to 1 (highest)."""
    below = sum(1 for other in values if other < value)
    equal = sum(1 for other in values if other == value)
    return (below + 0.5 * equal) / len(values)


def facts(summaries: list[dict[str, Any]], scope: str = "projects") -> list[list[dict[str, Any]]]:
    """For each summary, in order, its facts: at most three, the most unusual
    first, each of a different kind. A fact is ``{kind, label, value, big,
    sentence, compared, score}``; ``compared`` places it among the
    ``scope`` ("the 107 Gallery projects" reads "of the 107 projects")."""
    values = {kind.id: [kind.measure(summary) for summary in summaries] for kind in KINDS}
    known = {k: [v for v in vals if v is not None] for k, vals in values.items()}
    out = []
    for index, summary in enumerate(summaries):
        found = []
        for kind in KINDS:
            value = values[kind.id][index]
            pool = known[kind.id]
            if value is None or len(pool) < MIN_VALUES:
                continue
            place = _place(value, pool)
            high = place >= 0.5
            if (kind.tail == "high" and not high) or (kind.tail == "low" and high):
                continue
            extreme = place if high else 1 - place
            if extreme < EXTREME:
                continue
            ordered = sorted(pool, reverse=high)
            rank = ordered.index(value) + 1
            word = "highest" if high else "lowest"
            compared = (
                f"The {word} of the {len(pool)} {scope}."
                if rank == 1
                else f"{ordinal(rank)} {word} of {len(pool)}; "
                f"{kind.median(statistics.median(pool))}."
            )
            found.append(
                {
                    "kind": kind.id,
                    "label": kind.label,
                    "value": value,
                    "big": kind.big(summary, value),
                    "sentence": kind.say(summary, value),
                    "compared": compared,
                    "score": round(extreme * kind.weight, 4),
                }
            )
        found.sort(key=lambda fact: (-fact["score"], fact["kind"]))
        out.append(found[:MOST])
    return out


# ── how a page shows them ─────────────────────────────────────────────────


def facts_html(found: list[dict[str, Any]]) -> str:
    """The facts as a list: each its number large, its sentence, and how it
    compares."""
    items = "".join(
        '<li class="insight">'
        f'<span class="insight-big">{html.escape(fact["big"])}</span>'
        f'<div><span class="insight-label">{html.escape(fact["label"])}</span>'
        f'<p class="insight-sentence">{html.escape(fact["sentence"])}</p>'
        f'<p class="insight-compared">{html.escape(fact["compared"])}</p></div></li>'
        for fact in found
    )
    return f'<ul class="insights">{items}</ul>'


def overview_html(name: str, found: list[dict[str, Any]], others: int, portfolio: str) -> str:
    """The section a portfolio puts at the top of a report's overview."""
    if not found:
        return ""
    return (
        '<section class="insights-section" id="what-stands-out">'
        f"{html_header(2, 'What stands out')}"
        f'<p class="section-note">Next to the {others} other projects of '
        f'<a href="../index.html">{html.escape(portfolio)}</a>: where '
        f"{html.escape(name)} is in the top or bottom 15%.</p>"
        f"{facts_html(found)}"
        f'<p class="more-link"><a href="compare.html">How {html.escape(name)} compares, '
        "measure by measure &rarr;</a></p></section>"
    )
