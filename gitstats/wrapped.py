"""Generate a shareable "Repo Wrapped" SVG card for a Git repository.

Inspired by Spotify Wrapped: a square card of one year in the repository,
with that year's commits, active days, longest streak, lines changed,
contributors, busiest month and weekday, top contributor and the commits
in each month. Nothing on the card is an all-time number.
"""

from __future__ import annotations

import datetime
import logging
import os
from typing import Any

from gitstats.report_creator import compute_project_history

logger = logging.getLogger("gitstats")


def _write_within(directory: str, filename: str, content: str) -> str:
    """Write ``content`` into ``directory`` under a sanitized file name.

    ``filename`` is reduced to its base name, dropping any directory components
    or traversal segments, so the write cannot escape ``directory`` regardless
    of what the caller passed. ``directory`` must already exist. Returns the
    path written to.
    """
    safe_name = os.path.basename(filename)
    if not safe_name or safe_name in (os.curdir, os.pardir):
        raise ValueError(f"Invalid output file name: {filename!r}")
    base = os.path.abspath(directory)
    target = os.path.abspath(os.path.join(base, safe_name))
    # Validate the constructed path stays within the target directory before
    # touching the filesystem.
    if os.path.commonpath([base, target]) != base:
        raise ValueError(f"Refusing to write outside {base}: {filename!r}")
    with open(target, "w", encoding="utf-8") as f:
        f.write(content)
    return target


# ── Colour themes ──────────────────────────────────────────────────────────

THEMES: dict[str, dict[str, str]] = {
    "midnight": {
        "bg_start": "#0f0c29",
        "bg_mid": "#302b63",
        "bg_end": "#24243e",
        "card_bg": "rgba(255,255,255,0.06)",
        "card_border": "rgba(255,255,255,0.10)",
        "title": "#a78bfa",
        "year": "#ffffff",
        "stat_value": "#ffffff",
        "stat_label": "rgba(255,255,255,0.65)",
        "badge_bg": "rgba(167,139,250,0.15)",
        "badge_text": "#a78bfa",
        "footer": "rgba(255,255,255,0.35)",
        "accent": "#818cf8",
        "separator": "rgba(255,255,255,0.08)",
    },
    "sunset": {
        "bg_start": "#1a0a1e",
        "bg_mid": "#3d1b40",
        "bg_end": "#1e1029",
        "card_bg": "rgba(255,200,150,0.07)",
        "card_border": "rgba(255,200,150,0.15)",
        "title": "#fbbf24",
        "year": "#ffffff",
        "stat_value": "#fde68a",
        "stat_label": "rgba(255,255,255,0.65)",
        "badge_bg": "rgba(251,191,36,0.15)",
        "badge_text": "#fbbf24",
        "footer": "rgba(255,255,255,0.35)",
        "accent": "#fb923c",
        "separator": "rgba(255,255,255,0.08)",
    },
    "clean": {
        "bg_start": "#f8fafc",
        "bg_mid": "#e2e8f0",
        "bg_end": "#f1f5f9",
        "card_bg": "#ffffff",
        "card_border": "#e2e8f0",
        "title": "#6366f1",
        "year": "#1e293b",
        "stat_value": "#0f172a",
        "stat_label": "#64748b",
        "badge_bg": "rgba(99,102,241,0.10)",
        "badge_text": "#6366f1",
        "footer": "#94a3b8",
        "accent": "#6366f1",
        "separator": "#e2e8f0",
    },
}

MONTH_NAMES: dict[int, str] = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}

WEEKDAY_NAMES: dict[int, str] = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}

# The four quarters of the day, and what the card calls a year whose commits
# fall mostly in each: (name, first hour, the hour after the last)
DAY_PARTS: tuple[tuple[str, int, int], ...] = (
    ("Night Owl", 0, 6),
    ("Early Bird", 6, 12),
    ("Afternoon Coder", 12, 18),
    ("Evening Coder", 18, 24),
)

WIDTH = 1080
HEIGHT = 1080
# The content column: everything on the card sits between these two edges
LEFT = 60
RIGHT = 1020


def _longest_streak(days: list[str]) -> int:
    """Longest run of consecutive dates in ``days`` (sorted ``YYYY-MM-DD``)."""
    longest = current = 0
    previous: datetime.date | None = None
    for day in days:
        date = datetime.date.fromisoformat(day)
        current = current + 1 if previous and (date - previous).days == 1 else 1
        longest = max(longest, current)
        previous = date
    return longest


