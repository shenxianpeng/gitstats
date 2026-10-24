#!/usr/bin/env python3
"""Assemble the gallery portfolio page from per-repository summaries.

Each subdirectory of the gallery root holds one repository's full gitstats
report plus the ``summary.json`` the run produced. This script rewrites each
summary's ``report_path`` to point into its subdirectory and renders the
aggregate portfolio page (totals, sortable table, health badges) at
``<gallery_root>/index.html`` — the same page a multi-repository
``gitstats repo1 repo2 ... out/`` run generates.

Usage:
    python scripts/generate_gallery_portfolio.py <gallery_root> [--repos repos.yml]
        [--site-url URL] [--share-card]

``--repos`` is the gallery's list of repositories (gallery/repos.yml): the
pages then group the reports by ecosystem, and list the repositories that
have no report, so one that failed does not stop the others. Each ecosystem
also gets its ranking page under ecosystems/ (see gallery_ecosystems.py),
and the gallery its sitemap.xml when ``--site-url`` is given.

``--site-url`` is the gallery's public address; with ``--share-card`` too, its
pages point to their share cards as images (share-card.png and
ai-share-card.png), which are left to render from the HTML the script writes.

Every report page also gets a note at its end: how to make the report for
another repository, and on its overview the Markdown of its badge of
AI-assisted commits, when the report has one.

Run from a checkout, gitstats does not know its version. The gallery's reports
and this page are made from the same commit, so the pages then say the version
the reports were made with.
"""

import argparse
import html
import json
import os
import sys

from gitstats import load_config
from gitstats.aggregate import AggregateReportCreator
from gitstats.utils import get_version

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gallery_ecosystems import FOLDER, in_a_sentence, write_ecosystems  # noqa: E402
from gallery_repos import Group, Repo, RepoListError, load_repos  # noqa: E402

ACTION_URL = "https://github.com/shenxianpeng/gitstats-action"
REQUEST_URL = "https://github.com/shenxianpeng/gitstats/issues/new?template=gallery.yml"
AI_BADGE = "badges/ai-assisted.svg"
# marks a page that already has the note, so that a report kept from an
# earlier build does not get it twice
NOTE_MARK = "<!-- gitstats-gallery-note -->"

# The smallest workflow that publishes the report of a repository, as in the
# gitstats-action README
MINIMAL_WORKFLOW = """\
# .github/workflows/gitstats.yml
name: GitStats Report
on:
  push:
    branches: [main]
permissions:
  contents: write
jobs:
  gitstats:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0
      - uses: shenxianpeng/gitstats-action@v1
        with:
          deploy-to-pages: true
"""

_COPY_SCRIPT = """<script>
document.querySelectorAll('.gallery-note .badge-copy').forEach(function (button) {
	button.addEventListener('click', function () {
		var code = button.parentElement.querySelector('.badge-code').textContent;
		navigator.clipboard.writeText(code).then(function () {
			button.classList.add('is-copied');
			button.querySelector('span').textContent = 'Copied';
			setTimeout(function () {
				button.classList.remove('is-copied');
				button.querySelector('span').textContent = 'Copy';
			}, 1500);
		});
	});
});
</script>"""


def load_gallery_summaries(gallery_root: str, ids: list[str] | None = None) -> list[dict]:
    """Read every ``<gallery_root>/<dir>/summary.json``, one per repository;
    only those of ``ids``, when given, in that order.

    Each candidate path is resolved and checked to stay under the gallery
    root before reading, so crafted directory entries cannot escape it.
    """
    base = os.path.realpath(gallery_root)
    summaries = []
    for entry in sorted(os.listdir(base)) if ids is None else ids:
        summary_file = _inside(base, os.path.basename(entry), "summary.json")
        if not summary_file or not os.path.isfile(summary_file):
            continue
        try:
            with open(summary_file, encoding="utf-8") as f:
                summary = json.load(f)
        except (OSError, ValueError) as error:
            print(f"Skipping unreadable summary: {summary_file} ({error})", file=sys.stderr)
            continue
        if not isinstance(summary, dict):
            print(f"Skipping summary that is not an object: {summary_file}", file=sys.stderr)
            continue
        summary["report_path"] = f"{entry}/index.html"
        if not summary.get("name"):
            summary["name"] = entry
        summaries.append(summary)
    return summaries


def _inside(base: str, *parts: str) -> str:
    """``base/parts...`` resolved, or "" when it resolves outside ``base``."""
    path = os.path.realpath(os.path.join(base, *parts))
    try:
        # a symlink that resolves onto a different drive on Windows, or a UNC
        # path mixed with a local one, cannot be compared: not inside base
        return path if os.path.commonpath([base, path]) == base else ""
    except ValueError:
        return ""


