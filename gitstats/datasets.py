"""The portfolio's data: what its pages show, as files to download.

The AI-assisted commits page comes with ``ai.json`` and ``ai.csv``, and a
snapshot of each quarter that is over (``ai/2026-Q3.json``); the
organizations page with ``organizations.json`` and ``organizations.csv``.
The functions here put those together from the repositories' summaries
(see gitstats.summary), and the pages are written from the same rows.
"""

import csv
import datetime
import io
import json
import os
import re
from typing import Any

from gitstats import compare
from gitstats.employers import KINDS as ORGANIZATION_KINDS
from gitstats.summary import _AI_MONTHS
from gitstats.utils import get_version

_MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


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
        """0 for enough commits to come first, 1 for too few, 2 for no counts."""
        if counts is None:
            return 2
        return 0 if counts[1] >= MIN_RANKED_COMMITS else 1

    rows.sort(
        key=lambda row: (
            place(row[2][-1]),
            -share(row[2][-1]),
            -share(row[2][-2]),
            row[0].get("name", ""),
        )
    )
    return rows, quarters


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


def _read_snapshot(path: str, name: str) -> dict[str, Any] | None:
    """The snapshot ``name`` ("ai/2026-Q3.json") written before into the output
    root ``path``, or None when there is none, or it cannot be read as one.
    Only a snapshot's name, resolved inside the root, is read."""
    if not _SNAPSHOT.fullmatch(name):
        return None
    base = os.path.realpath(path)
    file = os.path.realpath(os.path.join(base, name))
    try:
        if os.path.commonpath([base, file]) != base:
            return None
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


def _snapshot_to_write(
    kept: dict[str, Any] | None, dataset: dict[str, Any], quarter: str
) -> dict[str, Any] | None:
    """The snapshot of ``quarter`` to write: ``kept`` (this portfolio's, read
    back) with the repositories it lacks, or a new one with the repositories
    that have counts for the quarter; None when there is nothing to add."""
    if kept is None or not _same_portfolio(kept, dataset):
        # the first of the quarter, or another portfolio's
        entries = [
            _snapshot_entry(entry, quarter)
            for entry in dataset["repositories"]
            if _has_quarter(entry, quarter)
        ]
        return {
            **dataset,
            "quarters": sorted({key for entry in entries for key in entry["quarters"]}),
            "repositories": entries,
        }
    added = _snapshot_additions(kept, dataset, quarter)
    if not added:
        return None
    # an entry without the quarter gives way to its counts
    replaced = {_repository_key(entry) for entry in added}
    stays = [
        entry
        for entry in kept["repositories"]
        if _has_quarter(entry, quarter) or _repository_key(entry) not in replaced
    ]
    return {
        **kept,
        "quarters": sorted(
            set(kept.get("quarters") or []) | {key for entry in added for key in entry["quarters"]}
        ),
        "repositories": sorted(stays + added, key=lambda entry: str(entry.get("name", "")).lower()),
    }


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


# how many organizations get a page and a badge of their own: the first of
# organizations_dataset, the most commits in the last 12 months first
_ORGANIZATION_PAGES = 200
# a domain, as an organization's page is named after it: "orgs/google.com.html"
_DOMAIN = r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+"


def organization_pages(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    """The organizations of ``organizations_dataset`` that get a page and a
    badge: the first _ORGANIZATION_PAGES whose domain can name a file."""
    return [row for row in dataset["organizations"] if re.fullmatch(_DOMAIN, row["organization"])][
        :_ORGANIZATION_PAGES
    ]