class WrappedCardGenerator:
    """Generate a shareable SVG "Repo Wrapped" card from collected stats.

    Every number on the card is for one year: the one it is headed with.
    """

    def __init__(self, data: Any, year: int | None = None, theme: str = "midnight") -> None:
        self.data = data
        self.year = year or datetime.datetime.now().year
        self.theme_name = theme
        self.colors = THEMES.get(theme, THEMES["midnight"])

    # ── data extraction helpers ─────────────────────────────────────────────

    def _year_grid(self) -> dict[int, dict[int, int]]:
        """The year's commits as weekday -> hour -> commits ({} if not collected)."""
        by_year = getattr(self.data, "activity_by_hour_of_week_by_year", {}) or {}
        return by_year.get(self.year, {})

    def _monthly_commits(self) -> list[int]:
        """The year's commits in each month, January first."""
        by_month = getattr(self.data, "commits_by_month", {}) or {}
        return [by_month.get(f"{self.year}-{month:02d}", 0) for month in range(1, 13)]

    def _busiest_weekday(self) -> str:
        """The weekday with the most of the year's commits ("" if unknown)."""
        totals = {day: sum(hours.values()) for day, hours in self._year_grid().items()}
        if not any(totals.values()):
            return ""
        # a tie goes to the earlier weekday
        return WEEKDAY_NAMES.get(max(sorted(totals), key=lambda day: totals[day]), "")

    def _day_part(self) -> dict[str, Any] | None:
        """The quarter of the day with the most of the year's commits.

        Returns its name, its hours and its share of the commits, or None when
        the hours were not collected. A tie goes to the earlier quarter.
        """
        by_hour: dict[int, int] = {}
        for hours in self._year_grid().values():
            for hour, commits in hours.items():
                by_hour[hour] = by_hour.get(hour, 0) + commits
        total = sum(by_hour.values())
        if not total:
            return None
        counts = [
            sum(commits for hour, commits in by_hour.items() if start <= hour < end)
            for _, start, end in DAY_PARTS
        ]
        name, start, end = DAY_PARTS[counts.index(max(counts))]
        return {"name": name, "start": start, "end": end, "share": max(counts) / total}

    def _collect_stats(self) -> dict[str, Any]:
        """Assemble the card's numbers, every one of them for ``self.year``.

        The per-year account is the History page's, so the two agree. Raises
        ValueError when the year has no commits: a card of zeros, or one that
        fills the year in with the repository's all-time numbers, would say
        something that is not true.
        """
        history = compute_project_history(self.data)
        entry = next(
            (e for e in history["years"] if e["year"] == self.year and e["commits"]),
            None,
        )
        if entry is None:
            last = history["last_year"]
            hint = f"; the last year with commits is {last}" if last else ""
            raise ValueError(f"no commits in {self.year}{hint}")

        days = sorted(
            day
            for day in getattr(self.data, "active_days", ())
            if str(day).startswith(f"{self.year}-")
        )
        monthly = self._monthly_commits()
        return {
            "year": self.year,
            "project_name": getattr(self.data, "project_name", "") or "Repository",
            "commits": entry["commits"],
            "active_days": len(days),
            "longest_streak": _longest_streak(days),
            "lines_changed": entry["lines_added"] + entry["lines_removed"],
            "contributors": entry["active_authors"],
            "new_contributors": len(entry["newcomers"]),
            "releases": len(entry["releases"]),
            # the most active person; a bot only when nobody else committed
            "top_author": entry["top_author"],
            "top_author_commits": entry["top_author_commits"],
            "monthly_commits": monthly,
            # a tie goes to the earlier month
            "busiest_month": MONTH_NAMES[monthly.index(max(monthly)) + 1] if any(monthly) else "",
            "busiest_weekday": self._busiest_weekday(),
            "day_part": self._day_part(),
        }

    # ── SVG rendering ──────────────────────────────────────────────────────

    @staticmethod
    def _format_number(n: int) -> str:
        """Format large numbers: 1234 → '1,234'."""
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n:,}"
        return str(n)

    @staticmethod
    def _clip(text: str, limit: int) -> str:
        """Shorten ``text`` to ``limit`` characters, ending in an ellipsis."""
        return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"

    def _render_card(self, stats: dict[str, Any]) -> str:
        """Render the full SVG card."""
        c = self.colors
        year = stats["year"]

        # The sixth number: the year's releases, or its newcomers when it had
        # no release, so a repository that does not tag still shows a count
        if stats["releases"] or not stats["new_contributors"]:
            sixth = ("Releases", stats["releases"])
        else:
            sixth = ("New Contributors", stats["new_contributors"])
        streak = stats["longest_streak"]
        numbers = [
            ("Commits", self._format_number(stats["commits"])),
            ("Active Days", self._format_number(stats["active_days"])),
            ("Longest Streak", f"{streak} day{'' if streak == 1 else 's'}"),
            ("Lines Changed", self._format_number(stats["lines_changed"])),
            ("Contributors", self._format_number(stats["contributors"])),
            (sixth[0], self._format_number(sixth[1])),
        ]
        # three columns of 300 with 30 between them fill the content column
        stat_cards = "\n  ".join(
            self._stat_card(LEFT + 330 * (i % 3), 290 + 150 * (i // 3), label, value)
            for i, (label, value) in enumerate(numbers)
        )

        return f"""<?xml version="1.0" encoding="utf-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}" font-family="system-ui, -apple-system, sans-serif">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{c["bg_start"]}"/>
      <stop offset="50%" stop-color="{c["bg_mid"]}"/>
      <stop offset="100%" stop-color="{c["bg_end"]}"/>
    </linearGradient>
    <linearGradient id="accent-bar" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="{c["accent"]}"/>
      <stop offset="100%" stop-color="{c["title"]}"/>
    </linearGradient>
    <clipPath id="card">
      <rect width="{WIDTH}" height="{HEIGHT}" rx="32"/>
    </clipPath>
  </defs>

  <!-- Everything is clipped to the card's rounded corners -->
  <g clip-path="url(#card)">
  <rect width="{WIDTH}" height="{HEIGHT}" fill="url(#bg)"/>
  <rect width="{WIDTH}" height="6" fill="url(#accent-bar)"/>

  <!-- Header: the year and the repository -->
  <text x="{LEFT}" y="80" font-size="20" font-weight="600" fill="{c["title"]}" letter-spacing="3">REPO WRAPPED</text>
  <text x="{LEFT}" y="180" font-size="96" font-weight="800" fill="{c["year"]}" letter-spacing="-2">{year}</text>
  <text x="{LEFT}" y="220" font-size="22" fill="{c["stat_label"]}">{self._escape_xml(self._clip(stats["project_name"], 60))}</text>
  <line x1="{LEFT}" y1="250" x2="{RIGHT}" y2="250" stroke="{c["separator"]}" stroke-width="1"/>

  <!-- The year in six numbers -->
  {stat_cards}
  <line x1="{LEFT}" y1="590" x2="{RIGHT}" y2="590" stroke="{c["separator"]}" stroke-width="1"/>

  <!-- When and by whom -->
  {self._render_personality(stats["day_part"])}
  {self._render_facts(stats)}

  <!-- The year month by month -->
  {self._render_mini_bar_chart(stats["monthly_commits"])}

  <!-- Footer -->
  <line x1="{LEFT}" y1="1000" x2="{RIGHT}" y2="1000" stroke="{c["separator"]}" stroke-width="1"/>
  <text x="{WIDTH // 2}" y="1035" font-size="13" fill="{c["footer"]}" text-anchor="middle">Generated by gitstats · github.com/shenxianpeng/gitstats</text>
  </g>
</svg>"""

    def _stat_card(self, x: int, y: int, label: str, value: str) -> str:
        """Render one number in its box (300×120), the pair centered in it."""
        c = self.colors
        return (
            f'<rect x="{x}" y="{y}" width="300" height="120" rx="14" '
            f'fill="{c["card_bg"]}" stroke="{c["card_border"]}" stroke-width="1"/>\n'
            f'  <text x="{x + 24}" y="{y + 60}" font-size="36" font-weight="700" '
            f'fill="{c["stat_value"]}">{value}</text>\n'
            f'  <text x="{x + 24}" y="{y + 90}" font-size="14" font-weight="500" '
            f'fill="{c["stat_label"]}" letter-spacing="0.5">{label}</text>'
        )

    def _render_personality(self, day_part: dict[str, Any] | None) -> str:
        """Render the quarter of the day the year's commits fell in most."""
        if not day_part:
            return ""
        c = self.colors
        share = (
            f"{day_part['share']:.0%} of commits between "
            f"{day_part['start']:02d}:00 and {day_part['end']:02d}:00"
        )
        return (
            f'<text x="{LEFT}" y="640" font-size="15" font-weight="600" '
            f'fill="{c["stat_label"]}" letter-spacing="1">CODING PERSONALITY</text>\n'
            f'  <rect x="{LEFT}" y="660" width="190" height="36" rx="18" fill="{c["badge_bg"]}" '
            f'stroke="{c["badge_text"]}" stroke-width="1" stroke-opacity="0.3"/>\n'
            f'  <text x="{LEFT + 95}" y="684" font-size="15" font-weight="600" '
            f'fill="{c["badge_text"]}" text-anchor="middle">{day_part["name"]}</text>\n'
            f'  <text x="{LEFT + 206}" y="684" font-size="16" fill="{c["stat_label"]}">{share}</text>'
        )

    def _render_facts(self, stats: dict[str, Any]) -> str:
        """Render the busiest month and weekday, and the top contributor."""
        c = self.colors

        def strong(text: str) -> str:
            return f'<tspan fill="{c["accent"]}" font-weight="600">{text}</tspan>'

        busiest = [
            f"{what}: {strong(name)}"
            for what, name in (
                ("Busiest month", stats["busiest_month"]),
                ("Busiest weekday", stats["busiest_weekday"]),
            )
            if name
        ]
        lines = [" · ".join(busiest)] if busiest else []
        if stats["top_author"]:
            commits = stats["top_author_commits"]
            name = self._escape_xml(self._clip(stats["top_author"], 40))
            lines.append(
                f"Top contributor: {strong(name)} · {self._format_number(commits)} "
                f"commit{'' if commits == 1 else 's'}"
            )
        return "\n  ".join(
            f'<text x="{LEFT}" y="{740 + 40 * i}" font-size="16" fill="{c["stat_label"]}">{line}</text>'
            for i, line in enumerate(lines)
        )

    def _render_mini_bar_chart(self, monthly: list[int]) -> str:
        """Render the year's commits per month as twelve bars across the card."""
        c = self.colors
        peak = max(monthly, default=0)
        if not peak:
            return ""

        # twelve bars of 58 with 24 between them fill the content column
        bar_w = 58
        step = bar_w + 24
        base_y = 940
        bar_max_h = 90

        parts = [
            f'<text x="{LEFT}" y="826" font-size="13" font-weight="600" '
            f'fill="{c["stat_label"]}" letter-spacing="0.5">MONTHLY COMMITS</text>'
        ]
        for i, commits in enumerate(monthly):
            x = LEFT + i * step
            middle = x + bar_w // 2
            if commits:
                h = max(4, round(commits / peak * bar_max_h))
                parts.append(
                    f'<rect x="{x}" y="{base_y - h}" width="{bar_w}" height="{h}" rx="4" '
                    f'fill="{c["accent"]}" fill-opacity="0.7"/>'
                )
                parts.append(
                    f'<text x="{middle}" y="{base_y - h - 6}" font-size="11" '
                    f'fill="{c["stat_label"]}" text-anchor="middle">'
                    f"{self._format_number(commits)}</text>"
                )
            else:
                # a month without commits keeps its place as a faint baseline
                parts.append(
                    f'<rect x="{x}" y="{base_y - 2}" width="{bar_w}" height="2" '
                    f'fill="{c["accent"]}" fill-opacity="0.25"/>'
                )
            parts.append(
                f'<text x="{middle}" y="{base_y + 18}" font-size="11" fill="{c["footer"]}" '
                f'text-anchor="middle">{MONTH_NAMES[i + 1][:3]}</text>'
            )
        return "\n  ".join(parts)

    @staticmethod
    def _escape_xml(text: str) -> str:
        """Escape XML special characters."""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )

    # ── public API ──────────────────────────────────────────────────────────

    def generate(self, output_path: str | None = None, base_dir: str | None = None) -> str:
        """Generate the Wrapped card and save to a file.

        Args:
            output_path: Where to save the SVG. Only its file name is used; the
                directory comes from ``base_dir`` (or the path's own directory).
                Auto-generated if None.
            base_dir: Existing directory to write the card into. The card's file
                name is stripped to its base name so a crafted path cannot escape
                this directory.

        Returns:
            The path to the generated SVG file.

        Raises:
            ValueError: the year has no commits, so there is no card to write.
        """
        stats = self._collect_stats()
        svg = self._render_card(stats)

        if output_path is None:
            output_path = f"gitstats-wrapped-{self.year}.svg"

        directory = base_dir if base_dir else (os.path.dirname(output_path) or ".")
        output_path = _write_within(directory, os.path.basename(output_path), svg)

        logger.info(f"Wrapped card saved: {output_path}")
        return output_path
