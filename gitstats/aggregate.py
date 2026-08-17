"""Multi-repository aggregation: per-repo summaries and the portfolio page.

When gitstats is run with several repositories, each repository gets its own
full report in a subdirectory and this module assembles the portfolio view:
a machine-readable ``summary.json`` per repository plus one aggregate
``index.html`` at the output root with a sortable overview table.

The computation functions are pure — they read collector attributes only and
issue no git commands — mirroring ``compute_project_history`` and
``compute_code_ownership`` in ``report_creator``.
"""

import datetime
import html
import json
import logging
import os
import re
import shutil
from typing import Any

from gitstats import load_config
from gitstats.report_creator import _classify_eras
from gitstats.utils import get_version

logger = logging.getLogger("gitstats")

conf = load_config()

_SECONDS_PER_DAY = 86400
_ACTIVE_WINDOW_DAYS = 365


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

    def _iso(stamp: int) -> str:
        return datetime.datetime.fromtimestamp(stamp).isoformat(sep=" ") if stamp else ""

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
        if os.path.commonpath([base, summary_file]) != base or not os.path.isfile(summary_file):
            continue
        try:
            with open(summary_file, encoding="utf-8") as f:
                summaries.append(json.load(f))
        except (OSError, ValueError):
            logger.warning(f"Skipping unreadable summary: {summary_file}")
    return summaries


