"""A repository's ``summary.json``: the numbers of a report a portfolio is made from.

Every report folder gets a ``summary.json`` beside its pages. With several
repositories, the portfolio's pages are written from those summaries rather
than from the collectors, so a portfolio can also be made from the files
alone, as the gallery does (scripts/generate_gallery_portfolio.py).

The functions here reduce what the collector gathered to a summary, write it
and read it back. They read collector attributes only and run no git.
"""

import datetime
import json
import logging
import os
import re
from typing import Any

from gitstats.employers import summarize as summarize_organizations
from gitstats.history import _classify_eras
from gitstats.sources import is_source
from gitstats.utils import get_version

logger = logging.getLogger("gitstats")


_SECONDS_PER_DAY = 86400
_ACTIVE_WINDOW_DAYS = 365
# How many months of AI-assisted commits a summary keeps, up to the month it is
# made in: the last four complete quarters, and a year before them.
_AI_MONTHS = 24


def _slugify_repo(path: str) -> str:
    """Turn a repository path into a safe directory/display name.

    Takes the basename (after dropping trailing separators and a trailing
    ``.git``) and keeps only word characters, dots and dashes so the slug can
    never escape the output directory.
    """
    name = os.path.basename(os.path.abspath(path).rstrip("/\\"))
    if name.endswith(".git"):
        name = name[: -len(".git")]
    name = re.sub(r"[^A-Za-z0-9._-]", "-", name).strip(".")
    if not name or set(name) <= {"-", "_"}:
        raise ValueError(f"Cannot derive a repository name from path: {path!r}")
    return name


def _is_bot(name: str) -> bool:
    return name.endswith("[bot]")


