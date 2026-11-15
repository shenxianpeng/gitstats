# Copyright (c) 2007-2014 Heikki Hokkanen <hoxu@users.sf.net> & others contributors
# GPLv2 / GPLv3
# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
"""Who has changed which files: the bus factor, the files only one person
knows, and the hotspots (the large files that change often).

Computed from what the collector gathered: no git is run here.
"""

import statistics
from typing import Any

from gitstats.utils import is_bot


def compute_code_ownership(author_files: dict[str, dict[str, int]]) -> dict[str, Any]:
    """Derive per-file ownership and per-author stats from author edit counts.

    Args:
        author_files: mapping of author -> file path -> number of commits that
            author made touching the file.

    Bot accounts (names ending in ``[bot]``) are excluded so ownership reflects
    human contributors. Returns a dict with:
        files:   per-file stats (path, edits, owner, owner_edits, ownership_pct,
                 contributors), sorted by edits descending;
        authors: per-author stats (author, files_owned, files_solely_owned,
                 files_touched), sorted by files owned then files touched;
        total_files, single_owner_files;
        bus_factor: the fewest authors who are, between them, primary owner
                 of more than half of the files (0 when there are no files),
                 with bus_factor_authors, their names, largest owner first,
                 and bus_factor_files, how many files they own.
    """
    # Invert to file -> {author: edits}, dropping bots.
    file_authors: dict[str, dict[str, int]] = {}
    for author, files in author_files.items():
        if is_bot(author):
            continue
        for filepath, count in files.items():
            file_authors.setdefault(filepath, {})[author] = count

    files_stats: list[dict[str, Any]] = []
    author_owned: dict[str, int] = {}
    author_solely: dict[str, int] = {}
    author_touched: dict[str, int] = {}
    for filepath, authors in file_authors.items():
        edits = sum(authors.values())
        # Primary owner: most edits; ties broken alphabetically for determinism.
        owner = max(zip(authors.values(), authors.keys()))[1]
        contributors = len(authors)
        files_stats.append(
            {
                "path": filepath,
                "edits": edits,
                "owner": owner,
                "owner_edits": authors[owner],
                "ownership_pct": round(100.0 * authors[owner] / edits, 1) if edits else 0.0,
                "contributors": contributors,
            }
        )
        author_owned[owner] = author_owned.get(owner, 0) + 1
        if contributors == 1:
            author_solely[owner] = author_solely.get(owner, 0) + 1
        for a in authors:
            author_touched[a] = author_touched.get(a, 0) + 1

    files_stats.sort(key=lambda x: x["edits"], reverse=True)

    authors_stats = [
        {
            "author": a,
            "files_owned": author_owned.get(a, 0),
            "files_solely_owned": author_solely.get(a, 0),
            "files_touched": author_touched[a],
        }
        for a in author_touched
    ]
    authors_stats.sort(key=lambda x: (x["files_owned"], x["files_touched"]), reverse=True)

    # Bus factor: take the largest owners until they hold more than half
    bus_authors: list[str] = []
    bus_files = 0
    for stats in authors_stats:
        if not files_stats or 2 * bus_files > len(files_stats):
            break
        author = str(stats["author"])
        bus_authors.append(author)
        bus_files += author_owned.get(author, 0)

    return {
        "files": files_stats,
        "authors": authors_stats,
        "total_files": len(files_stats),
        "single_owner_files": sum(1 for fs in files_stats if fs["contributors"] == 1),
        "bus_factor": len(bus_authors),
        "bus_factor_authors": bus_authors,
        "bus_factor_files": bus_files,
    }


def compute_hotspots(hotspot_files: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Derive the hotspot view from per-file size, churn and score.

    Args:
        hotspot_files: mapping of file path -> ``{"lines", "churn", "score"}``,
            where the score is ``churn * sqrt(lines)``.

    Only files with at least one line and one change can be placed on the
    (logarithmic) size and change axes, so the rest are left out. Returns a
    dict with:
        files:    per-file stats (path, lines, churn, score rounded to one
                  decimal), sorted by score descending;
        median_lines, median_churn: the upper medians over those files, which
                  split the plot into quadrants (0 when there are no files).
    """
    files = []
    for filepath, info in hotspot_files.items():
        lines = info.get("lines", 0)
        churn = info.get("churn", 0)
        if lines > 0 and churn > 0:
            files.append(
                {
                    "path": filepath,
                    "lines": lines,
                    "churn": churn,
                    "score": round(info.get("score", 0.0), 1),
                }
            )
    # ties broken by path for determinism
    files.sort(key=lambda fs: (-fs["score"], fs["path"]))

    if files:
        median_lines = statistics.median_high(fs["lines"] for fs in files)
        median_churn = statistics.median_high(fs["churn"] for fs in files)
    else:
        median_lines = median_churn = 0

    return {
        "files": files,
        "median_lines": median_lines,
        "median_churn": median_churn,
    }


def head_ownership(data: Any) -> dict[str, Any]:
    """compute_code_ownership() over the files that still exist.

    A deleted file carries no bus-factor risk, so when the data knows the
    files at HEAD only those are counted.
    """
    author_files = getattr(data, "author_files", {})
    if not isinstance(author_files, dict):
        author_files = {}
    current = head_files(data)
    if current is not None:
        author_files = {
            author: {p: n for p, n in files.items() if p in current}
            for author, files in author_files.items()
        }
    return compute_code_ownership(author_files)


def head_files(data: Any) -> set[str] | None:
    """Paths of the files at HEAD, or None when the data predates head_files."""
    paths = getattr(data, "head_files", None)
    if isinstance(paths, (list, tuple, set)) and paths:
        return set(paths)
    return None
