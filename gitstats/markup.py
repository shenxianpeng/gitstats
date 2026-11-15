# Copyright (c) 2007-2014 Heikki Hokkanen <hoxu@users.sf.net> & others contributors
# GPLv2 / GPLv3
# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
"""The HTML every page is made of: the theme, the nav and the footer, headings,
stat tiles, and the words numbers are written with.

Shared by the pages of a report (gitstats.pages), the portfolio
(gitstats.aggregate) and the gallery's own pages (scripts/).
"""

import html

from gitstats import load_config
from gitstats.utils import format_int, is_bot

# Runs before the stylesheet loads so the page never flashes the wrong theme.
# An explicit choice from the toggle wins; otherwise follow the OS setting.
THEME_INIT_SCRIPT = (
    "<script>(function(){var t;try{t=localStorage.getItem('theme');}catch(e){}"
    "if(t!=='light'&&t!=='dark'){t=window.matchMedia&&"
    "window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}"
    "document.documentElement.setAttribute('data-theme',t);})();</script>"
)

THEME_SCRIPT = """<script>
	function getCSSVar(v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }

	function setTheme(theme) {
		document.documentElement.setAttribute('data-theme', theme);
		updateThemeIcon(theme);
		document.dispatchEvent(new Event('themechange'));
	}

	function toggleTheme() {
		const newTheme = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
		try { localStorage.setItem('theme', newTheme); } catch (e) {}
		setTheme(newTheme);
	}

	function updateThemeIcon(theme) {
		const button = document.getElementById('theme-toggle');
		if (button) {
			button.setAttribute('aria-label', theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode');
		}
	}

	// Follow OS theme changes until the user picks one with the toggle.
	(function() {
		const query = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)');
		if (!query || !query.addEventListener) return;
		query.addEventListener('change', function(e) {
			let stored = null;
			try { stored = localStorage.getItem('theme'); } catch (err) {}
			if (stored !== 'light' && stored !== 'dark') setTheme(e.matches ? 'dark' : 'light');
		});
	})();

	// The nav scrolls sideways when it does not fit; start with the current page in view.
	function revealCurrentNavItem() {
		const current = document.querySelector('.nav a.active');
		if (!current) return;
		const list = current.closest('ul');
		const item = current.getBoundingClientRect(), box = list.getBoundingClientRect();
		list.scrollLeft += item.left - box.left - (box.width - item.width) / 2;
	}

	// Wide tables scroll sideways on phones, with the first column pinned; mark
	// the ones that actually overflow so only they draw the pinned column's divider.
	function watchScrollBoxes() {
		if (!window.ResizeObserver) return;
		const observer = new ResizeObserver(function(entries) {
			entries.forEach(function(entry) {
				const box = entry.target;
				box.classList.toggle('is-scrollable', box.scrollWidth > box.clientWidth + 1);
			});
		});
		document.querySelectorAll('.table-scroll, .timeline-scroll').forEach(function(box) {
			observer.observe(box);
		});
	}

	document.addEventListener('DOMContentLoaded', function() {
		updateThemeIcon(document.documentElement.getAttribute('data-theme'));
		revealCurrentNavItem();
		watchScrollBoxes();
	});
</script>"""


_THEME_TOGGLE_ICONS = (
    '<svg class="icon-moon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="16" height="16" '
    'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
    'aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>'
    '<svg class="icon-sun" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="16" height="16" '
    'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
    'aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41'
    'M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>'
)

THEME_TOGGLE_BUTTON = (
    '<button id="theme-toggle" class="theme-toggle" onclick="toggleTheme()" '
    f'aria-label="Switch to dark mode">{_THEME_TOGGLE_ICONS}</button>'
)

# Class of a table whose rows are files. A path cannot share a phone's width
# with a few numbers, so under 560px each row is laid out as two lines: the
# path, then the other cells, each named by its ``data-label`` (the column's
# heading), and the header row becomes the sort controls. See gitstats.css.
FILE_TABLE = "file-table"

# Most-read first: the overview, then who and when, what is at risk (knowledge
# held by one person, then large files that keep changing), the code itself,
# the story, and the reference lists; the Badges tool comes last
NAV_PAGES = (
    ("index.html", "General"),
    ("activity.html", "Activity"),
    ("authors.html", "Authors"),
    ("ownership.html", "Code Ownership"),
    ("hotspots.html", "Hotspots"),
    ("files.html", "Files"),
    ("history.html", "History"),
    ("lines.html", "Lines"),
    ("tags.html", "Tags"),
    ("badges.html", "Badges"),
)


