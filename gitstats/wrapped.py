"""Generate a shareable "Repo Wrapped" SVG card for a Git repository.

Inspired by Spotify Wrapped: a square card of one year in the repository,
with that year's commits, active days, longest streak, lines changed,
contributors, busiest month and weekday, top contributor and the commits
in each month. Nothing on the card is an all-time number.

Each number is set against the year before: the whole of it for a year that
is over, and the same days of it for the year under way, so that a card made
in December does not hold eleven months against twelve.

Next to a report the card comes with its numbers as data
(``wrapped-<year>.json``), a page that shows it and helps to share it
(``wrapped.html``), and that page's share card (``wrapped-card.html``).
"""

from __future__ import annotations

import datetime
import html
import io
import json
import logging
import os
from typing import Any

from gitstats.report_creator import (
    compute_project_history,
    is_bot,
    plural,
    share_card_page,
)
from gitstats.utils import format_int, get_version

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
        "up": "#6ee7b7",
        "down": "#fda4af",
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
        "up": "#86efac",
        "down": "#fda4af",
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
        "up": "#047857",
        "down": "#be123c",
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

# The six numbers a card can show, and whether each moves by a percentage
# (the large counts) or by a difference (days, people and releases, where
# "+3" says more than "+50%")
COMPARED: dict[str, bool] = {
    "commits": True,
    "active_days": False,
    "longest_streak": False,
    "lines_changed": True,
    "contributors": False,
    "new_contributors": False,
    "releases": False,
}

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


def change(now: int, before: int, relative: bool) -> tuple[int, str] | None:
    """How a number moved from the year before: its direction (1 up, -1 down,
    0 neither) and what is written next to it.

    ``relative`` numbers move by a percentage, or by a factor from ten times
    on ("+900%" is the last percentage), and have no change to show when the
    year before had none of them; the others move by a difference.
    """
    if not relative:
        difference = now - before
        return (difference > 0) - (difference < 0), f"{difference:+,}" if difference else "same"
    if not before:
        return None
    if now >= 10 * before:
        return 1, f"{now / before:.0f}x"
    percent = round(100 * (now - before) / before)
    return (percent > 0) - (percent < 0), f"{percent:+d}%" if percent else "same"


def day_text(day: str) -> str:
    """ "2025-12-05" as a card and a page write it: "December 5"."""
    date = datetime.date.fromisoformat(day)
    return f"{MONTH_NAMES[date.month]} {date.day}"