def reports_version(summaries: list[dict]) -> str:
    """The version of gitstats that made the reports, when they all say the
    same one; "" when they do not."""
    versions = {str(summary.get("generated_by", "")) for summary in summaries}
    if len(versions) == 1:
        (made_by,) = versions
        if made_by.startswith("gitstats "):
            return made_by[len("gitstats ") :]
    return ""


def badge_markdown(report_id: str, name: str, site_url: str) -> str:
    """The Markdown of a report's badge of AI-assisted commits, linking to it."""
    report = f"{site_url}{report_id}/" if site_url else ""
    return f"[![AI-assisted commits: {name}]({report}{AI_BADGE})]({report or 'index.html'})"


def report_note(
    report_id: str,
    name: str,
    site_url: str,
    badge: bool,
    group: Group | None = None,
    compared: bool = False,
) -> str:
    """The note at the end of a report page: how the repository compares with
    the others, when ``compared``, the badge, when ``badge``, how it ranks in
    its ``group``, and how to make the report for another repository."""
    parts = [NOTE_MARK, '<section class="gallery-note" id="gallery-note">']
    if compared:
        peers = (
            f"other {in_a_sentence(group.title)}"
            if group is not None
            else "the Gallery's other projects"
        )
        parts.append(
            f'<p class="more-link"><a href="compare.html">How {html.escape(name)} compares '
            f"with {html.escape(peers)} &rarr;</a></p>"
        )
    if group is not None:
        parts.append(
            f'<p class="more-link"><a href="../{FOLDER}/{group.id}.html">How {html.escape(name)} '
            f"ranks among {html.escape(in_a_sentence(group.title))} by AI-assisted commits "
            "&rarr;</a></p>"
        )
    if badge:
        code = badge_markdown(report_id, name, site_url)
        parts.append(
            "<h2>Badge for your README</h2>"
            '<p class="section-note">The share of the last 12 months&rsquo; commits that name '
            "an AI coding assistant, a lower bound, updated every week with this report.</p>"
            '<div class="badge-list"><div class="badge-row">'
            f'<div class="badge-info"><img src="{AI_BADGE}" alt="AI-assisted commits"></div>'
            f'<pre class="badge-code">{html.escape(code)}</pre>'
            '<button type="button" class="badge-copy" aria-label="Copy the Markdown of the '
            'badge"><span>Copy</span></button></div></div>'
        )
    parts.append(_cta_html("../index.html"))
    parts.append("</section>")
    if badge:
        parts.append(_COPY_SCRIPT)
    return "".join(parts)


def gallery_note(groups: list[Group] | None = None) -> str:
    """The note at the end of the gallery's own pages, with a link to each
    ecosystem's ranking."""
    ranked = ""
    if groups:
        links = " &middot; ".join(
            f'<a href="{FOLDER}/{group.id}.html">{html.escape(group.name)}</a>' for group in groups
        )
        ranked = (
            f'<p class="more-link"><a href="{FOLDER}/index.html">Ecosystems ranked by '
            f"AI-assisted commits &rarr;</a> {links}</p>"
        )
    return "".join(
        [
            NOTE_MARK,
            '<section class="gallery-note" id="gallery-note">',
            ranked,
            f'<p class="more-link"><a href="{REQUEST_URL}" target="_blank" rel="noopener">'
            "Add your project to the Gallery &rarr;</a> Open source, on GitHub: suggest it "
            "in an issue.</p>",
            _cta_html(""),
            "</section>",
        ]
    )


def _cta_html(gallery_link: str) -> str:
    gallery = f' &middot; <a href="{gallery_link}">All Gallery reports</a>' if gallery_link else ""
    return (
        '<p class="more-link">Generate this report for your own repository with '
        f'<a href="{ACTION_URL}" target="_blank" rel="noopener">gitstats-action</a>{gallery}'
        "</p>"
        '<details class="table-details"><summary>The smallest workflow</summary>'
        '<p class="section-note">Publishes the report to GitHub Pages on every push to '
        "<code>main</code>: turn on Pages for the <code>gh-pages</code> branch.</p>"
        f'<pre class="badge-code">{html.escape(MINIMAL_WORKFLOW)}</pre></details>'
    )


def add_note(base: str, page: str, note: str) -> bool:
    """Put ``note`` before the footer of the HTML file ``page`` (or before
    ``</body>``), unless it has it already. Whether it was added.

    ``page`` must resolve to an .html file under the directory ``base``:
    nothing else is read or written."""
    base = os.path.realpath(base)
    page = os.path.realpath(page)
    try:
        inside = os.path.commonpath([base, page]) == base
    except ValueError:
        inside = False
    if not inside or page == base or not page.endswith(".html"):
        return False
    try:
        with open(page, encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError):
        return False
    if NOTE_MARK in text:
        return False
    for anchor in ('<div class="footer">', "</body>"):
        at = text.rfind(anchor)
        if at >= 0:
            break
    else:
        return False
    with open(page, "w", encoding="utf-8") as f:
        f.write(text[:at] + note + text[at:])
    return True


