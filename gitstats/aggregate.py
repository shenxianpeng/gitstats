"""Multi-repository aggregation: per-repo summaries and the portfolio page.

When gitstats is run with several repositories, each repository gets its own
full report in a subdirectory and this module assembles the portfolio view:
a machine-readable ``summary.json`` per repository plus one aggregate
``index.html`` at the output root with a sortable overview table.

The computation functions are pure — they read collector attributes only and
issue no git commands — mirroring ``compute_project_history`` and
``compute_code_ownership`` in ``report_creator``.
"""

import csv
import datetime
import html
import io
import json
import logging
import os
import re
import shutil
from typing import Any

from gitstats import compare, insights, load_config
from gitstats.badge import compact_count, endpoint_json, render_badge
from gitstats.employers import KIND_LABELS, ORGANIZATION
from gitstats.employers import KINDS as ORGANIZATION_KINDS
from gitstats.employers import summarize as summarize_organizations
from gitstats.report_creator import (
    AI_ASSISTED_COUNTED,
    FOOTER,
    INSIGHTS_END,
    INSIGHTS_START,
    NAV_END,
    NAV_START,
    REPORT_BRAND,
    SKIP_LINK,
    THEME_INIT_SCRIPT,
    THEME_SCRIPT,
    THEME_TOGGLE_BUTTON,
    _classify_eras,
    html_header,
    nav_link,
    page_title,
    plural,
    share_card_page,
    share_meta_html,
    share_text,
    stat_tiles_html,
)
from gitstats.sources import is_source
from gitstats.utils import format_int, get_version

logger = logging.getLogger("gitstats")

conf = load_config()

_SECONDS_PER_DAY = 86400
_ACTIVE_WINDOW_DAYS = 365
# How many months of AI-assisted commits a summary keeps, up to the month it is
# made in: the last four complete quarters, and a year before them.
_AI_MONTHS = 24
_MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


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


ORGANIZATIONS_DATA_DESCRIPTION = (
    "Commits by the domain of the author's email address, added up across the "
    "repositories. An organization's commits in the last 12 months are those of the 12 "
    "months that end with each repository's last commit. A domain only one person commits "
    "from is counted apart, as are mail providers anyone can sign up for, code hosts' "
    "private noreply addresses and bots. A domain says where an address is, not who paid "
    "for the work."
)


def organizations_dataset(
    summaries: list[dict[str, Any]], now: datetime.datetime, version: str = ""
) -> dict[str, Any]:
    """The counts of the organizations page, as data, put together by gitstats
    ``version`` (this one's, when not given).

    ``organizations``: each organization of any repository, with its commits
    added up across them, the most in the last 12 months first.
    ``repositories``: for each repository whose summary sorts its commits
    this way, its commits of the last four complete quarters by kind of
    address, and its organizations with the most commits in the last 12
    months.
    """
    quarters = [quarter_id(months) for _, months in last_quarters(now)]
    totals: dict[str, dict[str, Any]] = {}
    repositories = []
    for summary in summaries:
        block = summary.get("organizations")
        if not isinstance(block, dict):
            continue
        name = str(summary.get("name", "") or "")
        by_kind = dict.fromkeys(ORGANIZATION_KINDS, 0)
        for quarter in quarters:
            for kind, commits in (block.get("quarters") or {}).get(quarter, {}).items():
                by_kind[kind] = by_kind.get(kind, 0) + int(commits)
        rows = block.get("top") or []
        for row in rows:
            total = totals.setdefault(
                row["organization"],
                {"commits": 0, "commits_last_12mo": 0, "repositories": [], "by_repository": []},
            )
            total["commits"] += int(row["commits"])
            total["commits_last_12mo"] += int(row["commits_last_12mo"])
            total["repositories"].append(name)
            total["by_repository"].append(
                {
                    "name": name,
                    "report": summary.get("report_path", "") or "",
                    "commits": int(row["commits"]),
                    "commits_last_12mo": int(row["commits_last_12mo"]),
                    "addresses": int(row.get("addresses", 0) or 0),
                    "first_commit": row.get("first_commit", ""),
                    "last_commit": row.get("last_commit", ""),
                }
            )
        recent = sorted(
            (row for row in rows if row["commits_last_12mo"]),
            key=lambda row: (-row["commits_last_12mo"], row["organization"]),
        )
        entry: dict[str, Any] = {
            "name": name,
            "report": summary.get("report_path", "") or "",
            "commits": sum(by_kind.values()),
            "by_kind": by_kind,
            "organizations_last_12mo": [
                {"organization": row["organization"], "commits": row["commits_last_12mo"]}
                for row in recent[:5]
            ],
        }
        if summary.get("group"):
            entry["group"] = summary["group"]
        repositories.append(entry)
    organizations = [
        {
            "organization": name,
            "commits_last_12mo": total["commits_last_12mo"],
            "commits": total["commits"],
            "repositories": sorted(total["repositories"], key=str.lower),
            "by_repository": sorted(
                total["by_repository"],
                key=lambda row: (-row["commits_last_12mo"], -row["commits"], row["name"].lower()),
            ),
        }
        for name, total in sorted(
            totals.items(),
            key=lambda item: (
                -item[1]["commits_last_12mo"],
                -item[1]["commits"],
                -len(item[1]["repositories"]),
                item[0],
            ),
        )
    ]
    return {
        "schema_version": 1,
        "title": "Commits by organization",
        "description": ORGANIZATIONS_DATA_DESCRIPTION,
        "generated_by": f"gitstats {version or get_version()}",
        "generated_at": now.astimezone().isoformat(timespec="seconds"),
        "quarters": quarters,
        "organizations": organizations,
        "repositories": repositories,
    }


