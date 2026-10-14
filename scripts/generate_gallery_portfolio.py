#!/usr/bin/env python3
"""Assemble the gallery portfolio page from per-repository summaries.

Each subdirectory of the gallery root holds one repository's full gitstats
report plus the ``summary.json`` the run produced. This script rewrites each
summary's ``report_path`` to point into its subdirectory and renders the
aggregate portfolio page (totals, sortable table, health badges) at
``<gallery_root>/index.html`` — the same page a multi-repository
``gitstats repo1 repo2 ... out/`` run generates.

Usage:
    python scripts/generate_gallery_portfolio.py <gallery_root> [--site-url URL] [--share-card]

``--site-url`` is the gallery's public address; with ``--share-card`` too, its
pages point to their share cards as images (share-card.png and
ai-share-card.png), which are left to render from the HTML the script writes.
"""

import argparse
import json
import os
import sys

from gitstats import load_config
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
                summary = json.load(f)
        except (OSError, ValueError) as error:
            print(f"Skipping unreadable summary: {summary_file} ({error})", file=sys.stderr)
            continue
        summary["report_path"] = f"{entry}/index.html"
        if not summary.get("name"):
            summary["name"] = entry
        summaries.append(summary)
    return summaries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assemble the gallery portfolio page.")
    parser.add_argument("gallery_root")
    parser.add_argument("--site-url", default="", help="the gallery's public address")
    parser.add_argument("--share-card", action="store_true", help="point to the share cards")
    try:
        args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit:
        print(__doc__, file=sys.stderr)
        return 2
    gallery_root = args.gallery_root
    if not os.path.isdir(gallery_root):
        print(f"Not a directory: {gallery_root}", file=sys.stderr)
        return 1
    site_url = args.site_url
    if site_url and not site_url.endswith("/"):
        site_url += "/"
    load_config()["share_card"] = args.share_card

    summaries = load_gallery_summaries(gallery_root)
    if not summaries:
        print(f"No summary.json found under {gallery_root}", file=sys.stderr)
        return 1

    AggregateReportCreator().create(
        summaries, [], gallery_root, title="GitStats Gallery", site_url=site_url
    )
    print(f"Portfolio page written for {len(summaries)} repositories: {gallery_root}/index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