def _report_pages(folder: str) -> list[str]:
    """The pages of a report to read: not its share card, nor the comparison
    page and card the portfolio wrote next to them."""
    return [
        entry
        for entry in sorted(os.listdir(folder))
        if entry.endswith(".html") and not entry.startswith(("share-card", "compare"))
    ]


def _add_report_note(
    base: str, summary: dict, site_url: str, groups: dict[str, Group] | None = None
) -> int:
    """Add the note to every page of one report; how many pages got it."""
    report_id = summary["report_path"].split("/", 1)[0]
    folder = _inside(base, report_id)
    if not folder or folder == base or not os.path.isdir(folder):
        return 0
    badge = os.path.isfile(os.path.join(folder, AI_BADGE))
    compared = os.path.isfile(os.path.join(folder, "compare.html"))
    name = str(summary.get("name", ""))
    group = (groups or {}).get(str(summary.get("group", "")))
    added = 0
    for entry in _report_pages(folder):
        note = report_note(
            report_id, name, site_url, badge and entry == "index.html", group, compared
        )
        added += add_note(base, os.path.join(folder, entry), note)
    return added


def add_report_notes(
    gallery_root: str, summaries: list[dict], site_url: str, groups: list[Group] | None = None
) -> int:
    """Add the note to every page of each report; how many pages got it."""
    base = os.path.realpath(gallery_root)
    by_id = {group.id: group for group in groups or []}
    added = sum(_add_report_note(base, summary, site_url, by_id) for summary in summaries)
    for entry in ("index.html", "ai.html", "organizations.html"):
        page = os.path.join(base, entry)
        if os.path.isfile(page):
            added += add_note(base, page, gallery_note(groups))
    return added


def _listed_summaries(
    gallery_root: str, repos_file: str
) -> tuple[list[dict], list[Group], list[Repo], list[dict[str, str]]]:
    """The summaries of the repositories of the list, each with its group;
    the groups and the repositories of the list; and those without a report."""
    repo_groups, repos = load_repos(repos_file)
    summaries = load_gallery_summaries(gallery_root, [repo.id for repo in repos])
    by_id = {repo.id: repo for repo in repos}
    found = set()
    for summary in summaries:
        report_id = summary["report_path"].split("/", 1)[0]
        found.add(report_id)
        summary["group"] = by_id[report_id].group
        # owner/name: its own domain (pytorch.org) is not an employer
        summary["repository"] = by_id[report_id].url
    failures = [
        {"name": repo.name, "error": f"No report: generating it for {repo.url} failed"}
        for repo in repos
        if repo.id not in found
    ]
    for failure in failures:
        print(f"{failure['name']}: {failure['error']}", file=sys.stderr)
    return summaries, repo_groups, repos, failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assemble the gallery portfolio page.")
    parser.add_argument("gallery_root")
    parser.add_argument("--repos", default="", help="the list of repositories, repos.yml")
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

    groups: list[Group] = []
    repos: list[Repo] = []
    failures: list[dict[str, str]] = []
    if args.repos:
        try:
            summaries, groups, repos, failures = _listed_summaries(gallery_root, args.repos)
        except (OSError, RepoListError) as error:
            print(f"{args.repos}: {error}", file=sys.stderr)
            return 1
    else:
        summaries = load_gallery_summaries(gallery_root)
    if not summaries:
        print(f"No summary.json found under {gallery_root}", file=sys.stderr)
        return 1

    version = get_version()
    if version == "dev":
        version = reports_version(summaries) or version
    AggregateReportCreator().create(
        summaries,
        failures,
        gallery_root,
        title="GitStats Gallery",
        site_url=site_url,
        version=version,
        groups=[(group.id, group.name) for group in groups],
        group_titles={group.id: in_a_sentence(group.title) for group in groups},
    )
    ecosystems = write_ecosystems(
        gallery_root, groups, repos, summaries, site_url, args.share_card, version
    )
    pages = add_report_notes(gallery_root, summaries, site_url, ecosystems)
    print(
        f"Portfolio page written for {len(summaries)} repositories: {gallery_root}/index.html"
        + (f" ({len(failures)} without a report)" if failures else "")
        + (f"; {len(ecosystems)} ecosystem pages" if ecosystems else "")
        + f"; notes added to {pages} pages"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