def compute_repo_summary(data: Any, report_path: str) -> dict[str, Any]:
    """Reduce one repository's collected data to a small summary dict.

    Pure function over collector attributes — no git calls. Bot accounts
    (names ending in ``[bot]``) are excluded from the people-facing fields,
    the same convention as ``compute_project_history``.
    """
    now = datetime.datetime.now()
    cutoff = now.timestamp() - _ACTIVE_WINDOW_DAYS * _SECONDS_PER_DAY

    authors = {
        name: info
        for name, info in (getattr(data, "authors", {}) or {}).items()
        if isinstance(info, dict) and not _is_bot(name)
    }
    author_commits = {name: int(info.get("commits", 0)) for name, info in authors.items()}
    active_12mo = sum(
        1 for info in authors.values() if int(info.get("last_commit_stamp", 0)) >= cutoff
    )
    top_authors = [
        {"name": name, "commits": commits}
        for name, commits in sorted(author_commits.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    ]

    commits_by_year = {
        int(year): int(commits)
        for year, commits in (getattr(data, "commits_by_year", {}) or {}).items()
    }
    era = ""
    if commits_by_year:
        last_year = max(commits_by_year)
        era = _classify_eras(commits_by_year).get(last_year, "")

    first_stamp = int(getattr(data, "first_commit_stamp", 0) or 0)
    last_stamp = int(getattr(data, "last_commit_stamp", 0) or 0)
    age_days = (last_stamp - first_stamp) // _SECONDS_PER_DAY + 1 if last_stamp else 0

    # a repository without commits has neither; one whose first commit is at
    # the epoch has a first stamp of 0, and a date for it all the same
    def _iso(stamp: int) -> str:
        return datetime.datetime.fromtimestamp(stamp).isoformat(sep=" ") if last_stamp else ""

    recent_months = set()
    year, month = now.year, now.month
    for _ in range(12):
        recent_months.add(f"{year}-{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    commits_by_month = getattr(data, "commits_by_month", {}) or {}
    commits_last_12mo = sum(
        int(count) for key, count in commits_by_month.items() if key in recent_months
    )

    return {
        "schema_version": 1,
        "generated_by": f"gitstats {get_version()}",
        "generated_at": now.astimezone().isoformat(timespec="seconds"),
        "name": getattr(data, "project_name", "") or "",
        "report_path": report_path,
        "first_commit": _iso(first_stamp),
        "last_commit": _iso(last_stamp),
        "age_days": age_days,
        "active_days": len(getattr(data, "active_days", set()) or set()),
        "total_commits": int(getattr(data, "total_commits", 0) or 0),
        "total_authors": len(authors),
        "active_authors_12mo": active_12mo,
        "commits_last_12mo": commits_last_12mo,
        "total_files": int(getattr(data, "total_files", 0) or 0),
        "total_lines": int(getattr(data, "total_lines", 0) or 0),
        "lines_added": int(getattr(data, "total_lines_added", 0) or 0),
        "lines_removed": int(getattr(data, "total_lines_removed", 0) or 0),
        "total_tags": len(getattr(data, "tags", {}) or {}),
        "era": era,
        "top_authors": top_authors,
        "author_commits": author_commits,
        "commits_by_year": {
            str(year): commits for year, commits in sorted(commits_by_year.items())
        },
        "ai_assisted": ai_assisted_summary(data, now),
        "organizations": organizations_summary(data),
        "people_last_12mo": people_summary(data),
        "humans": humans_summary(data),
        # commits by the UTC offset recorded in each: "+0800" -> commits
        "timezones": {
            str(zone): int(commits)
            for zone, commits in sorted((getattr(data, "commits_by_timezone", {}) or {}).items())
        },
        "source_lines": source_lines_summary(data),
    }


def humans_summary(data: Any) -> dict[str, Any] | None:
    """The commits of people, bots left out (see gitstats.employers): by year,
    and how many days have one. None for data collected before that."""
    by_year = getattr(data, "human_commits_by_year", None)
    days = getattr(data, "human_active_days", None)
    if not isinstance(by_year, dict) or not isinstance(days, set):
        return None
    return {
        "commits": sum(by_year.values()),
        "commits_by_year": {str(year): commits for year, commits in sorted(by_year.items())},
        "active_days": len(days),
    }


def source_lines_summary(data: Any) -> dict[str, Any] | None:
    """Lines of the project's own source, leaving out vendored dependencies,
    generated files, test fixtures and lock files (see gitstats.sources):
    ever added, and in the files of the last commit. None when they were not
    counted."""
    added = getattr(data, "source_lines_added", None)
    files = getattr(data, "hotspot_files", None)
    if not isinstance(added, int) or not isinstance(files, dict):
        return None
    return {
        "added": added,
        "current": sum(
            int(info.get("lines", 0)) for path, info in files.items() if is_source(path)
        ),
    }


def people_summary(data: Any) -> dict[str, Any] | None:
    """Who made the commits of the 12 months that end with the last commit:
    how many people, how many of them made their first commit in those
    months, and how few people made half of the commits. Bots, by their
    ``[bot]`` names, are left out. None without commits by month."""
    by_month = getattr(data, "author_of_month", None)
    if not isinstance(by_month, dict) or not by_month:
        return None
    last = max(by_month)
    first = _months_up_to_month(last, 12)[0]
    commits: dict[str, int] = {}
    for month, authors in by_month.items():
        if month >= first:
            for name, count in authors.items():
                if not _is_bot(name):
                    commits[name] = commits.get(name, 0) + int(count)
    year, month = map(int, first.split("-"))
    since = datetime.datetime(year, month, 1).timestamp()
    info = getattr(data, "authors", {}) or {}
    new = sum(
        1
        for name in commits
        if isinstance(info.get(name), dict)
        and int(info[name].get("first_commit_stamp", 0)) >= since
    )
    # the fewest people whose commits add up to half of them, the busiest first
    half, made = 0, 0
    for count in sorted(commits.values(), reverse=True):
        if made * 2 >= sum(commits.values()):
            break
        made += count
        half += 1
    return {
        "from": first,
        "to": last,
        "commits": sum(commits.values()),
        "authors": len(commits),
        "new_authors": new,
        "half_of_commits": half,
    }


def _months_up_to_month(last: str, count: int) -> list[str]:
    """The ``count`` "YYYY-MM" months that end with ``last``, oldest first."""
    year, month = map(int, last.split("-"))
    return _months_up_to(datetime.datetime(year, month, 1), count)


def organizations_summary(data: Any) -> dict[str, Any] | None:
    """Where the commits come from, by the domain of the author's address.

    Every organization, the most commits first, and the commits of the last
    eight quarters by kind of address (organization, one-person domain,
    personal, hidden, unknown, bot). Domains only, never an address. None for
    data collected before addresses were sorted this way. See
    gitstats.employers.
    """
    overview = summarize_organizations(data, limit=None, quarters=8)
    if overview is None:
        return None

    def _day(stamp: int) -> str:
        return datetime.datetime.fromtimestamp(stamp).strftime("%Y-%m-%d")

    return {
        "description": (
            "Commits by the domain of the author's email address. Mail providers anyone can "
            "sign up for count as personal, code hosts' private noreply addresses as hidden, "
            "CI accounts and accounts named [bot] as bots, and a domain only one person "
            "commits from as one_person. A domain says where an address is, not who paid "
            "for the work."
        ),
        "commits": overview["commits"],
        "by_kind": overview["by_kind"],
        "organization_count": overview["organization_count"],
        "last_12mo_from": overview["year_start"],
        "top": [
            {
                "organization": row["organization"],
                "commits": row["commits"],
                "commits_last_12mo": row["commits_last_12mo"],
                "addresses": row["authors"],
                "first_commit": _day(row["first_commit_stamp"]),
                "last_commit": _day(row["last_commit_stamp"]),
            }
            for row in overview["organizations"]
        ],
        "quarters": {quarter["quarter"]: quarter["by_kind"] for quarter in overview["quarters"]},
    }


def _months_up_to(now: datetime.datetime, count: int) -> list[str]:
    """The ``count`` calendar months that end with the month of ``now``, oldest first."""
    months = []
    year, month = now.year, now.month
    for _ in range(count):
        months.append(f"{year:04d}-{month:02d}")
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    return months[::-1]


def ai_assisted_summary(data: Any, now: datetime.datetime) -> dict[str, Any] | None:
    """The commits that name an AI coding assistant, as a summary keeps them.

    In all and by assistant, and for each of the last _AI_MONTHS months next
    to all the commits of that month, so that a share can be worked out for
    any quarter in them. None for data collected before they were counted.
    """
    commits = getattr(data, "ai_assisted_commits", None)
    by_month = getattr(data, "ai_assisted_by_month", None)
    if not isinstance(commits, int) or not isinstance(by_month, dict):
        return None
    all_by_month = getattr(data, "commits_by_month", {}) or {}
    assistants = getattr(data, "ai_assistants", {}) or {}
    months = _months_up_to(now, _AI_MONTHS)
    return {
        "commits": commits,
        "authored": int(getattr(data, "ai_assisted_authored", 0) or 0),
        "assistants": {
            name: int(info.get("commits", 0))
            for name, info in sorted(
                assistants.items(), key=lambda item: (-int(item[1].get("commits", 0)), item[0])
            )
        },
        "by_month": {month: int(by_month.get(month, 0)) for month in months},
        "commits_by_month": {month: int(all_by_month.get(month, 0)) for month in months},
    }


def write_repo_summary(summary: dict[str, Any], path: str) -> None:
    """Write ``summary.json`` into a report directory.

    The filename is fixed; resolving the target and checking it stays under
    the report root guards against directory traversal.
    """
    base = os.path.abspath(path)
    target = os.path.abspath(os.path.join(base, "summary.json"))
    if os.path.commonpath([base, target]) != base:
        raise ValueError(f"Refusing to write outside report directory: {path}")
    with open(target, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)


def load_repo_summaries(outputpath: str) -> list[dict[str, Any]]:
    """Read every ``<outputpath>/*/summary.json`` back into memory.

    Only immediate subdirectories that resolve inside ``outputpath`` are
    considered, so symlinked or crafted entries cannot read outside it.
    """
    base = os.path.realpath(outputpath)
    summaries = []
    try:
        entries = sorted(os.listdir(base))
    except OSError:
        return []
    for entry in entries:
        summary_file = os.path.realpath(os.path.join(base, os.path.basename(entry), "summary.json"))
        try:
            inside_base = os.path.commonpath([base, summary_file]) == base
        except ValueError:
            # e.g. a symlink that resolves onto a different drive on Windows,
            # or a UNC path mixed with a local one: not inside base either way
            inside_base = False
        if not inside_base or not os.path.isfile(summary_file):
            continue
        try:
            with open(summary_file, encoding="utf-8") as f:
                summaries.append(json.load(f))
        except (OSError, ValueError):
            logger.warning(f"Skipping unreadable summary: {summary_file}")
    return summaries