# The brand at the start of a report's nav bar. A portfolio that puts the
# report in one of its folders replaces it with the way back to itself.
REPORT_BRAND = '<a href="index.html" class="nav-brand">GitStats</a>'

# The header of a column of share bars: the bars are drawn for the eye only
# (aria-hidden), and a header cell still needs a name
BAR_HEADER = '<th class="unsortable"><span class="visually-hidden">Bar</span></th>'

# A page's frame, the same on every page: the first Tab reaches a link past
# the nav (hidden until then), the nav and the page's own content are
# landmarks, and the footer closes the content.
SKIP_LINK = '<a class="skip-link" href="#main">Skip to content</a>'
NAV_START = '<nav class="nav" aria-label="Pages">'
NAV_END = '</nav>\n<main id="main">'
FOOTER = (
    '</main>\n<footer class="footer"><span class="footer-generated">Generated by '
    '<a href="https://github.com/shenxianpeng/gitstats" target="_blank" rel="noopener">'
    "gitstats</a></span></footer>\n"
)


def nav_link(href: str, label: str, current: str | None = None) -> str:
    """Return a nav ``<li>``, marking it as the current page when ``href == current``."""
    if href == current:
        return f'<li><a href="{href}" class="active" aria-current="page">{label}</a></li>'
    return f'<li><a href="{href}">{label}</a></li>'


_COPY_ICONS = (
    '<svg class="icon-copy" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="14" '
    'height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="12" height="12"/>'
    '<path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/></svg>'
    '<svg class="icon-check" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="14" '
    'height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>'
)


def author_html(name: str) -> str:
    """An author's name, HTML-escaped; a bot account shows a BOT badge in place
    of its "[bot]" suffix, with the full name kept as the badge's tooltip."""
    if not is_bot(name):
        return html.escape(name)
    return (
        f"{html.escape(name[: -len('[bot]')])} "
        f'<span class="badge" title="{html.escape(name)}">bot</span>'
    )


# What makes a commit AI-assisted, folded under the numbers that count them
AI_ASSISTED_COUNTED = (
    '<details class="table-details"><summary>What is counted</summary>'
    "<ul>"
    "<li>The author is an assistant's own account, such as the Copilot coding agent, "
    "Devin or Cursor's agent.</li>"
    "<li>A <code>Co-authored-by:</code> line names an assistant, as Claude Code, "
    "Copilot, Cursor, Codex, Aider and others add when they commit for a person. A "
    "review bot whose suggestion was applied is named the same way.</li>"
    "<li>An <code>Assisted-by:</code> or <code>Generated-by:</code> line names an "
    "assistant.</li>"
    "<li>The message has the line an assistant leaves in it, such as "
    "&ldquo;Generated with [Claude Code]&rdquo; or the link to a Devin or Codex "
    "session.</li>"
    "</ul>"
    "<p>Accounts and addresses are matched, not first names: a person called Claude, "
    "Devin or Jules is not an assistant.</p>"
    "</details>"
)


# The overview page keeps a place, between these two, for what stands out about
# the repository next to the others of a portfolio (see gitstats.insights). A
# report made alone leaves it empty; a portfolio fills it, and fills it again
# when it is made again.
INSIGHTS_START = "<!-- gitstats:insights -->"
INSIGHTS_END = "<!-- /gitstats:insights -->"


def page_title(title: str) -> str:
    """The <title> of a page whose own title is ``title``: what a browser tab
    and a search result show. Each page has its own, with "GitStats" in it
    once."""
    return title if "GitStats" in title else f"GitStats - {title}"


# Why a year with commits can have no lines: see lines_uncounted()
FIRST_PARENT_LINES = (
    "No lines counted: lines are counted along the main line of history (each "
    "commit against its first parent), where the lines of a branch count in the "
    "year it was merged, not in the years its commits were made."
)


# A tag's authors the Tags page lists before folding the rest away: a release
# with 200 authors made the page tens of thousands of pixels tall on a phone
TAG_AUTHORS_SHOWN = 3


