#!/usr/bin/env python3
"""Assemble the gallery portfolio page from per-repository summaries.

Each subdirectory of the gallery root holds one repository's full gitstats
report plus the ``summary.json`` the run produced. This script rewrites each
summary's ``report_path`` to point into its subdirectory and renders the
aggregate portfolio page (totals, sortable table, health badges) at
``<gallery_root>/index.html`` — the same page a multi-repository
``gitstats repo1 repo2 ... out/`` run generates.

Usage:
    python scripts/generate_gallery_portfolio.py <gallery_root>
"""

import json
import os
import sys

from gitstats.aggregate import AggregateReportCreator


def load_gallery_summaries(gallery_root: str) -> list[dict]:
    """Read every ``<gallery_root>/<dir>/summary.json``, one per repository.

    Each candidate path is resolved and checked to stay under the gallery
    root before reading, so crafted directory entries cannot escape it.
    """
    base = os.path.realpath(gallery_root)
    summaries = []
    for entry in sorted(os.listdir(base)):
        summary_file = os.path.realpath(os.path.join(base, os.path.basename(entry), "summary.json"))
        if os.path.commonpath([base, summary_file]) != base:
            continue
        if not os.path.isfile(summary_file):
            continue
        with open(summary_file, encoding="utf-8") as f:
            summary = json.load(f)
        summary["report_path"] = f"{entry}/index.html"
        if not summary.get("name"):
            summary["name"] = entry
        summaries.append(summary)
    return summaries


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    gallery_root = sys.argv[1]
    if not os.path.isdir(gallery_root):
        print(f"Not a directory: {gallery_root}", file=sys.stderr)
        return 1

    summaries = load_gallery_summaries(gallery_root)
    if not summaries:
        print(f"No summary.json found under {gallery_root}", file=sys.stderr)
        return 1

    AggregateReportCreator().create(summaries, [], gallery_root, title="GitStats Gallery")
    print(f"Portfolio page written for {len(summaries)} repositories: {gallery_root}/index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