def organizations_csv(dataset: dict[str, Any]) -> str:
    """The organizations of ``organizations_dataset``, one row each."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["organization", "repositories", "commits_last_12mo", "commits"])
    for row in dataset["organizations"]:
        writer.writerow(
            [
                row["organization"],
                len(row["repositories"]),
                row["commits_last_12mo"],
                row["commits"],
            ]
        )
    return out.getvalue()


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


def last_quarters(now: datetime.datetime, count: int = 4) -> list[tuple[str, list[str]]]:
    """The last ``count`` complete calendar quarters before ``now``, oldest first:
    ``("Jul–Sep 2026", ["2026-07", "2026-08", "2026-09"])``."""
    year, month = now.year, (now.month - 1) // 3 * 3 + 1  # the current quarter's first month
    quarters = []
    for _ in range(count):
        month -= 3
        if month < 1:
            year, month = year - 1, month + 12
        label = f"{_MONTH_NAMES[month - 1]}\u2013{_MONTH_NAMES[month + 1]} {year}"
        quarters.append((label, [f"{year:04d}-{m:02d}" for m in range(month, month + 3)]))
    return quarters[::-1]


# A quarter's share is ranked when the quarter has this many commits or more:
# one of 3 commits is a third of them, and says little
MIN_RANKED_COMMITS = 30


# a repository's summary, its AI-assisted commits, and (commits that name an
# assistant, all commits) in each quarter, None where the summary has no counts
AiRow = tuple[dict[str, Any], dict[str, Any] | None, list[tuple[int, int] | None]]


def ai_rows(
    summaries: list[dict[str, Any]], now: datetime.datetime
) -> tuple[list[AiRow], list[tuple[str, list[str]]]]:
    """The rows of the AI-assisted commits page, the largest share in the last
    quarter first, then in the quarter before it; and those quarters. A
    repository with fewer than MIN_RANKED_COMMITS commits in the last quarter
    comes after those with more, one without counts for it last."""
    quarters = last_quarters(now)
    rows: list[AiRow] = []
    for summary in summaries:
        # a summary kept from an earlier build counts the month it was made
        # in up to that day: not a whole one
        ai = compare.complete_ai(summary)
        counts = [
            _quarter_counts(ai, months) if isinstance(ai, dict) else None for _, months in quarters
        ]
        rows.append((summary, ai if isinstance(ai, dict) else None, counts))

    def share(counts: tuple[int, int] | None) -> float:
        return counts[0] / counts[1] if counts and counts[1] else -1.0

    def place(counts: tuple[int, int] | None) -> int:
        return 2 if counts is None else 0 if counts[1] >= MIN_RANKED_COMMITS else 1

    rows.sort(
        key=lambda row: (
            place(row[2][-1]),
            -share(row[2][-1]),
            -share(row[2][-2]),
            row[0].get("name", ""),
        )
    )
    return rows, quarters


def portfolio_description(summaries: list[dict[str, Any]]) -> str:
    """One sentence about the portfolio, for its share tags."""
    commits = sum(int(s.get("total_commits", 0) or 0) for s in summaries)
    names = [
        s.get("name", "")
        for s in sorted(summaries, key=lambda s: -int(s.get("total_commits", 0) or 0))
    ]
    shown = ", ".join(names[:4]) + (" and more" if len(names) > 4 else "")
    return (
        f"Reports made with gitstats for {len(summaries)} repositories, "
        f"{format_int(commits)} commits: {shown}."
    )


def ai_description(rows: list[AiRow], quarters: list[tuple[str, list[str]]]) -> str:
    """One sentence about the AI-assisted commits page, for its share tags."""
    text = (
        f"The share of commits that name an AI coding assistant in {len(rows)} repositories, "
        "quarter by quarter."
    )
    summary, _, counts = rows[0] if rows else ({}, None, [None])
    latest = counts[-1]
    if latest and latest[0] and latest[1] >= MIN_RANKED_COMMITS:
        largest = share_text(*latest).replace("&lt;", "<")
        text += f" {quarters[-1][0]}: {summary.get('name', '')}, {largest}."
    return text


AI_DATA_DESCRIPTION = (
    "Commits that name an AI coding assistant: as their author, as a co-author, or in "
    "the line it signs with. These are lower bounds: an assistant that leaves no mark in "
    "a commit is not counted, and a mark does not say how much of the commit the "
    "assistant wrote. A commit counts in the month it was written (its author date)."
)
# A snapshot of the data of a quarter, each repository kept as it was first
# written into it: "ai/2026-Q3.json"
_SNAPSHOT = re.compile(r"ai/(\d{4})-Q([1-4])\.json")


def quarter_id(months: list[str]) -> str:
    """The quarter of these months, as data names it: "2026-Q3" for July to September."""
    year, month = months[0].split("-")
    return f"{year}-Q{(int(month) - 1) // 3 + 1}"


def ai_dataset(
    summaries: list[dict[str, Any]], now: datetime.datetime, version: str = ""
) -> dict[str, Any]:
    """The counts of the AI-assisted commits page, as data, put together by
    gitstats ``version`` (this one's, when not given).

    For each repository whose summary counts them: its totals, and each
    complete month and quarter the summary covers, with all the commits of it.
    A month is complete before this one, and before the one the summary was
    made in: a summary kept from an earlier build has that month as it was
    then.
    """
    this_month = f"{now.year:04d}-{now.month:02d}"
    quarters = last_quarters(now, _AI_MONTHS // 3)
    covered: set[str] = set()
    repositories = []
    for summary in sorted(summaries, key=lambda s: str(s.get("name", "")).lower()):
        ai = compare.complete_ai(summary)
        if ai is None:
            continue
        by_month, all_by_month = ai.get("by_month") or {}, ai.get("commits_by_month") or {}
        by_quarter = _ai_quarters(ai, quarters)
        covered.update(by_quarter)
        repositories.append(
            {
                "name": summary.get("name", ""),
                "report": summary.get("report_path", ""),
                # the counts are the summary's: the version that made it counted them
                "counted_by": summary.get("generated_by", ""),
                "all_time": {
                    "commits": int(summary.get("total_commits", 0) or 0),
                    "ai_assisted": int(ai.get("commits", 0) or 0),
                    "authored": int(ai.get("authored", 0) or 0),
                    "assistants": dict(ai.get("assistants") or {}),
                },
                "quarters": by_quarter,
                "months": {
                    month: {
                        "commits": int(all_by_month[month]),
                        "ai_assisted": int(by_month.get(month, 0)),
                    }
                    for month in sorted(all_by_month)
                    if month < this_month
                },
            }
        )
    return {
        "schema_version": 1,
        "title": "AI-assisted commits",
        "description": AI_DATA_DESCRIPTION,
        "generated_by": f"gitstats {version or get_version()}",
        "generated_at": now.astimezone().isoformat(timespec="seconds"),
        "quarters": sorted(covered),
        "repositories": repositories,
    }


def _ai_quarters(
    ai: dict[str, Any], quarters: list[tuple[str, list[str]]]
) -> dict[str, dict[str, Any]]:
    """The quarters of ``ai_dataset`` an ai_assisted block covers, by their names."""
    by_quarter = {}
    for _, months in quarters:
        counts = _quarter_counts(ai, months)
        if counts is not None:
            assisted, commits = counts
            by_quarter[quarter_id(months)] = {
                "commits": commits,
                "ai_assisted": assisted,
                "share": round(assisted / commits, 4) if commits else None,
            }
    return by_quarter


def ai_csv(dataset: dict[str, Any]) -> str:
    """The months of ``ai_dataset``, one row for each repository and month."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["repository", "month", "commits", "ai_assisted"])
    for repository in dataset["repositories"]:
        for month, counts in repository["months"].items():
            writer.writerow([repository["name"], month, counts["commits"], counts["ai_assisted"]])
    return out.getvalue()


def snapshot_label(name: str) -> str:
    """The quarter a snapshot holds, as the page names it: "Jul–Sep 2026"."""
    match = _SNAPSHOT.fullmatch(name)
    if not match:
        return name
    first = (int(match.group(2)) - 1) * 3
    return f"{_MONTH_NAMES[first]}–{_MONTH_NAMES[first + 2]} {match.group(1)}"


def _read_snapshot(file: str) -> dict[str, Any] | None:
    """A snapshot written before, or None when there is none, or it cannot be
    read as one."""
    try:
        with open(file, encoding="utf-8") as f:
            snapshot = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("repositories"), list):
        return None
    return snapshot


def _repository_key(entry: Any) -> str:
    """Which repository an entry of ``ai_dataset`` is: its report, which a
    portfolio keeps in the same place, or its name."""
    if not isinstance(entry, dict):
        return ""
    return str(entry.get("report") or entry.get("name") or "")


def _same_portfolio(snapshot: dict[str, Any] | None, dataset: dict[str, Any]) -> bool:
    """Whether ``snapshot`` was written by this portfolio: it has one of its
    repositories."""
    if snapshot is None:
        return False
    have = {_repository_key(entry) for entry in snapshot["repositories"]} - {""}
    return any(_repository_key(entry) in have for entry in dataset["repositories"])


def _snapshot_entry(entry: dict[str, Any], quarter: str) -> dict[str, Any]:
    """A repository of ``ai_dataset`` as the snapshot of ``quarter`` keeps it:
    its months and quarters up to that one. Its all-time counts are those of
    the day it was put in."""
    year, number = quarter.split("-Q")
    last_month = f"{year}-{int(number) * 3:02d}"
    return {
        **entry,
        "quarters": {key: value for key, value in entry["quarters"].items() if key <= quarter},
        "months": {key: value for key, value in entry["months"].items() if key <= last_month},
    }


def _has_quarter(entry: Any, quarter: str) -> bool:
    return isinstance(entry, dict) and quarter in (entry.get("quarters") or {})


def _snapshot_additions(
    snapshot: dict[str, Any], dataset: dict[str, Any], quarter: str
) -> list[dict[str, Any]]:
    """The repositories of ``dataset`` with counts for ``quarter`` that its
    snapshot has none for, as the snapshot keeps them, with when they were
    added. One the snapshot has without that quarter (its report was kept
    from a build before the quarter ended) has none; one it has under
    another report folder (its id renamed) has them."""
    counted = [entry for entry in snapshot["repositories"] if _has_quarter(entry, quarter)]
    keys = {_repository_key(entry) for entry in counted}
    names = {str(entry.get("name", "")) for entry in counted} - {""}
    return [
        {**_snapshot_entry(entry, quarter), "added_at": dataset["generated_at"]}
        for entry in dataset["repositories"]
        if _has_quarter(entry, quarter)
        and _repository_key(entry) not in keys
        and str(entry.get("name", "")) not in names
    ]


def _quarter_counts(ai: dict[str, Any], months: list[str]) -> tuple[int, int] | None:
    """(commits that name an assistant, all commits) in these months, or None
    when the summary does not cover all of them."""
    by_month, all_by_month = ai.get("by_month") or {}, ai.get("commits_by_month") or {}
    if any(month not in all_by_month for month in months):
        return None
    return (
        sum(int(by_month.get(month, 0)) for month in months),
        sum(int(all_by_month[month]) for month in months),
    )


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


def _group_attr(group: str) -> str:
    return f' data-group="{html.escape(group, quote=True)}"' if group else ""


def group_filter_html(summaries: list[dict[str, Any]], groups: list[tuple[str, str]]) -> str:
    """Buttons that narrow the table after them to the repositories of one
    group, each with how many it has. Without scripts, every row shows."""
    counts: dict[str, int] = {}
    for summary in summaries:
        group = str(summary.get("group", "") or "")
        counts[group] = counts.get(group, 0) + 1
    buttons = [("", "All", len(summaries))] + [
        (group_id, name, counts[group_id]) for group_id, name in groups if counts.get(group_id)
    ]
    return (
        '<div class="group-filter" role="group" aria-label="Show the repositories of">'
        + "".join(
            f'<button type="button" data-group="{html.escape(group_id, quote=True)}" '
            f'aria-pressed="{"true" if not group_id else "false"}">{html.escape(name)} '
            f"<span>{count}</span></button>"
            for group_id, name, count in buttons
        )
        + "</div>"
    )


