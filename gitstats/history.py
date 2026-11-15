# Copyright (c) 2007-2014 Heikki Hokkanen <hoxu@users.sf.net> & others contributors
# GPLv2 / GPLv3
# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
"""A repository's history as the report tells it: one account per year, with
the era each year belongs to, and the chapters an AI chronicle is split into.

Computed from what the collector gathered: no git is run here.
"""

import datetime
import re
from typing import Any

from gitstats.utils import is_bot


def _classify_eras(year_commits: dict[int, int]) -> dict[int, str]:
    """Assign each year of the project's span one era label.

    Labels are relative to the repository's own baseline (the median of its
    non-zero years), so a "surge" in a small project and in a huge one mean
    the same thing: well above what is normal *for that project*. The span is
    contiguous — years without commits appear as "dormant" instead of being
    skipped, because silence is part of the story.

    Priority per year: birth > dormant > peak > revival > surge > quiet > steady.
    """
    if not year_commits:
        return {}
    first, last = min(year_commits), max(year_commits)
    span = {y: year_commits.get(y, 0) for y in range(first, last + 1)}
    active = [c for c in span.values() if c > 0]
    med = sorted(active)[len(active) // 2]
    peak_year = max(span, key=lambda y: (span[y], y))
    # With under three active years there is no meaningful baseline to
    # compare against, so only the structural labels apply.
    tiny = len(active) < 3

    eras: dict[int, str] = {}
    prev = ""
    for y in sorted(span):
        c = span[y]
        if y == first:
            era = "birth"
        elif c == 0:
            era = "dormant"
        elif y == peak_year and not tiny:
            era = "peak"
        elif prev in ("dormant", "quiet") and c >= med:
            era = "revival"
        elif not tiny and c >= 1.6 * med:
            era = "surge"
        elif not tiny and c <= 0.35 * med:
            era = "quiet"
        else:
            era = "steady"
        eras[y] = era
        prev = era
    return eras


def compute_project_history(data: Any) -> dict[str, Any]:
    """Derive a chronological, per-year account of the project from collected data.

    Everything here is computed from data the collector already gathered —
    no extra git traffic. Bot accounts (names ending in ``[bot]``) are left
    out of the people-facing fields. Returns a dict with:
        years: one entry per calendar year of the span (gap years included),
               each carrying commits, line deltas, author counts, the top
               author, newcomers (authors whose first commit fell in that
               year, most active first) and the releases tagged that year;
        first_year, last_year, peak_year, total_releases.
    """
    year_commits: dict[int, int] = dict(getattr(data, "commits_by_year", {}) or {})
    if not year_commits:
        return {
            "years": [],
            "first_year": None,
            "last_year": None,
            "peak_year": None,
            "total_releases": 0,
        }

    eras = _classify_eras(year_commits)
    author_of_year = getattr(data, "author_of_year", {}) or {}
    lines_added = getattr(data, "lines_added_by_year", {}) or {}
    lines_removed = getattr(data, "lines_removed_by_year", {}) or {}

    # Authors whose first commit fell in each year (bots excluded).
    newcomers_by_year: dict[int, list[str]] = {}
    for name, info in (getattr(data, "authors", {}) or {}).items():
        stamp = info.get("first_commit_stamp") if isinstance(info, dict) else None
        if not stamp or is_bot(name):
            continue
        yy = datetime.datetime.fromtimestamp(stamp).year
        newcomers_by_year.setdefault(yy, []).append(name)

    # Releases (tags) by the year they were made.
    releases_by_year: dict[int, list[tuple[str, str]]] = {}
    total_releases = 0
    for tag, info in (getattr(data, "tags", {}) or {}).items():
        date = str(info.get("date", ""))
        if len(date) >= 4 and date[:4].isdigit():
            releases_by_year.setdefault(int(date[:4]), []).append((date, tag))
            total_releases += 1

    total_commits = sum(year_commits.values())
    years: list[dict[str, Any]] = []
    for y in sorted(eras):
        commits = year_commits.get(y, 0)
        year_authors = author_of_year.get(y, {})
        humans = {a: c for a, c in year_authors.items() if not a.endswith("[bot]")}
        ranked = sorted(humans or year_authors, key=lambda a: (year_authors[a], a), reverse=True)
        top_author = ranked[0] if ranked else ""
        newcomers = sorted(
            newcomers_by_year.get(y, []),
            key=lambda a: (year_authors.get(a, 0), a),
            reverse=True,
        )
        years.append(
            {
                "year": y,
                "era": eras[y],
                "commits": commits,
                "commits_pct": round(100.0 * commits / total_commits, 1) if total_commits else 0.0,
                "lines_added": lines_added.get(y, 0),
                "lines_removed": lines_removed.get(y, 0),
                "active_authors": len(year_authors),
                "top_author": top_author,
                "top_author_commits": year_authors.get(top_author, 0),
                "newcomers": newcomers,
                "releases": [t for _, t in sorted(releases_by_year.get(y, []))],
            }
        )

    return {
        "years": years,
        "first_year": years[0]["year"],
        "last_year": years[-1]["year"],
        "peak_year": max(year_commits, key=lambda y: (year_commits[y], y)),
        "total_releases": total_releases,
    }


def parse_chronicle(text: str) -> dict[str, Any]:
    """Split AI chronicle text into a prologue and per-year chapters.

    Expects ``[PROLOGUE]`` and ``[YEAR <n>] <title>`` marker lines; everything
    between markers belongs to the preceding one. Tolerant by design: years
    the model skipped simply have no chapter, and text with no markers at all
    yields no chapters so the caller can fall back to showing it whole.
    """
    prologue = ""
    chapters: dict[int, dict[str, str]] = {}
    current: dict[str, str] | None = None
    in_prologue = False
    prologue_lines: list[str] = []
    marker = re.compile(r"^\[YEAR\s+(\d{4})\]\s*(.*)$")

    for raw_line in text.splitlines():
        line = raw_line.strip()
        m = marker.match(line)
        if m:
            in_prologue = False
            current = {"title": m.group(2).strip(), "story": ""}
            chapters[int(m.group(1))] = current
        elif line == "[PROLOGUE]":
            in_prologue = True
            current = None
        elif in_prologue:
            prologue_lines.append(line)
        elif current is not None and line:
            current["story"] = (current["story"] + " " + line).strip()

    prologue = " ".join(line for line in prologue_lines if line).strip()
    return {"prologue": prologue, "chapters": chapters}