class WrappedCardGenerator:
    """Generate a shareable SVG "Repo Wrapped" card from collected stats.

    Every number on the card is for one year: the one it is headed with.
    """

    def __init__(
        self,
        data: Any,
        year: int | None = None,
        theme: str = "midnight",
        today: datetime.date | None = None,
    ) -> None:
        self.data = data
        # the day the card is made on: the months after it have not happened yet
        self.today = today or datetime.date.today()
        self.year = year or self.today.year
        self.theme_name = theme
        self.colors = THEMES.get(theme, THEMES["midnight"])
        # the card generate() last wrote, and its numbers; None before it has
        self.svg: str | None = None
        self.stats: dict[str, Any] | None = None

    # ── data extraction helpers ─────────────────────────────────────────────

    def _year_grid(self) -> dict[int, dict[int, int]]:
        """The year's commits as weekday -> hour -> commits ({} if not collected)."""
        by_year = getattr(self.data, "activity_by_hour_of_week_by_year", {}) or {}
        grid: dict[int, dict[int, int]] = by_year.get(self.year, {})
        return grid

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

    def _under_way(self) -> bool:
        """Whether the card is for the year it is made in, which is not over."""
        return self.year == self.today.year

    def _previous(self) -> dict[str, Any] | None:
        """The year before, as far into it as the card's year has come: all
        of it when the card's year is over, and up to the same day when it is
        under way (February 28 for a February 29 the year before lacks).

        Counted the way the card's own numbers are, from what the collector
        gathered. None when there is nothing to compare with: the year before
        has no commits in those days, or the data does not say which days its
        commits were made on (it was collected before they were kept).
        """
        year = self.year - 1
        end = datetime.date(year, 12, 31)
        if self._under_way():
            try:
                end = self.today.replace(year=year)
            except ValueError:
                end = datetime.date(year, 2, 28)
        first, through = f"{year}-01-01", end.isoformat()

        def within(day: Any) -> bool:
            return first <= str(day) <= through

        by_day = getattr(self.data, "commits_by_day", {}) or {}
        commits = sum(count for day, count in by_day.items() if within(day))
        if not commits:
            return None
        lines = getattr(self.data, "lines_changed_by_day", {}) or {}
        days = sorted(str(day) for day in getattr(self.data, "active_days", ()) if within(day))
        authors = getattr(self.data, "authors", {}) or {}
        by_month = getattr(self.data, "commits_by_month", {}) or {}

        def arrived(info: dict[str, Any]) -> str:
            stamp = info.get("first_commit_stamp")
            return datetime.datetime.fromtimestamp(stamp).strftime("%Y-%m-%d") if stamp else ""

        return {
            "year": year,
            "through": through,
            "commits": commits,
            "active_days": len(days),
            "longest_streak": _longest_streak(days),
            "lines_changed": sum(count for day, count in lines.items() if within(day)),
            "contributors": sum(
                1
                for info in authors.values()
                if any(within(day) for day in info.get("active_days", ()))
            ),
            "new_contributors": sum(
                1 for name, info in authors.items() if not is_bot(name) and within(arrived(info))
            ),
            "releases": sum(
                1
                for info in (getattr(self.data, "tags", {}) or {}).values()
                if within(info.get("date", ""))
            ),
            "monthly_commits": [by_month.get(f"{year}-{month:02d}", 0) for month in range(1, 13)],
        }

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
            # the last day the numbers reach, and whether the year is over
            "through": self.today.isoformat() if self._under_way() else f"{self.year}-12-31",
            "complete": not self._under_way(),
            # the same numbers of the year before, to set them against
            "previous": self._previous(),
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
            sixth = ("Releases", "releases")
        else:
            sixth = ("New Contributors", "new_contributors")
        streak = stats["longest_streak"]
        numbers = [
            ("Commits", "commits", self._format_number(stats["commits"])),
            ("Active Days", "active_days", self._format_number(stats["active_days"])),
            ("Longest Streak", "longest_streak", f"{streak} day{'' if streak == 1 else 's'}"),
            ("Lines Changed", "lines_changed", self._format_number(stats["lines_changed"])),
            ("Contributors", "contributors", self._format_number(stats["contributors"])),
            (sixth[0], sixth[1], self._format_number(stats[sixth[1]])),
        ]
        previous = stats.get("previous")
        months_before = previous["monthly_commits"] if previous else None
        # three columns of 300 with 30 between them fill the content column
        stat_cards = "\n  ".join(
            self._stat_card(
                LEFT + 330 * (i % 3),
                290 + 150 * (i // 3),
                label,
                value,
                change(stats[key], previous[key], COMPARED[key]) if previous else None,
            )
            for i, (label, key, value) in enumerate(numbers)
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
  {self._render_compared(stats)}
  <line x1="{LEFT}" y1="590" x2="{RIGHT}" y2="590" stroke="{c["separator"]}" stroke-width="1"/>

  <!-- When and by whom -->
  {self._render_personality(stats["day_part"])}
  {self._render_facts(stats)}

  <!-- The year month by month -->
  {self._render_mini_bar_chart(stats["monthly_commits"], months_before)}

  <!-- Footer -->
  <line x1="{LEFT}" y1="1000" x2="{RIGHT}" y2="1000" stroke="{c["separator"]}" stroke-width="1"/>
  <text x="{WIDTH // 2}" y="1035" font-size="13" fill="{c["footer"]}" text-anchor="middle">Generated by gitstats · github.com/shenxianpeng/gitstats</text>
  </g>
</svg>"""

    def _stat_card(
        self, x: int, y: int, label: str, value: str, moved: tuple[int, str] | None = None
    ) -> str:
        """Render one number in its box (300×120), the pair centered in it,
        and how it ``moved`` from the year before on the line of its label, at
        the right: green when it went up, red when it went down."""
        c = self.colors
        card = (
            f'<rect x="{x}" y="{y}" width="300" height="120" rx="14" '
            f'fill="{c["card_bg"]}" stroke="{c["card_border"]}" stroke-width="1"/>\n'
            f'  <text x="{x + 24}" y="{y + 60}" font-size="36" font-weight="700" '
            f'fill="{c["stat_value"]}">{value}</text>\n'
            f'  <text x="{x + 24}" y="{y + 90}" font-size="14" font-weight="500" '
            f'fill="{c["stat_label"]}" letter-spacing="0.5">{label}</text>'
        )
        if moved is None:
            return card
        direction, text = moved
        color = {1: c["up"], -1: c["down"]}.get(direction, c["stat_label"])
        return card + (
            f'\n  <text x="{x + 276}" y="{y + 90}" font-size="14" font-weight="600" '
            f'fill="{color}" text-anchor="end">{text}</text>'
        )

    def _render_compared(self, stats: dict[str, Any]) -> str:
        """Say, under the six numbers, what they are compared with."""
        previous = stats.get("previous")
        if not previous:
            return ""
        text = f"Compared with {previous['year']}"
        if not stats["complete"]:
            text = (
                f"Compared with the same days of {previous['year']}: "
                f"January 1 to {day_text(previous['through'])}"
            )
        return (
            f'<text x="{RIGHT}" y="580" font-size="13" fill="{self.colors["stat_label"]}" '
            f'text-anchor="end">{text}</text>'
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

    def _render_mini_bar_chart(self, monthly: list[int], previous: list[int] | None = None) -> str:
        """Render the year's commits per month as twelve bars across the card.

        In the year the card is made in, the months still to come have no bar
        and no baseline: a quiet end of the year is not drawn before it happens.

        ``previous`` is the year before, month by month: each of its months
        stands as a narrow bar to the right of this year's, in the place the
        one bar otherwise takes. Only beside the months that are over, as the
        month under way is not yet what the whole month of a year ago was.
        """
        c = self.colors
        # how many of the year's months have begun: only they are drawn
        months = self.today.month if self.year == self.today.year else 12
        peak = max(monthly[:months], default=0)
        if not peak:
            return ""
        title = "MONTHLY COMMITS SO FAR" if months < 12 else "MONTHLY COMMITS"
        before = (previous or [])[: months - 1 if self._under_way() else 12]
        paired = any(before)
        # one height for both years, so a bar and the one beside it compare
        peak = max([peak, *before])

        # twelve bars of 58 with 24 between them fill the content column; with
        # the year before, a bar of 40, 4 apart from one of 14, takes the 58
        slot_w = 58
        bar_w = 40 if paired else slot_w
        step = slot_w + 24
        base_y = 940
        bar_max_h = 90

        parts = [
            f'<text x="{LEFT}" y="826" font-size="13" font-weight="600" '
            f'fill="{c["stat_label"]}" letter-spacing="0.5">{title}</text>'
        ]
        if paired:
            parts += self._bars_of_the_year_before(before, peak, bar_w, step, base_y, bar_max_h)
        for i, commits in enumerate(monthly):
            x = LEFT + i * step
            # the month's name is centered under its place, its count over its bar
            name_x = x + slot_w // 2
            middle = x + bar_w // 2
            if i >= months:
                # a month to come: its name, faint, and nothing above it
                parts.append(
                    f'<text x="{name_x}" y="{base_y + 18}" font-size="11" fill="{c["footer"]}" '
                    f'fill-opacity="0.5" text-anchor="middle">{MONTH_NAMES[i + 1][:3]}</text>'
                )
                continue
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
                f'<text x="{name_x}" y="{base_y + 18}" font-size="11" fill="{c["footer"]}" '
                f'text-anchor="middle">{MONTH_NAMES[i + 1][:3]}</text>'
            )
        return "\n  ".join(parts)

    def _bars_of_the_year_before(
        self, before: list[int], peak: int, bar_w: int, step: int, base_y: int, bar_max_h: int
    ) -> list[str]:
        """The narrow bars of the year before, each to the right of its
        month's own, and above the chart what they are: one of them, and the
        year they stand for. A month without commits then has none."""
        fill = f'fill="{self.colors["stat_label"]}" fill-opacity="0.45"'
        parts = [
            f'<rect x="{RIGHT - 54}" y="816" width="14" height="10" rx="3" {fill}/>',
            f'<text x="{RIGHT}" y="826" font-size="13" fill="{self.colors["stat_label"]}" '
            f'text-anchor="end">{self.year - 1}</text>',
        ]
        for i, commits in enumerate(before):
            if commits:
                h = max(4, round(commits / peak * bar_max_h))
                x = LEFT + i * step + bar_w + 4
                parts.append(
                    f'<rect x="{x}" y="{base_y - h}" width="14" height="{h}" rx="3" {fill}/>'
                )
        return parts

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
        self.svg, self.stats = svg, stats

        if output_path is None:
            output_path = f"gitstats-wrapped-{self.year}.svg"

        directory = base_dir if base_dir else (os.path.dirname(output_path) or ".")
        output_path = _write_within(directory, os.path.basename(output_path), svg)

        logger.info(f"Wrapped card saved: {output_path}")
        return output_path


# ── next to a report: the numbers as data, a page, and its share card ───────

# The version of what wrapped-<year>.json holds: a field that changes its
# name, type or meaning comes with a new one
SCHEMA_VERSION = 1
PAGE = "wrapped.html"
SHARE_CARD = "wrapped-card.html"
# the image the page points to where its link is shared, rendered from SHARE_CARD
SHARE_IMAGE = "wrapped-card.png"

# The seven numbers of a year, as the page lists them
NUMBERS: tuple[tuple[str, str], ...] = (
    ("Commits", "commits"),
    ("Active days", "active_days"),
    ("Longest streak, in days", "longest_streak"),
    ("Lines changed", "lines_changed"),
    ("Contributors", "contributors"),
    ("New contributors", "new_contributors"),
    ("Releases", "releases"),
)

# Fills in the text to post with the page's address, when the page is served
# and --site-url did not say it; copies it; and saves the card as a PNG, drawn
# from the SVG the page carries (#wrapped-data), so that it also works for a
# page opened from a file.
WRAPPED_SCRIPT = r"""<script>
(function() {
	const data = JSON.parse(document.getElementById('wrapped-data').textContent);
	const served = /^https?:$/.test(window.location.protocol);
	const url = data.url || (served ? window.location.href.split(/[?#]/)[0] : '');
	const text = data.text + (url ? ' ' + url : '');
	document.getElementById('wrapped-text').textContent = text;
	document.getElementById('wrapped-x').href =
		'https://twitter.com/intent/tweet?text=' + encodeURIComponent(text);
	document.getElementById('wrapped-bluesky').href =
		'https://bsky.app/intent/compose?text=' + encodeURIComponent(text);

	const copy = document.getElementById('wrapped-copy');
	copy.addEventListener('click', function() {
		navigator.clipboard.writeText(text).then(function() {
			copy.classList.add('is-copied');
			copy.querySelector('span').textContent = 'Copied';
			setTimeout(function() {
				copy.classList.remove('is-copied');
				copy.querySelector('span').textContent = 'Copy';
			}, 1500);
		});
	});

	document.getElementById('wrapped-png').addEventListener('click', function() {
		const source = URL.createObjectURL(new Blob([data.svg], {type: 'image/svg+xml'}));
		const image = new Image();
		image.onload = function() {
			// at the card's own size: under the megabyte some places stop at
			const canvas = document.createElement('canvas');
			canvas.width = canvas.height = data.size;
			canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height);
			URL.revokeObjectURL(source);
			canvas.toBlob(function(blob) {
				const link = document.createElement('a');
				link.href = URL.createObjectURL(blob);
				link.download = data.png;
				link.click();
				URL.revokeObjectURL(link.href);
			}, 'image/png');
		};
		image.src = source;
	});
})();
</script>"""


def card_data(stats: dict[str, Any], theme: str, card: str) -> dict[str, Any]:
    """What ``wrapped-<year>.json`` holds: the numbers of a card, with the
    file it is and the theme it is drawn in."""
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_by": f"gitstats {get_version()}",
        "generated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "card": card,
        "theme": theme,
        **stats,
    }


def write_card_data(directory: str, stats: dict[str, Any], theme: str, card: str) -> str:
    """Write a card's numbers next to it, in ``directory``; the file's name."""
    name = f"wrapped-{stats['year']}.json"
    text = json.dumps(card_data(stats, theme, card), indent=2, ensure_ascii=False)
    _write_within(directory, name, text + "\n")
    return name


def period_text(stats: dict[str, Any]) -> str:
    """The days a card's numbers cover, in a sentence: "in 2025", or "from
    January 1 to December 5, 2025" for a year under way."""
    if stats["complete"]:
        return f"in {stats['year']}"
    return f"from January 1 to {day_text(stats['through'])}, {stats['year']}"


def compared_text(stats: dict[str, Any]) -> str:
    """What a card's numbers are compared with, to end a sentence with; ""
    when with nothing."""
    previous = stats["previous"]
    if not previous:
        return ""
    if stats["complete"]:
        return f", compared with {previous['year']}"
    return f", compared with the same days of {previous['year']}"


def summary_text(stats: dict[str, Any]) -> str:
    """The year in one sentence: what a link to the page says under its
    title, and what the line to post starts with."""
    previous = stats["previous"]
    commits = plural(stats["commits"], "commit")
    moved = change(stats["commits"], previous["commits"], True) if previous else None
    if moved and moved[0]:
        days = "" if stats["complete"] else "the same days of "
        commits += f" ({moved[1]} on {days}{previous['year']})"
    so_far = "" if stats["complete"] else " so far"
    return (
        f"{stats['project_name']} in {stats['year']}{so_far}: {commits}, "
        f"{plural(stats['contributors'], 'contributor')}, "
        f"{plural(stats['active_days'], 'active day')}."
    )


def _moved_html(stats: dict[str, Any], key: str) -> str:
    """How one number moved from the year before, as a span coloured by its
    direction; "" when there is no year before, or nothing to say."""
    previous = stats["previous"]
    moved = change(stats[key], previous[key], COMPARED[key]) if previous else None
    if not moved:
        return ""
    direction, text = moved
    name = {1: "wrapped-up", -1: "wrapped-down"}.get(direction, "wrapped-same")
    return f'<span class="{name}">{html.escape(text)}</span>'


def numbers_table_html(stats: dict[str, Any]) -> str:
    """The year's numbers as a table: beside those of the year before, and
    how each moved, when there is one to compare with."""
    previous = stats["previous"]
    head = f'<th></th><th class="num">{stats["year"]}</th>'
    if previous:
        head += f'<th class="num">{previous["year"]}</th><th class="num">Change</th>'
    rows = ""
    for label, key in NUMBERS:
        rows += f'<tr><td>{label}</td><td class="num">{format_int(stats[key])}</td>'
        if previous:
            rows += (
                f'<td class="num">{format_int(previous[key])}</td>'
                f'<td class="num">{_moved_html(stats, key)}</td>'
            )
        rows += "</tr>"
    return (
        '<div class="table-scroll"><table class="wrapped-numbers">'
        f"<tr>{head}</tr>{rows}</table></div>"
    )


def share_card_html(stats: dict[str, Any]) -> str:
    """The page's share card: the repository, the year, four of its numbers
    with how they moved, and its commits month by month."""
    name = stats["project_name"]
    tiles = "".join(
        f"<div><dt>{label}</dt><dd>{format_int(stats[key])}{_moved_html(stats, key)}</dd></div>"
        for label, key in (
            ("Commits", "commits"),
            ("Contributors", "contributors"),
            ("Active days", "active_days"),
            ("Lines changed", "lines_changed"),
        )
    )
    # the months that have begun: a month to come is not a month without commits
    months = datetime.date.fromisoformat(stats["through"]).month
    monthly = stats["monthly_commits"][:months]
    top = max(monthly, default=0) or 1
    columns = "".join(f'<i style="height:{100 * count / top:.1f}%"></i>' for count in monthly)
    period = period_text(stats) + compared_text(stats)
    return share_card_page(
        f"{name}: Repo Wrapped {stats['year']}",
        f'<div class="brand">// Repo Wrapped {stats["year"]}</div><h1>{html.escape(name)}</h1>'
        f'<p class="sub">{period[0].upper()}{period[1:]}</p><dl class="tiles">{tiles}</dl>'
        f'<div class="history"><div class="columns">{columns}</div><div class="axis">'
        f"<span>Jan</span><span>commits per month</span>"
        f"<span>{MONTH_NAMES[months][:3]}</span></div></div>",
    )


def page_body_html(card: dict[str, Any], url: str = "") -> str:
    """What the Wrapped page shows between its nav and its footer: the card,
    the year's numbers, and what to share it with. ``url`` is the page's
    public address when the report knows it."""
    stats = card["stats"]
    year, name, file = stats["year"], stats["project_name"], html.escape(str(card["file"]))
    png = f"{os.path.splitext(str(card['file']))[0]}.png"
    text = f"{summary_text(stats)} #RepoWrapped"
    page_data = {"svg": card["svg"], "png": png, "size": WIDTH, "text": text, "url": url}
    return (
        f"<h1>Repo Wrapped {year}</h1>"
        f'<p class="section-note">{html.escape(name)} {period_text(stats)}'
        f"{compared_text(stats)}.</p>"
        '<div class="wrapped-page">'
        f'<a class="wrapped-card" href="{file}"><img src="{file}" width="{WIDTH}" '
        f'height="{HEIGHT}" alt="Repo Wrapped card for {html.escape(name)} in {year}"></a>'
        '<div class="wrapped-side">'
        f"{numbers_table_html(stats)}"
        '<p class="wrapped-actions"><button type="button" id="wrapped-png">Download PNG</button>'
        f'<a href="{file}" download>Download SVG</a>'
        f'<a href="{html.escape(str(card["data"]))}">Data</a></p>'
        "<h2>Share it</h2>"
        '<p class="section-note">Save the card as a PNG and post it as an image, with a '
        "line like this one:</p>"
        '<div class="wrapped-share">'
        f'<pre class="badge-code" id="wrapped-text">{html.escape(f"{text} {url}".strip())}</pre>'
        '<button type="button" class="badge-copy" id="wrapped-copy" '
        'aria-label="Copy the text to post"><span>Copy</span></button></div>'
        '<p class="more-link"><a id="wrapped-x" target="_blank" rel="noopener" '
        'href="https://twitter.com/intent/tweet">Post on X &rarr;</a> &middot; '
        '<a id="wrapped-bluesky" target="_blank" rel="noopener" '
        'href="https://bsky.app/intent/compose">Post on Bluesky &rarr;</a> &middot; '
        '<a href="badges.html#repo_wrapped">Show it in a README &rarr;</a></p>'
        "</div></div>"
        '<script type="application/json" id="wrapped-data">'
        + json.dumps(page_data).replace("</", "<\\/")
        + "</script>"
        + WRAPPED_SCRIPT
    )


def write_wrapped_page(report: Any, path: str, card: dict[str, Any]) -> None:
    """Write the Wrapped page of a report, and the page's share card, into
    the report directory ``path``.

    ``report`` is the HTMLReportCreator that wrote the other pages: the page
    gets its header, nav and footer. ``card`` is what the report shows the
    card by, with its numbers (``stats``), its SVG (``svg``) and the name of
    its data file (``data``).
    """
    stats = card["stats"]
    url = f"{report.site_url}{PAGE}" if report.site_url else ""
    page = io.StringIO()
    report.print_header(page, PAGE, image=SHARE_IMAGE, description=summary_text(stats))
    report.print_nav(page, PAGE)
    page.write(page_body_html(card, url))
    report.print_footer(page)
    page.write("</body></html>")
    _write_within(path, PAGE, page.getvalue())
    _write_within(path, SHARE_CARD, share_card_html(stats))


def remove_wrapped_page(path: str) -> None:
    """Remove the Wrapped page an earlier run left in the report directory
    ``path``, with its share card: a report without a card links to neither,
    and their numbers would be those of that run."""
    for name in (PAGE, SHARE_CARD):
        target = os.path.join(os.path.abspath(path), name)
        if os.path.isfile(target):
            os.remove(target)