# Narrows the rows of a page's tables to one group, and remembers it in the
# address (#group=python), so that a link can show one group
GROUP_FILTER_SCRIPT = """<script>
(function () {
	var buttons = document.querySelectorAll('.group-filter button');
	function show(group) {
		var known = !group;
		buttons.forEach(function (b) {
			if (b.getAttribute('data-group') === group) { known = true; }
		});
		if (!known) { group = ''; }
		buttons.forEach(function (b) {
			b.setAttribute('aria-pressed', String(b.getAttribute('data-group') === group));
		});
		document.querySelectorAll('tr[data-group]').forEach(function (row) {
			row.hidden = !!group && row.getAttribute('data-group') !== group;
		});
	}
	function fromHash(event) {
		var match = /^#group=([a-z0-9-]+)$/.exec(location.hash);
		// a link within the page (the skip link, a heading) chooses no group
		if (!match && location.hash && event) return;
		show(match ? match[1] : '');
	}
	buttons.forEach(function (b) {
		b.addEventListener('click', function () {
			var group = b.getAttribute('data-group');
			history.replaceState(null, '', group ? '#group=' + group : location.pathname + location.search);
			show(group);
		});
	});
	window.addEventListener('hashchange', fromHash);
	fromHash();
})();
</script>
"""


# how many organizations the page lists; the data has them all
_ORGANIZATIONS_SHOWN = 50
# how many organizations get a page and a badge of their own: the first of
# organizations_dataset, the most commits in the last 12 months first
_ORGANIZATION_PAGES = 200
# a domain, as an organization's page is named after it: "orgs/google.com.html"
_DOMAIN = r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+"
_ORGANIZATION_FILE = re.compile(rf"orgs/{_DOMAIN}\.(?:html|svg|json)")
# a repository's comparison page and card, in its report's folder
_COMPARE_FILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*/compare(?:-card)?\.html")


def _report_folder(report_path: str) -> str:
    """The folder of a report in a portfolio: "flask" for "flask/index.html";
    "" for one that is not in a folder of its own."""
    end = "/index.html"
    return report_path[: -len(end)] if report_path.endswith(end) else ""