def tag_authors_html(names: list[str], commits: dict[str, int], limit: int) -> str:
    """A tag's authors, the most commits first, each with its commits: the
    first TAG_AUTHORS_SHOWN, and the others folded under "+N more". At most
    ``limit`` are named (none is a limit when below 0); the rest are
    counted."""
    named = names if limit < 0 else names[:limit]
    items = [f"{author_html(name)} ({format_int(commits[name])})" for name in named]
    hidden = len(names) - len(named)
    unnamed = f"<em>and {plural(hidden, 'more author')}</em>" if hidden else ""
    shown, folded = items[:TAG_AUTHORS_SHOWN], items[TAG_AUTHORS_SHOWN:]
    text = ", ".join(shown)
    if not folded:
        return ", ".join(part for part in (text, unnamed) if part)
    rest = ", ".join(folded + ([unnamed] if unnamed else []))
    return (
        f'{text} <details class="tag-authors"><summary>+{len(names) - len(shown)} more'
        f"</summary>{rest}</details>"
    )


def lines_uncounted(commits: int, added: int, removed: int) -> bool:
    """Whether a period with ``commits`` has no lines because of how they are
    counted, not because none changed: along the main line of history
    (``linear_linestats``), a branch's lines count when it is merged, and its
    commits' own years show none."""
    return bool(commits) and not added and not removed and bool(load_config()["linear_linestats"])


def plural(count: int, word: str, many: str = "", number: bool = True) -> str:
    """A count and the word for what it counts, singular for one: "1 commit",
    "1,234 commits"; ``many`` when adding "s" is not the plural. Without
    ``number``, the word alone."""
    noun = word if count == 1 else many or f"{word}s"
    return f"{format_int(count)} {noun}" if number else noun


def percent_text(share: float) -> str:
    """A share as the pages write it, to one decimal: "4.1%". One too small to
    show that way is "<0.1%", not "0.0%", and one short of all "99.9%", not
    "100.0%"; none is "0%". Plain text: escape it for a page."""
    if share <= 0:
        return "0%"
    if share < 0.0005:
        return "<0.1%"
    if 0.9995 <= share < 1:
        return "99.9%"
    return f"{100.0 * share:.1f}%"


def share_text(part: int, whole: int) -> str:
    """``part`` as a percentage of ``whole``, as ``percent_text`` writes it,
    for a page: "&lt;0.1%"."""
    if not part or not whole:
        return "0%"
    return html.escape(percent_text(part / whole))


def stat_tiles_html(tiles: list[tuple[str, str, str]]) -> str:
    """Render headline numbers as a grid of stat tiles (KPI cards).

    Each tile is ``(label, value, note)``; ``value`` and ``note`` are inserted
    as HTML, so callers escape any user-controlled text. An empty note is
    left out.

    Wide, medium (<=1024px) and narrow (<=560px) screens get up to 6, 3 and
    2 columns: the largest divisor of the tile count when that gives at least
    two columns (6 tiles -> 6/3/2, 4 -> 4/2/2), otherwise as many columns as
    fit with the last tile spanning the rest of its row (3 tiles on a phone:
    two, then one full width) instead of stacking one per row.
    """

    def columns(limit: int) -> tuple[int, int]:
        """(columns, span of the last tile) for up to ``limit`` columns."""
        n = max(len(tiles), 1)
        cols = next(c for c in range(min(n, limit), 0, -1) if n % c == 0)
        if cols > 1 or n == 1:
            return cols, 1
        cols = min(n, limit)
        return cols, cols - n % cols + 1 if n % cols else 1

    def phrases(note: str) -> str:
        # a note wraps after a " · " between its phrases, never inside one ("per active / day")
        parts = note.split(" &middot; ")
        if len(parts) == 1:
            return note
        return "&nbsp;&middot; ".join(f'<span class="nowrap">{part}</span>' for part in parts)

    items = "".join(
        '<div class="stat-tile">'
        f"<dt>{label}</dt>"
        f'<dd class="stat-value">{value}</dd>'
        + (f'<dd class="stat-note">{phrases(note)}</dd>' if note else "")
        + "</div>"
        for label, value, note in tiles
    )
    style = "; ".join(
        f"--cols{suffix}: {cols}" + (f"; --span{suffix}: {span}" if span > 1 else "")
        for suffix, (cols, span) in (("", columns(6)), ("-md", columns(3)), ("-sm", columns(2)))
    )
    return f'<dl class="stat-tiles" style="{style}">{items}</dl>'


def html_header(level: int, text: str) -> str:
    name = html_linkify(text)
    return '\n<h%d id="%s"><a href="#%s">%s</a></h%d>\n\n' % (
        level,
        name,
        name,
        text,
        level,
    )


def html_linkify(text: str) -> str:
    return text.lower().replace(" ", "_")