class AggregateReportCreator:
    """Render the portfolio page for a multi-repository run."""

    def create(
        self,
        summaries: list[dict[str, Any]],
        failures: list[dict[str, str]],
        path: str,
        title: str = "GitStats Portfolio",
    ) -> None:
        self._copy_assets(path)
        f = self._open_portfolio_file(path)
        try:
            self._write_page(f, summaries, failures, title)
        finally:
            f.close()

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
            "arrow-up.gif",
            "arrow-down.gif",
            "arrow-none.gif",
        ):
            src = os.path.join(basedir, file)
            target = os.path.abspath(os.path.join(base, os.path.basename(file)))
            if os.path.commonpath([base, target]) != base:
                raise ValueError(f"Refusing to write outside report directory: {file}")
            if os.path.exists(src):
                shutil.copyfile(src, target)

    @staticmethod
    def _open_portfolio_file(path: str) -> Any:
        """Open the portfolio index for writing, confined to the output root.

        The filename is fixed; resolving the target and checking it stays
        under the output root guards against directory traversal.
        """
        base = os.path.abspath(path)
        target = os.path.abspath(os.path.join(base, "index.html"))
        if os.path.commonpath([base, target]) != base:
            raise ValueError(f"Refusing to write outside report directory: {path}")
        return open(target, "w", encoding="utf-8")

    def _write_page(
        self,
        f: Any,
        summaries: list[dict[str, Any]],
        failures: list[dict[str, str]],
        title: str,
    ) -> None:
        self._print_header(f, title)
        self._print_nav(f, title)

        f.write(f"<h1>{html.escape(title)}</h1>")
        generated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(
            f'<p class="portfolio-subtitle">{len(summaries)} repositories &middot; '
            f"generated by gitstats {html.escape(get_version())} on {generated}</p>"
        )

        self._write_totals(f, summaries)
        self._write_repo_table(f, summaries)
        self._write_failures(f, failures)

        f.write(
            '<div class="footer">'
            '<span class="footer-generated">Generated by '
            '<a href="https://github.com/shenxianpeng/gitstats" target="_blank" rel="noopener">gitstats</a>'
            "</span>"
            "</div>\n"
        )
        f.write("</body>\n</html>")

    @staticmethod
    def _print_header(f: Any, title: str) -> None:
        f.write(
            """<!DOCTYPE html>
<html lang="en">
<head>
	<meta charset="UTF-8">
	<meta name="viewport" content="width=device-width, initial-scale=1.0">
	<title>GitStats - {}</title>
	<!-- Apply theme before CSS loads to prevent flash of unstyled content -->
	<script>(function(){{var t=localStorage.getItem('theme')||'light';document.documentElement.setAttribute('data-theme',t);}})();</script>
	<link rel="stylesheet" href="{}" type="text/css">
	<meta name="generator" content="GitStats {}">
	<script type="text/javascript" src="sortable.js"></script>
	<script>
		function toggleTheme() {{
			const currentTheme = document.documentElement.getAttribute('data-theme');
			const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
			document.documentElement.setAttribute('data-theme', newTheme);
			localStorage.setItem('theme', newTheme);
			updateThemeIcon(newTheme);
		}}

		function updateThemeIcon(theme) {{
			const button = document.getElementById('theme-toggle');
			if (button) {{
				button.innerHTML = theme === 'dark' ? '☀️' : '\U0001f319';
				button.setAttribute('aria-label', theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode');
			}}
		}}

		document.addEventListener('DOMContentLoaded', function() {{
			updateThemeIcon(document.documentElement.getAttribute('data-theme'));
		}});
	</script>
</head>
<body>
""".format(html.escape(title), load_config()["style"], get_version())
        )

    @staticmethod
    def _print_nav(f: Any, title: str) -> None:
        f.write(
            f"""
            <div class="nav">
            <a href="index.html" class="nav-brand">GitStats</a>
            <ul>
            <li><a href="index.html">{html.escape(title)}</a></li>
            </ul>
            <div class="nav-right">
            <button id="theme-toggle" class="theme-toggle" onclick="toggleTheme()" aria-label="Switch to dark mode">\U0001f319</button>
            </div>
            </div>
            """
        )

    @staticmethod
    def _write_totals(f: Any, summaries: list[dict[str, Any]]) -> None:
        distinct_authors: set[str] = set()
        for summary in summaries:
            distinct_authors.update((summary.get("author_commits") or {}).keys())
        total_commits = sum(s.get("total_commits", 0) for s in summaries)
        total_lines = sum(s.get("total_lines", 0) for s in summaries)
        total_tags = sum(s.get("total_tags", 0) for s in summaries)
        last_commit = max((s.get("last_commit", "") for s in summaries), default="")

        f.write("<h2>Totals</h2>")
        f.write("<table border='1' cellspacing='0' cellpadding='4'>")
        f.write(f"<tr><td>Repositories</td><td>{len(summaries)}</td></tr>")
        f.write(f"<tr><td>Total Commits</td><td>{total_commits}</td></tr>")
        f.write(f"<tr><td>Distinct Authors</td><td>{len(distinct_authors)}</td></tr>")
        f.write(f"<tr><td>Total Lines of Code</td><td>{total_lines}</td></tr>")
        f.write(f"<tr><td>Total Tags</td><td>{total_tags}</td></tr>")
        f.write(f"<tr><td>Last Commit</td><td>{html.escape(last_commit)}</td></tr>")
        f.write("</table>")

    @staticmethod
    def _write_repo_table(f: Any, summaries: list[dict[str, Any]]) -> None:
        f.write("<h2>Repositories</h2>")
        f.write('<table class="sortable" id="portfolio">')
        f.write(
            "<tr><th>Repository</th><th>Health</th><th>Commits</th><th>Authors</th>"
            "<th>Active (12 mo)</th><th>Files</th><th>Lines</th>"
            "<th>Last Commit</th><th>Age (days)</th></tr>"
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
            f.write(
                f'<tr><td><a href="{link}">{name}</a></td>'
                f"<td>{era_html}</td>"
                f"<td>{summary.get('total_commits', 0)}</td>"
                f"<td>{summary.get('total_authors', 0)}</td>"
                f"<td>{summary.get('active_authors_12mo', 0)}</td>"
                f"<td>{summary.get('total_files', 0)}</td>"
                f"<td>{summary.get('total_lines', 0)}</td>"
                f"<td>{last_commit}</td>"
                f"<td>{summary.get('age_days', 0)}</td></tr>"
            )
        f.write("</table>")

    @staticmethod
    def _write_failures(f: Any, failures: list[dict[str, str]]) -> None:
        if not failures:
            return
        f.write("<h2>Failed Repositories</h2>")
        f.write("<table border='1' cellspacing='0' cellpadding='4'>")
        f.write("<tr><th>Repository</th><th>Error</th></tr>")
        for failure in failures:
            f.write(
                f"<tr><td>{html.escape(failure.get('name', ''))}</td>"
                f"<td>{html.escape(failure.get('error', ''))}</td></tr>"
            )
        f.write("</table>")