def organization_pages(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    """The organizations of ``organizations_dataset`` that get a page and a
    badge: the first _ORGANIZATION_PAGES whose domain can name a file."""
    return [row for row in dataset["organizations"] if re.fullmatch(_DOMAIN, row["organization"])][
        :_ORGANIZATION_PAGES
    ]


def organization_badge_message(row: dict[str, Any]) -> str:
    """What an organization's badge says: its commits and projects in the last
    12 months, or in all, when it has none in them."""
    recent = [repo for repo in row["by_repository"] if repo["commits_last_12mo"]]
    if recent:
        commits, projects, when = row["commits_last_12mo"], len(recent), " in 12 months"
    else:
        commits, projects, when = row["commits"], len(row["by_repository"]), ""
    return (
        f"{compact_count(commits, 'commit')} to {projects} "
        f"project{'' if projects == 1 else 's'}{when}"
    )


def _fraction(part: int, whole: int) -> str:
    """``part`` of ``whole``, for a cell to sort by: "0.000614"."""
    return f"{part / whole:.6f}" if whole else "0"


def _organization_share_key(entry: dict[str, Any]) -> tuple[float, str]:
    """Sorts repositories by the share of their commits from organizations, the
    largest first, then by name."""
    commits = entry["commits"]
    share = entry["by_kind"].get(ORGANIZATION, 0) / commits if commits else -1.0
    return (-share, entry["name"].lower())


def organizations_description(dataset: dict[str, Any]) -> str:
    """One sentence about the organizations page, for its share tags."""
    text = (
        f"The organizations whose addresses commit to {len(dataset['repositories'])} "
        "repositories, by the domain of the address."
    )
    if dataset["organizations"]:
        top = dataset["organizations"][0]
        # the repositories of those commits, as its own page counts them
        recent = sum(1 for repo in top["by_repository"] if repo["commits_last_12mo"])
        if recent:
            text += (
                f" Most commits in the last 12 months: {top['organization']}, "
                f"{format_int(top['commits_last_12mo'])} in {plural(recent, 'repository', 'repositories')}."
            )
        else:
            # none in the last 12 months: the most of all
            text += (
                f" Most commits: {top['organization']}, {format_int(top['commits'])} in "
                f"{plural(len(top['repositories']), 'repository', 'repositories')}."
            )
    return text


class AggregateReportCreator:
    """Render the portfolio page for a multi-repository run."""

    def create(
        self,
        summaries: list[dict[str, Any]],
        failures: list[dict[str, str]],
        path: str,
        title: str = "GitStats Portfolio",
        site_url: str = "",
        version: str = "",
        groups: list[tuple[str, str]] | None = None,
        group_titles: dict[str, str] | None = None,
        nav: list[tuple[str, str]] | None = None,
    ) -> None:
        """Write the portfolio's pages, and the share card of each: ``site_url``
        is the portfolio's public address, ending in "/", or "" when unknown;
        ``version``, the gitstats they say made them, when not this one.

        ``groups`` are the (id, name) of the groups the repositories are in,
        in the order the pages offer them: each summary names its group as
        ``"group"``. With them, the pages can be narrowed to one group.
        ``group_titles`` name each group's projects inside a sentence
        ("Python open source projects"), for the comparison pages. ``nav``
        adds (address from the output root, label) links to the nav bar of
        every page, for pages written next to the portfolio's own, such as
        the Gallery's ecosystems.

        Each repository's report gets the way back to the portfolio, at the
        start of its nav bar."""
        self.group_titles = dict(group_titles or {})
        self.nav = list(nav or [])
        self._copy_assets(path)
        self.site_url = site_url
        self.version = version or get_version()
        self.groups = [
            (group_id, name)
            for group_id, name in (groups or [])
            if any(summary.get("group") == group_id for summary in summaries)
        ]
        # the page of AI-assisted commits, when a summary counts them
        ai = any(isinstance(summary.get("ai_assisted"), dict) for summary in summaries)
        # the page of organizations, when a summary names one
        self.organizations = any(
            (summary.get("organizations") or {}).get("top") for summary in summaries
        )
        f = self._open_portfolio_file(path)
        try:
            self._write_page(f, summaries, failures, title, ai)
        finally:
            f.close()
        f = self._open_portfolio_file(path, "share-card.html")
        try:
            f.write(self._share_card(summaries, title))
        finally:
            f.close()
        if ai:
            now = datetime.datetime.now()
            snapshots = self._write_ai_data(path, ai_dataset(summaries, now, self.version))
            rows, quarters = ai_rows(summaries, now)
            f = self._open_portfolio_file(path, "ai.html")
            try:
                self._write_ai_page(f, summaries, title, rows, quarters, snapshots)
            finally:
                f.close()
            f = self._open_portfolio_file(path, "ai-share-card.html")
            try:
                f.write(self._ai_share_card(rows, quarters))
            finally:
                f.close()
        if self.organizations:
            dataset = organizations_dataset(summaries, datetime.datetime.now(), self.version)
            for name, text in (
                ("organizations.json", json.dumps(dataset, indent=2, ensure_ascii=False)),
                ("organizations.csv", organizations_csv(dataset)),
            ):
                f = self._open_portfolio_file(path, name)
                try:
                    f.write(text)
                finally:
                    f.close()
            pages = organization_pages(dataset)
            self.organization_page_names = {row["organization"] for row in pages}
            f = self._open_portfolio_file(path, "organizations.html")
            try:
                self._write_organizations_page(f, summaries, title, dataset, ai)
            finally:
                f.close()
            for row in pages:
                self._write_organization_files(path, row, title, len(summaries), ai)
        if len(summaries) >= compare.MIN_REPOSITORIES:
            self._write_comparisons(path, summaries, title, ai)
        for summary in summaries:
            self._link_back(path, summary, title)

    site_url = ""
    nav: list[tuple[str, str]] = []
    organizations = False
    organization_page_names: set[str] = set()
    organization_sections: set[str] = set()
    group_titles: dict[str, str] = {}
    version = ""
    groups: list[tuple[str, str]] = []

    def _write_ai_data(self, path: str, dataset: dict[str, Any]) -> list[str]:
        """Write the data of the AI-assisted commits page, as ai.json and
        ai.csv, and the snapshot of its last quarter; return the snapshots in
        the output root that are this portfolio's, oldest first.

        A snapshot keeps the counts of its quarter as they were first
        published: commits written in a quarter can still be merged after it
        ends, and change the counts of ai.json. So a repository already in it
        with counts for the quarter stays as it is; one that has none there
        (added to the portfolio since, or kept from a build before the quarter
        ended) is added, as counted now, with when it was. A snapshot that has none of
        this portfolio's repositories is another portfolio's, written into
        the same folder before: it is written again, and an older one of them
        is not listed.
        """
        if dataset["quarters"]:
            quarter = dataset["quarters"][-1]
            name = f"ai/{quarter}.json"
            target = os.path.join(path, name)
            kept = _read_snapshot(target)
            if kept is None and os.path.exists(target):
                logger.warning("Leaving %s as it is: it cannot be read as a snapshot", name)
            else:
                if kept is not None and _same_portfolio(kept, dataset):
                    added = _snapshot_additions(kept, dataset, quarter)
                    # an entry without the quarter gives way to its counts
                    replaced = {_repository_key(entry) for entry in added}
                    snapshot = {
                        **kept,
                        "quarters": sorted(
                            set(kept.get("quarters") or [])
                            | {key for entry in added for key in entry["quarters"]}
                        ),
                        "repositories": sorted(
                            [
                                entry
                                for entry in kept["repositories"]
                                if _has_quarter(entry, quarter)
                                or _repository_key(entry) not in replaced
                            ]
                            + added,
                            key=lambda entry: str(entry.get("name", "")).lower(),
                        ),
                    }
                else:
                    # the first of the quarter: the repositories with counts for it
                    added = [
                        _snapshot_entry(entry, quarter)
                        for entry in dataset["repositories"]
                        if _has_quarter(entry, quarter)
                    ]
                    snapshot = {
                        **dataset,
                        "quarters": sorted({key for entry in added for key in entry["quarters"]}),
                        "repositories": added,
                    }
                if added:
                    f = self._open_portfolio_file(path, name)
                    try:
                        json.dump(snapshot, f, indent=2, ensure_ascii=False)
                    finally:
                        f.close()
        folder = os.path.join(path, "ai")
        snapshots = sorted(
            f"ai/{entry}"
            for entry in (os.listdir(folder) if os.path.isdir(folder) else [])
            if _SNAPSHOT.fullmatch(f"ai/{entry}")
            and _same_portfolio(_read_snapshot(os.path.join(folder, entry)), dataset)
        )
        f = self._open_portfolio_file(path, "ai.json")
        try:
            json.dump({**dataset, "snapshots": snapshots}, f, indent=2, ensure_ascii=False)
        finally:
            f.close()
        f = self._open_portfolio_file(path, "ai.csv")
        try:
            f.write(ai_csv(dataset))
        finally:
            f.close()
        return snapshots

    @staticmethod
    def _copy_assets(path: str) -> None:
        """Copy the shared static assets into the output root.

        Asset names are hard-coded; each destination is resolved and checked
        to stay under the output root before writing.
        """
        basedir = os.path.dirname(os.path.abspath(__file__))
        base = os.path.abspath(path)
        for file in (
            load_config()["style"],
            "sortable.js",
        ):
            src = os.path.join(basedir, file)
            target = os.path.abspath(os.path.join(base, os.path.basename(file)))
            if os.path.commonpath([base, target]) != base:
                raise ValueError(f"Refusing to write outside report directory: {file}")
            if os.path.exists(src):
                shutil.copyfile(src, target)

    @staticmethod
    def _open_portfolio_file(path: str, name: str = "index.html") -> Any:
        """Open a portfolio page for writing, confined to the output root.

        The filename is one of the portfolio's own; resolving the target and
        checking it stays under the output root guards against directory
        traversal.
        """
        pages = (
            "index.html",
            "ai.html",
            "organizations.html",
            "share-card.html",
            "ai-share-card.html",
        )
        data = ("ai.json", "ai.csv", "organizations.json", "organizations.csv")
        if (
            name not in (*pages, *data)
            and not _SNAPSHOT.fullmatch(name)
            and not _ORGANIZATION_FILE.fullmatch(name)
            and not _COMPARE_FILE.fullmatch(name)
            and name != "compare.json"
        ):
            raise ValueError(f"Not a portfolio page: {name}")
        base = os.path.abspath(path)
        target = os.path.abspath(os.path.join(base, name))
        if os.path.commonpath([base, target]) != base:
            raise ValueError(f"Refusing to write outside report directory: {path}")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        return open(target, "w", encoding="utf-8")

    def _write_page(
        self,
        f: Any,
        summaries: list[dict[str, Any]],
        failures: list[dict[str, str]],
        title: str,
        ai: bool = False,
    ) -> None:
        self._print_header(
            f,
            title,
            self._share_tags(
                title, portfolio_description(summaries), "index.html", "share-card.png"
            ),
        )
        self._print_nav(f, title, "index.html", ai)

        f.write(f"<h1>{html.escape(title)}</h1>")
        generated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(
            f'<p class="portfolio-subtitle">{len(summaries)} repositories &middot; '
            f"generated by gitstats {html.escape(self.version or get_version())} on {generated}</p>"
        )

        self._write_totals(f, summaries)
        if ai:
            f.write(
                '<p class="more-link"><a href="ai.html">AI-assisted commits, quarter by '
                "quarter &rarr;</a></p>"
            )
        if self.organizations:
            f.write(
                '<p class="more-link"><a href="organizations.html">Organizations, by the '
                "domains of their commit addresses &rarr;</a></p>"
            )
        self._write_repo_table(f, summaries, self.groups)
        self._write_failures(f, failures)

        self._print_footer(f)

    @staticmethod
    def _print_footer(f: Any) -> None:
        f.write(FOOTER)
        f.write("</body>\n</html>")

    def _write_ai_page(
        self,
        f: Any,
        summaries: list[dict[str, Any]],
        title: str,
        rows: list[AiRow],
        quarters: list[tuple[str, list[str]]],
        snapshots: list[str] | None = None,
    ) -> None:
        """The commits that name an AI coding assistant, repository by
        repository and quarter by quarter, and where to get their data."""
        heading = f"{title}: AI-assisted commits"
        self._print_header(
            f,
            heading,
            self._share_tags(
                heading, ai_description(rows, quarters), "ai.html", "ai-share-card.png"
            ),
        )
        self._print_nav(f, title, "ai.html", True)
        f.write("<h1>AI-assisted commits</h1>")
        now = datetime.datetime.now()
        f.write(
            f'<p class="portfolio-subtitle">{len(summaries)} repositories &middot; '
            f"generated by gitstats {html.escape(self.version or get_version())} on "
            f"{now.strftime('%Y-%m-%d %H:%M:%S')}</p>"
        )
        f.write(
            '<p class="section-note">Commits that name an AI coding assistant: as their '
            "author, as a co-author, or in the line it signs with. These are lower bounds. "
            "An assistant that leaves no mark in a commit is not counted, so a share near "
            "zero says that commits are not signed, not that no assistant is used. And a "
            "mark does not say how much of the commit the assistant wrote.</p>"
        )

        self._write_ai_tiles(f, rows, quarters)

        f.write("<h2>By quarter</h2>")
        f.write(
            '<p class="section-note">The share of each quarter&rsquo;s commits that name an '
            "assistant, and under it those commits and all of them. The darker, the larger "
            "the share. The largest share in the last quarter comes first, of the "
            f"repositories with {MIN_RANKED_COMMITS} commits or more in it; then the others. "
            "The assistants named most are those of all the history.</p>"
        )
        if self.groups:
            f.write(group_filter_html(summaries, self.groups))
        f.write('<div class="table-scroll"><table class="ai-grid">')
        f.write(
            "<tr><th>Repository</th>"
            + "".join(f'<th class="num">{label}</th>' for label, _ in quarters)
            + "<th>Named most (all time)</th></tr>"
        )
        for row in rows:
            f.write(self._ai_row(*row))
        f.write("</table></div>")
        if self.groups:
            f.write(GROUP_FILTER_SCRIPT)
        # Where the table scrolls sideways (a phone), it starts at the last
        # quarter: the column the page is about, not the oldest one
        f.write(
            "<script>document.querySelectorAll('table.ai-grid').forEach(function (table) {"
            " var box = table.parentElement, cells = table.rows[0].cells;"
            " var last = cells[cells.length - 2];"
            " if (box.scrollWidth > box.clientWidth) {"
            " box.scrollLeft = last.offsetLeft + last.offsetWidth - box.clientWidth; }"
            " });</script>"
        )
        f.write(AI_ASSISTED_COUNTED)

        f.write("<h2>Data</h2>")
        note = (
            "The counts behind this page, for each complete month and quarter the reports "
            'cover: <a href="ai.json">ai.json</a>, <a href="ai.csv">ai.csv</a>.'
        )
        if snapshots:
            links = ", ".join(
                f'<a href="{html.escape(name, quote=True)}">{html.escape(snapshot_label(name))}</a>'
                for name in snapshots
            )
            note += (
                " Each quarter is also kept as it was first published, since commits written "
                "in a quarter can still be merged after it ends; a repository added to the "
                f"portfolio later is kept as it was when it was added: {links}."
            )
        f.write(f'<p class="section-note">{note}</p>')
        self._print_footer(f)

    def _write_organizations_page(
        self,
        f: Any,
        summaries: list[dict[str, Any]],
        title: str,
        dataset: dict[str, Any],
        ai: bool = False,
    ) -> None:
        """The organizations whose addresses the repositories' commits come
        from, added up across them, and for each repository how its commits
        of the last four quarters divide between kinds of address."""
        organizations = dataset["organizations"]
        repositories = dataset["repositories"]
        # the reports whose Authors page has the "Commits by organization"
        # section: those with a commit from an organization
        self.organization_sections = {
            str(summary.get("report_path", "") or "")
            for summary in summaries
            if (summary.get("organizations") or {}).get("top")
        }
        heading = f"{title}: Organizations"
        self._print_header(
            f,
            heading,
            self._share_tags(
                heading,
                organizations_description(dataset),
                "organizations.html",
                "share-card.png",
            ),
        )
        self._print_nav(f, title, "organizations.html", ai)
        f.write("<h1>Organizations</h1>")
        f.write(
            f'<p class="portfolio-subtitle">{len(repositories)} repositories &middot; '
            f"generated by gitstats {html.escape(self.version or get_version())} on "
            f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>"
        )
        f.write(
            '<p class="section-note">Commits counted by the domain of the author&rsquo;s '
            "email address: <code>corp.google.com</code> and <code>google.com</code> both "
            "count under google.com. A domain only one person commits from is most often that "
            "person&rsquo;s own, and is counted apart, as are mail providers anyone can sign up "
            "for, hidden noreply addresses and bots.</p>"
            '<p class="section-note">A domain says where an address is, not who paid for the '
            "work: people commit from personal addresses on paid time, and from work addresses "
            "on their own. These counts are lower bounds of what organizations do.</p>"
        )
        self._write_organization_tiles(f, organizations, repositories)

        f.write("<h2>Across the repositories</h2>")
        f.write(
            '<p class="section-note">The organizations with the most commits in the last 12 '
            "months, added up across the repositories, and the repositories they committed "
            "to.</p>"
        )
        f.write('<div class="table-scroll"><table class="sortable" id="organizations">')
        f.write(
            '<tr><th>Organization</th><th class="num">Repositories</th>'
            '<th class="num">Commits (12 mo)</th><th class="num">Commits</th>'
            "<th>Committed to</th></tr>"
        )
        for row in organizations[:_ORGANIZATIONS_SHOWN]:
            names = row["repositories"]
            shown = ", ".join(html.escape(name) for name in names[:4])
            if len(names) > 4:
                shown += f" and {len(names) - 4} more"
            f.write(
                f"<tr><td>{self._organization_link(row['organization'])}</td>"
                f'<td class="num">{format_int(len(names))}</td>'
                f'<td class="num">{format_int(row["commits_last_12mo"])}</td>'
                f'<td class="num">{format_int(row["commits"])}</td>'
                f"<td>{shown}</td></tr>"
            )
        f.write("</table></div>")
        if len(organizations) > _ORGANIZATIONS_SHOWN:
            f.write(
                f'<p class="section-note">The first {_ORGANIZATIONS_SHOWN} of '
                f"{format_int(len(organizations))}; all of them are in the data below.</p>"
            )

        quarters = dataset["quarters"]
        f.write("<h2>By repository</h2>")
        f.write(
            '<p class="section-note">How each repository&rsquo;s commits of the last four '
            f"complete quarters ({html.escape(quarters[0])} to {html.escape(quarters[-1])}) "
            "divide between kinds of address, the largest share from organizations first, "
            "and its organizations with the most commits in the last 12 months.</p>"
        )
        if self.groups:
            f.write(group_filter_html(summaries, self.groups))
        f.write('<div class="table-scroll"><table class="sortable" id="organization-mix">')
        f.write(
            '<tr><th>Repository</th><th class="num">Commits</th>'
            + "".join(f'<th class="num">{KIND_LABELS[kind]}</th>' for kind in ORGANIZATION_KINDS)
            + "<th>Organizations, last 12 months</th></tr>"
        )
        for entry in sorted(repositories, key=_organization_share_key):
            f.write(self._organization_mix_row(entry))
        f.write("</table></div>")
        if self.groups:
            f.write(GROUP_FILTER_SCRIPT)

        f.write("<h2>Data</h2>")
        f.write(
            '<p class="section-note">Every organization of every repository, and each '
            'repository&rsquo;s counts: <a href="organizations.json">organizations.json</a>, '
            '<a href="organizations.csv">organizations.csv</a>. Domains and counts only, never '
            "an address.</p>"
        )
        self._print_footer(f)

    def _write_comparisons(
        self, path: str, summaries: list[dict[str, Any]], title: str, ai: bool
    ) -> None:
        """For each repository with a report folder, a page of how it compares
        with the others and a share card; and the numbers, as compare.json."""
        now = datetime.datetime.now()
        quarters = [months for _, months in last_quarters(now)]
        rows = compare.comparisons(summaries, quarters)
        stand_out = insights.facts(summaries, f"{title} projects")
        data = []
        for row, found in zip(rows, stand_out):
            summary = row["summary"]
            report = str(summary.get("report_path", "") or "")
            folder = _report_folder(report)
            group = str(summary.get("group", "") or "")
            entry: dict[str, Any] = {
                "name": summary.get("name", ""),
                "values": row["values"],
                "ranks": {
                    measure: {
                        scope: list(place) if place else None for scope, place in ranks.items()
                    }
                    for measure, ranks in row["ranks"].items()
                },
            }
            if group:
                entry["group"] = group
            entry["insights"] = [
                {
                    key: fact[key]
                    for key in ("kind", "label", "value", "big", "sentence", "compared")
                }
                for fact in found
            ]
            if not _COMPARE_FILE.fullmatch(f"{folder}/compare.html"):
                data.append(entry)
                continue
            entry["page"] = f"{folder}/compare.html"
            entry["headline"] = compare.headline(row, self._group_projects(group))
            data.append(entry)
            f = self._open_portfolio_file(path, f"{folder}/compare.html")
            try:
                self._write_comparison_page(
                    f, row, rows, title, folder, entry["headline"], ai, found
                )
            finally:
                f.close()
            f = self._open_portfolio_file(path, f"{folder}/compare-card.html")
            try:
                f.write(
                    self._comparison_card(
                        row, self._group_projects(group), entry["headline"], found
                    )
                )
            finally:
                f.close()
            self._fill_overview(
                path,
                folder,
                insights.overview_html(
                    str(summary.get("name", "") or ""), found, len(rows) - 1, title
                ),
            )
        f = self._open_portfolio_file(path, "compare.json")
        try:
            json.dump(
                {
                    "schema_version": 1,
                    "title": "How each repository compares",
                    "generated_by": f"gitstats {self.version or get_version()}",
                    "generated_at": now.astimezone().isoformat(timespec="seconds"),
                    "quarters": [quarter_id(months) for months in quarters],
                    "measures": [
                        {"id": m.id, "label": m.label, "definition": m.definition}
                        for m in compare.MEASURES
                    ],
                    "repositories": data,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )
        finally:
            f.close()

    def _write_comparison_page(
        self,
        f: Any,
        row: dict[str, Any],
        rows: list[dict[str, Any]],
        title: str,
        folder: str,
        headline: str,
        ai: bool,
        found: list[dict[str, Any]] | None = None,
    ) -> None:
        """One repository next to the others: what stands out about it, then
        a sentence on where it ranks, and each measure with every repository
        on a strip and its rank."""
        summary = row["summary"]
        name = str(summary.get("name", "") or "")
        group = str(summary.get("group", "") or "")
        group_name = dict(self.groups).get(group, "")
        peers = [other for other in rows if group and other["summary"].get("group") == group]
        others = [other for other in rows if other not in peers]
        heading = f"How {name} compares"
        description = (
            found[0]["sentence"]
            if found
            else headline or f"{name} next to the other repositories of {title}."
        )
        self._print_header(
            f,
            heading,
            self._share_tags(
                heading, description, f"{folder}/compare.html", f"{folder}/compare-card.png"
            ),
            "../",
        )
        self._print_nav(f, title, "", ai, prefix="../")
        f.write(f"<h1>{html.escape(name)}</h1>")
        compared = f"all {len(rows)} repositories of"
        if peers:
            # "14 open source languages and developer tools", as a sentence names them
            projects = self._group_projects(group)
            compared = f"{len(peers)} {html.escape(projects)}, and all {len(rows)} of"
        f.write(
            f'<p class="portfolio-subtitle">Compared with {compared} '
            f'<a href="../index.html">{html.escape(title)}</a> &middot; the 12 months up to '
            "each one&rsquo;s last commit</p>"
        )
        if found:
            f.write(html_header(2, "What stands out"))
            f.write(
                '<p class="section-note">Where it is in the top or bottom 15% of these '
                "projects.</p>" + insights.facts_html(found)
            )
            f.write(html_header(2, "Where it stands"))
        elif headline:
            # with nothing that stands out, the sentence on where it ranks leads;
            # with something, that sentence would say part of it again
            f.write(f'<p class="compare-headline">{html.escape(headline)}</p>')
        legend = [f'<span><i class="own"></i>{html.escape(name)}</span>']
        if peers:
            legend.append(f'<span><i class="group"></i>{html.escape(group_name)}</span>')
        legend.append(f'<span><i class="all"></i>{"others" if peers else "all"}</span>')
        f.write(f'<p class="compare-legend">{"".join(legend)}</p>')
        f.write('<div class="compare-list">')
        for measure in compare.MEASURES:
            own = row["values"][measure.id]
            if own is None:
                # a measure this repository's summary has nothing for
                continue
            ranks = row["ranks"][measure.id]
            strip = compare.strip_svg(
                measure,
                own,
                [peer["values"][measure.id] for peer in peers if peer is not row],
                [other["values"][measure.id] for other in others],
            )
            # a measure with a value has a rank among all, and among its peers;
            # a place others share says so, and one all of them share is none
            place = ranks["group"] if peers else ranks["all"]
            # "12th of 12 open source AI coding assistants", as a sentence names them
            where = html.escape(self._group_projects(group)) if peers else "repositories"
            same = sum(1 for other in (peers or rows) if other["values"][measure.id] == own)
            words, more = compare.rank_words(place, same)
            if words == "Same for all":
                rank_html = f"<b>{words}</b>{more} {where}"
            else:
                rank_html = f"<b>{words}</b>{where}{more}"
            if peers:
                same = sum(1 for other in rows if other["values"][measure.id] == own)
                words, more = compare.rank_words(ranks["all"], same)
                if words == "Same for all":
                    rank_html += f"<br>the same for all {more} overall"
                else:
                    rank_html += f"<br>{words} overall{more}"
            f.write(
                '<div class="compare-row">'
                f'<div><span class="compare-name">{html.escape(measure.label)}</span>'
                f'<span class="compare-value">{compare.show(own, measure)}</span></div>'
                f"{strip or '<span></span>'}"
                f'<div class="compare-rank">{rank_html}</div>'
                f'<p class="compare-definition">{html.escape(measure.definition)}</p>'
                "</div>"
            )
        f.write("</div>")
        f.write(
            '<p class="section-note">Counts sit on a logarithmic scale, so that projects of '
            "every size have room; shares on a straight one. A rank is a position among "
            "these projects, not a score: more is not better. Every number is in "
            '<a href="../compare.json">compare.json</a>.</p>'
        )
        f.write(
            f'<p class="more-link"><a href="index.html">The full report of {html.escape(name)} '
            "&rarr;</a></p>"
        )
        self._print_footer(f)

    @staticmethod
    def _comparison_card(
        row: dict[str, Any],
        group_projects: str,
        headline: str,
        found: list[dict[str, Any]] | None = None,
    ) -> str:
        """The comparison's share card: what stands out, each fact's number
        large; or, with nothing that does, the sentence, and each measure's
        rank as a bar, longer the nearer the top. ``group_projects`` names the
        projects of its group, as a sentence does; "" without one."""
        name = str(row["summary"].get("name", "") or "")
        if found:
            facts = "".join(
                f"<div><b>{html.escape(fact['big'])}</b>"
                f"<span>{html.escape(fact['sentence'])}</span></div>"
                for fact in found
            )
            return share_card_page(
                f"What stands out in {name}",
                f'<div class="brand">// what stands out</div><h1>{html.escape(name)}</h1>'
                f'<div class="facts n{len(found)}">{facts}</div>',
            )
        scope = "group" if group_projects else "all"
        bars = "".join(
            f"<div><b>{html.escape(label)}</b>"
            f'<i style="width:{max(2.0, 100 * position):.1f}%"></i>'
            f"<span>{html.escape(rank_text)}</span></div>"
            for label, position, rank_text in compare.card_rows(row, scope)
        )
        brand = (
            f"// {html.escape(group_projects)} compared" if group_projects else "// how it compares"
        )
        return share_card_page(
            f"How {name} compares",
            f'<div class="brand">{brand}</div><h1>{html.escape(name)}</h1>'
            f'<p class="sub clamp">{html.escape(headline)}</p>'
            f'<div class="bars ranks">{bars}</div>',
        )

    @staticmethod
    def _link_back(path: str, summary: dict[str, Any], title: str) -> int:
        """Make the brand of each page of a repository's report the way back
        to the portfolio, "← GitStats Gallery"; how many pages changed. A page
        changed before, by an earlier portfolio, keeps what it has."""
        folder = _report_folder(str(summary.get("report_path", "") or ""))
        base = os.path.abspath(path)
        target = os.path.abspath(os.path.join(base, folder))
        # a plain folder name, the same a comparison page is written into
        if (
            not _COMPARE_FILE.fullmatch(f"{folder}/compare.html")
            or os.path.commonpath([base, target]) != base
            or not os.path.isdir(target)
        ):
            return 0
        brand = f'<a href="../index.html" class="nav-brand nav-up">&larr; {html.escape(title)}</a>'
        changed = 0
        for entry in sorted(os.listdir(target)):
            if not entry.endswith(".html") or entry.startswith(("compare", "share-card")):
                continue
            page = os.path.abspath(os.path.join(target, entry))
            if os.path.commonpath([target, page]) != target or not os.path.isfile(page):
                continue
            with open(page, encoding="utf-8") as f:
                text = f.read()
            if REPORT_BRAND in text:
                with open(page, "w", encoding="utf-8") as f:
                    f.write(text.replace(REPORT_BRAND, brand, 1))
                changed += 1
        return changed

    @staticmethod
    def _fill_overview(path: str, folder: str, section: str) -> None:
        """Put ``section`` in the place a report's overview keeps for it,
        replacing what an earlier portfolio put there; nothing when the page
        is missing or keeps no place (a report made before there was one)."""
        base = os.path.abspath(path)
        page = os.path.abspath(os.path.join(base, folder, "index.html"))
        if os.path.commonpath([base, page]) != base or not os.path.isfile(page):
            return
        with open(page, encoding="utf-8") as f:
            text = f.read()
        start = text.find(INSIGHTS_START)
        end = text.find(INSIGHTS_END, start)
        if start < 0 or end < 0:
            return
        text = text[: start + len(INSIGHTS_START)] + section + text[end:]
        with open(page, "w", encoding="utf-8") as f:
            f.write(text)

    def _group_projects(self, group: str) -> str:
        """How a sentence names a group's projects: its title, or "<name>
        projects"; "" without a group."""
        if not group or group not in dict(self.groups):
            return ""
        return self.group_titles.get(group) or f"{dict(self.groups)[group]} projects"

    def _organization_link(self, name: str, prefix: str = "") -> str:
        """An organization's name, linked to its page when it has one."""
        if name not in self.organization_page_names:
            return html.escape(name)
        href = html.escape(f"{prefix}orgs/{name}.html", quote=True)
        return f'<a href="{href}">{html.escape(name)}</a>'

    def _write_organization_files(
        self, path: str, row: dict[str, Any], title: str, repositories: int, ai: bool
    ) -> None:
        """An organization's page, its badge, and the badge's shields.io endpoint."""
        name = row["organization"]
        message = organization_badge_message(row)
        files = (
            ("svg", render_badge(title, message)),
            ("json", endpoint_json(title, message, "#4a7ab5")),
        )
        for extension, text in files:
            f = self._open_portfolio_file(path, f"orgs/{name}.{extension}")
            try:
                f.write(text)
            finally:
                f.close()
        f = self._open_portfolio_file(path, f"orgs/{name}.html")
        try:
            self._write_organization_page(f, row, title, repositories, message, ai)
        finally:
            f.close()

    def _write_organization_page(
        self,
        f: Any,
        row: dict[str, Any],
        title: str,
        repositories: int,
        message: str,
        ai: bool = False,
    ) -> None:
        """One organization: its commits to each repository of the portfolio,
        and its badge with the markup to show it."""
        name = row["organization"]
        page = f"orgs/{name}.html"
        heading = f"{name} in {title}"
        description = (
            f"{name} in {title}: {message}, counted by the domain of its commit addresses."
        )
        self._print_header(
            f, heading, self._share_tags(heading, description, page, "share-card.png"), "../"
        )
        self._print_nav(f, title, "organizations.html", ai, prefix="../")
        f.write(f"<h1>{html.escape(name)}</h1>")
        f.write(
            f'<p class="portfolio-subtitle"><a href="../index.html">{html.escape(title)}</a>, '
            f"{format_int(repositories)} repositories &middot; generated by gitstats "
            f"{html.escape(self.version or get_version())} on "
            f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>"
        )
        f.write(
            '<p class="section-note">How it is counted: a commit counts here when the '
            f"author&rsquo;s email address is at {html.escape(name)} or under it, and at "
            "least two people commit from the domain. A domain says where an address is, "
            "not who paid for the work, so these are lower bounds.</p>"
        )
        recent = [repo for repo in row["by_repository"] if repo["commits_last_12mo"]]
        first = min((repo["first_commit"] for repo in row["by_repository"]), default="")
        f.write(
            stat_tiles_html(
                [
                    (
                        "Commits (12 mo)",
                        format_int(row["commits_last_12mo"]),
                        f"to {len(recent)} of these repositories",
                    ),
                    (
                        "Repositories",
                        format_int(len(row["by_repository"])),
                        "it has committed to",
                    ),
                    ("Commits", format_int(row["commits"]), f"since {html.escape(first)}"),
                ]
            )
        )

        f.write("<h2>Repositories</h2>")
        f.write('<div class="table-scroll"><table class="sortable" id="organization-repos">')
        f.write(
            '<tr><th>Repository</th><th class="num">Commits (12 mo)</th>'
            '<th class="num">Commits</th><th class="num">Addresses</th>'
            "<th>First commit</th><th>Last commit</th></tr>"
        )
        for repo in row["by_repository"]:
            link = repo["report"]
            if link.endswith("index.html"):
                link = link[: -len("index.html")] + "authors.html#commits_by_organization"
            f.write(
                f'<tr><td><a href="../{html.escape(link, quote=True)}">'
                f"{html.escape(repo['name'])}</a></td>"
                f'<td class="num">{format_int(repo["commits_last_12mo"])}</td>'
                f'<td class="num">{format_int(repo["commits"])}</td>'
                f'<td class="num">{format_int(repo["addresses"])}</td>'
                f'<td class="nowrap">{html.escape(repo["first_commit"])}</td>'
                f'<td class="nowrap">{html.escape(repo["last_commit"])}</td></tr>'
            )
        f.write("</table></div>")

        f.write("<h2>Badge</h2>")
        site = self.site_url
        image = f"{site}orgs/{name}.svg" if site else f"orgs/{name}.svg"
        target = f"{site}orgs/{name}.html" if site else f"orgs/{name}.html"
        markdown = f"[![{title}]({image})]({target})"
        f.write(
            '<p class="section-note">For a README or an open source program&rsquo;s page. It '
            "is made again with the portfolio, so it stays current. A shields.io "
            f'<a href="{html.escape(name, quote=True)}.json">endpoint</a> is next to it, for '
            "badges in other styles.</p>"
        )
        f.write(
            f'<p><img src="{html.escape(name, quote=True)}.svg" '
            f'alt="{html.escape(title, quote=True)}: {html.escape(message, quote=True)}"></p>'
        )
        f.write(f'<pre class="badge-code">{html.escape(markdown)}</pre>')
        self._print_footer(f)

    def _organization_mix_row(self, entry: dict[str, Any]) -> str:
        """One repository's row of the By repository table: its name links to
        the organizations of its report, or to the report when it has none."""
        link = entry["report"]
        if link.endswith("index.html") and link in self.organization_sections:
            link = link[: -len("index.html")] + "authors.html#commits_by_organization"
        cells = "".join(
            # sorted by the exact share: "<0.1%" alone would make the column text
            f'<td class="num" data-sort="{_fraction(entry["by_kind"].get(kind, 0), entry["commits"])}">'
            f"{share_text(entry['by_kind'].get(kind, 0), entry['commits'])}</td>"
            for kind in ORGANIZATION_KINDS
        )
        named = ", ".join(
            f"{self._organization_link(row['organization'])} ({format_int(row['commits'])})"
            for row in entry["organizations_last_12mo"][:3]
        )
        group = _group_attr(str(entry.get("group", "") or "")) if self.groups else ""
        return (
            f'<tr{group}><td><a href="{html.escape(link, quote=True)}">'
            f"{html.escape(entry['name'])}</a></td>"
            f'<td class="num">{format_int(entry["commits"])}</td>{cells}'
            f"<td>{named or '&ndash;'}</td></tr>"
        )

    @staticmethod
    def _write_organization_tiles(
        f: Any, organizations: list[dict[str, Any]], repositories: list[dict[str, Any]]
    ) -> None:
        """Headline numbers: how many organizations, the one in the most
        repositories, and the repository whose commits come most from them."""
        active = [row for row in organizations if row["commits_last_12mo"]]
        tiles = [
            (
                "Organizations",
                format_int(len(active)),
                f"with commits in the last 12 months, of {format_int(len(organizations))}",
            )
        ]
        # the page is only written when there is an organization
        widest = max(
            organizations,
            key=lambda row: (len(row["repositories"]), row["commits_last_12mo"]),
        )
        tiles.append(
            (
                "In the Most Repositories",
                # a narrow tile breaks a domain before a dot, not inside a name
                html.escape(widest["organization"]).replace(".", "<wbr>."),
                f"{len(widest['repositories'])} of {len(repositories)} repositories",
            )
        )
        counted = [entry for entry in repositories if entry["commits"]]
        if counted:
            top = min(counted, key=_organization_share_key)
            tiles.append(
                (
                    "Largest Share",
                    share_text(top["by_kind"].get(ORGANIZATION, 0), top["commits"]),
                    f"of {html.escape(top['name'])}&rsquo;s commits come from organizations",
                )
            )
        f.write(stat_tiles_html(tiles))

    def _ai_row(
        self,
        summary: dict[str, Any],
        ai: dict[str, Any] | None,
        counts: list[tuple[int, int] | None],
    ) -> str:
        """One repository's row of the AI-assisted commits table."""
        link = summary.get("report_path", "") or ""
        if link.endswith("index.html"):
            link = link[: -len("index.html")] + "authors.html"
            if ai and ai.get("commits"):
                link += "#ai-assisted_commits"
        cells = "".join(self._ai_cell(quarter) for quarter in counts)
        named = ", ".join(
            html.escape(name) for name in list((ai or {}).get("assistants") or {})[:2]
        )
        group = _group_attr(str(summary.get("group", "") or "")) if self.groups else ""
        return (
            f'<tr{group}><td><a href="{html.escape(link, quote=True)}">'
            f"{html.escape(summary.get('name', ''))}</a></td>{cells}"
            f"<td>{named or '&ndash;'}</td></tr>"
        )

    @staticmethod
    def _share_card(summaries: list[dict[str, Any]], title: str) -> str:
        """The portfolio's share card: its repositories, the largest first."""
        commits = sum(int(s.get("total_commits", 0) or 0) for s in summaries)
        authors: set[str] = set()
        for summary in summaries:
            authors.update((summary.get("author_commits") or {}).keys())
        # a line may break between two names, never inside one, and the dot
        # between them stays with the name before it
        names = [
            html.escape(summary.get("name", "")).replace(" ", "&nbsp;")
            for summary in sorted(summaries, key=lambda s: -int(s.get("total_commits", 0) or 0))
        ]
        sub = f"{format_int(len(summaries))} repositories &middot; {format_int(commits)} commits"
        if authors:
            sub += f" &middot; {format_int(len(authors))} authors"
        return share_card_page(
            title,
            f'<div class="brand">// GitStats</div><h1>{html.escape(title)}</h1>'
            f'<p class="sub">{sub}</p><p class="names">{"&nbsp;&middot; ".join(names)}</p>',
        )

    @staticmethod
    def _ai_share_card(rows: list[AiRow], quarters: list[tuple[str, list[str]]]) -> str:
        """The share card of the AI-assisted commits page: the largest shares
        of the last quarter, as bars."""
        latest = [
            (summary.get("name", ""), counts[-1])
            for summary, _, counts in rows
            if counts[-1] and counts[-1][0] and counts[-1][1] >= MIN_RANKED_COMMITS
        ][:6]
        top = max((part / whole for _, (part, whole) in latest), default=1.0) or 1.0
        bars = "".join(
            f"<div><b>{html.escape(name)}</b>"
            f'<i style="width:{100 * part / whole / top:.1f}%"></i>'
            f"<span>{share_text(part, whole)}</span></div>"
            for name, (part, whole) in latest
        )
        return share_card_page(
            "AI-assisted commits: GitStats",
            '<div class="brand">// AI-assisted commits</div>'
            f"<h1>{html.escape(quarters[-1][0])}</h1>"
            f'<p class="sub">The share of each repository&rsquo;s commits that name an AI coding '
            f"assistant, of {format_int(len(rows))} repositories. A lower bound.</p>"
            f'<div class="bars">{bars}</div>',
        )

    @staticmethod
    def _ai_cell(counts: tuple[int, int] | None) -> str:
        """One repository's quarter: its share, shaded, with the two counts under it."""
        if counts is None:
            return '<td class="share">&ndash;</td>'
        part, whole = counts
        if not whole:
            # a quarter without commits has no share, not a share of nothing
            return '<td class="share"><small>no commits</small></td>'
        ratio = part / whole if whole else 0.0
        # one hue, darker for more; a square root, so that a few per cent still shows
        strength = 0 if ratio <= 0 else 10 + 65 * min(1.0, ratio / 0.6) ** 0.5
        return (
            f'<td class="share" style="--share-strength: {strength:.0f}%">'
            f"{share_text(part, whole) if part else '0%'}"
            f"<small>{format_int(part)} / {format_int(whole)}</small></td>"
        )

    @staticmethod
    def _write_ai_tiles(
        f: Any,
        rows: list[tuple[dict[str, Any], dict[str, Any] | None, list[tuple[int, int] | None]]],
        quarters: list[tuple[str, list[str]]],
    ) -> None:
        """Headline numbers, each about the repositories one by one: shares are
        not added up across them, where the largest would decide the total."""
        naming = sum(
            1 for _, _, counts in rows if any(quarter and quarter[0] for quarter in counts)
        )
        tiles = [
            (
                "Repositories",
                f"{naming} of {len(rows)}",
                "name an assistant in the last four quarters",
            )
        ]
        summary, _, counts = rows[0]
        latest = counts[-1]
        if latest and latest[0] and latest[1] >= MIN_RANKED_COMMITS:
            tiles.append(
                (
                    "Largest Share",
                    share_text(*latest),
                    f"{html.escape(summary.get('name', ''))}, {quarters[-1][0]}",
                )
            )
        # the assistant named in the most repositories, then in the most commits
        repositories: dict[str, int] = {}
        commits: dict[str, int] = {}
        for _, ai, _ in rows:
            for name, count in ((ai or {}).get("assistants") or {}).items():
                repositories[name] = repositories.get(name, 0) + 1
                commits[name] = commits.get(name, 0) + int(count)
        if repositories:
            name = max(repositories, key=lambda key: (repositories[key], commits[key], key))
            tiles.append(
                (
                    "Named Most Widely",
                    html.escape(name),
                    f"in {repositories[name]} of {len(rows)} repositories",
                )
            )
        f.write(stat_tiles_html(tiles))

    def _share_tags(self, title: str, description: str, page: str, image: str) -> str:
        """The tags a link to one of the portfolio's pages is previewed by."""
        return share_meta_html(
            title,
            description,
            self.site_url,
            page,
            image if load_config().get("share_card") else "",
        )

    def _print_header(self, f: Any, title: str, share: str = "", prefix: str = "") -> None:
        """The head of a portfolio page; ``prefix`` leads from the page's
        folder to the output root ("../" for a page in a folder)."""
        f.write(
            """<!DOCTYPE html>
<html lang="en">
<head>
	<meta charset="UTF-8">
	<meta name="viewport" content="width=device-width, initial-scale=1.0">
	<title>{}</title>
	{}
	<!-- Apply theme before CSS loads to prevent flash of unstyled content -->
	{}
	<link rel="stylesheet" href="{}{}" type="text/css">
	<meta name="generator" content="GitStats {}">
	<script type="text/javascript" src="{}sortable.js"></script>
	{}
</head>
<body>
{}
""".format(
                html.escape(page_title(title)),
                share,
                THEME_INIT_SCRIPT,
                prefix,
                load_config()["style"],
                html.escape(self.version or get_version()),
                prefix,
                THEME_SCRIPT,
                SKIP_LINK,
            )
        )

    def _print_nav(
        self,
        f: Any,
        title: str,
        current: str = "index.html",
        ai: bool = False,
        prefix: str = "",
    ) -> None:
        """The nav bar; ``current`` is the page it marks, and ``prefix`` leads
        from the page's folder to the output root."""
        current = prefix + current
        ai_link = nav_link(f"{prefix}ai.html", "AI-assisted commits", current=current) if ai else ""
        if self.organizations:
            ai_link += nav_link(f"{prefix}organizations.html", "Organizations", current=current)
        for href, label in self.nav:
            ai_link += nav_link(html.escape(f"{prefix}{href}", quote=True), html.escape(label))
        f.write(
            f"""
            {NAV_START}
            <a href="{prefix}index.html" class="nav-brand">GitStats</a>
            <ul>
            {nav_link(f"{prefix}index.html", html.escape(title), current=current)}
            {ai_link}
            </ul>
            <div class="nav-right">
            {THEME_TOGGLE_BUTTON}
            </div>
            {NAV_END}
            """
        )

    @staticmethod
    def _write_totals(f: Any, summaries: list[dict[str, Any]]) -> None:
        distinct_authors: set[str] = set()
        for summary in summaries:
            distinct_authors.update((summary.get("author_commits") or {}).keys())
        total_commits = sum(s.get("total_commits", 0) for s in summaries)
        commits_12mo = sum(s.get("commits_last_12mo", 0) for s in summaries)
        active_repos = sum(1 for s in summaries if s.get("commits_last_12mo", 0) > 0)
        total_lines = sum(s.get("total_lines", 0) for s in summaries)

        # Stat tiles, like the top of every repository report
        f.write(
            stat_tiles_html(
                [
                    (
                        "Repositories",
                        format_int(len(summaries)),
                        f"{format_int(active_repos)} active in the last 12 months",
                    ),
                    (
                        "Commits",
                        format_int(total_commits),
                        f"{format_int(commits_12mo)} in the last 12 months",
                    ),
                    (
                        "Authors",
                        format_int(len(distinct_authors)),
                        "distinct, across all repositories",
                    ),
                    ("Lines of Code", format_int(total_lines), "all repositories at HEAD"),
                ]
            )
        )

    @staticmethod
    def _write_repo_table(
        f: Any, summaries: list[dict[str, Any]], groups: list[tuple[str, str]] | None = None
    ) -> None:
        f.write("<h2>Repositories</h2>")
        names = dict(groups or [])
        if names:
            f.write(group_filter_html(summaries, groups or []))
        f.write('<div class="table-scroll"><table class="sortable" id="portfolio">')
        f.write(
            "<tr><th>Repository</th>"
            + ('<th class="portfolio-group">Ecosystem</th>' if names else "")
            + '<th>Health</th><th class="num">Commits</th><th class="num">Authors</th>'
            '<th class="num">Active (12 mo)</th><th class="num">Files</th><th class="num">Lines of Code</th>'
            "<th>Last Commit</th><th>Since</th></tr>"
        )
        ordered = sorted(summaries, key=lambda s: -s.get("total_commits", 0))
        for summary in ordered:
            name = html.escape(summary.get("name", ""))
            link = html.escape(summary.get("report_path", ""), quote=True)
            era = summary.get("era", "")
            era_html = (
                f'<span class="history-era history-era-{html.escape(era)}">{html.escape(era)}</span>'
                if era
                else ""
            )
            last_commit = html.escape((summary.get("last_commit", "") or "")[:10])
            since = html.escape((summary.get("first_commit", "") or "")[:4])
            group = str(summary.get("group", "") or "")
            group_cell = (
                f'<td class="portfolio-group">{html.escape(names.get(group, ""))}</td>'
                if names
                else ""
            )
            f.write(
                f"<tr{_group_attr(group) if names else ''}>"
                f'<td><a href="{link}">{name}</a></td>{group_cell}'
                f"<td>{era_html}</td>"
                f'<td class="num">{format_int(summary.get("total_commits", 0))}</td>'
                f'<td class="num">{format_int(summary.get("total_authors", 0))}</td>'
                f'<td class="num">{format_int(summary.get("active_authors_12mo", 0))}</td>'
                f'<td class="num">{format_int(summary.get("total_files", 0))}</td>'
                f'<td class="num">{format_int(summary.get("total_lines", 0))}</td>'
                f"<td>{last_commit}</td>"
                f"<td>{since}</td></tr>"
            )
        f.write("</table></div>")
        f.write(
            '<p class="section-note">Authors are people: accounts named &hellip;[bot] are '
            "left out, so a report, which counts them, can say more. Active: those whose last "
            "commit is in the 12 months up to the report.</p>"
        )
        if names:
            f.write(GROUP_FILTER_SCRIPT)

    @staticmethod
    def _write_failures(f: Any, failures: list[dict[str, str]]) -> None:
        if not failures:
            return
        f.write("<h2>Failed repositories</h2>")
        f.write('<div class="table-scroll"><table>')
        f.write("<tr><th>Repository</th><th>Error</th></tr>")
        for failure in failures:
            f.write(
                f"<tr><td>{html.escape(failure.get('name', ''))}</td>"
                f"<td>{html.escape(failure.get('error', ''))}</td></tr>"
            )
        f.write("</table></div>")
