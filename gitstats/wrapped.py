"""Generate a shareable "Repo Wrapped" SVG card for a Git repository.

Inspired by Spotify Wrapped — creates a personality-driven,
social-media-friendly card with the year's key git stats:
commits, streak, night-owl ratio, most active month, and more.
"""

from __future__ import annotations

import datetime
import logging
import os
from typing import Any

logger = logging.getLogger("gitstats")

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

WIDTH = 1080
HEIGHT = 1080


class WrappedCardGenerator:
    """Generate a shareable SVG "Repo Wrapped" card from collected stats."""

    def __init__(
        self,
        data: Any,
        year: int | None = None,
        theme: str = "midnight",
        repo_dir: str | None = None,
    ) -> None:
        self.data = data
        self.year = year or datetime.datetime.now().year
        self.theme_name = theme
        self.repo_dir = repo_dir
        self.colors = THEMES.get(theme, THEMES["midnight"])

    # ── data extraction helpers ─────────────────────────────────────────────

    def _get_total_commits(self) -> int:
        """Return commits for the target year (fall back to total)."""
        yearly = getattr(self.data, "commits_by_year", {})
        return yearly.get(self.year, getattr(self.data, "total_commits", 0))

    def _get_night_owl_ratio(self) -> float:
        """Fraction of commits made between 00:00-05:59."""
        hourly = getattr(self.data, "activity_by_hour_of_day", {})
        total = sum(hourly.values()) or 1
        night = sum(v for h, v in hourly.items() if h < 6)
        return night / total

    def _get_most_active_month(self) -> str:
        """Return the month name with the most commits."""
        monthly = getattr(self.data, "activity_by_month_of_year", {})
        if not monthly:
            return "—"
        best = max(monthly, key=monthly.get)  # type: ignore[arg-type]
        return MONTH_NAMES.get(best, str(best))

    def _get_busiest_weekday(self) -> str:
        """Return the weekday name with the most commits."""
        daily = getattr(self.data, "activity_by_day_of_week", {})
        if not daily:
            return "—"
        best = max(daily, key=daily.get)  # type: ignore[arg-type]
        return WEEKDAY_NAMES.get(best, str(best))

    def _get_total_lines_touched(self) -> int:
        added = getattr(self.data, "total_lines_added", 0)
        removed = getattr(self.data, "total_lines_removed", 0)
        return added + removed

    def _get_top_author(self) -> str:
        authors = getattr(self.data, "authors_by_commits", [])
        return authors[0] if authors else "—"

    def _get_first_commit_year(self) -> int:
        stamp = getattr(self.data, "first_commit_stamp", 0)
        if stamp:
            return datetime.datetime.fromtimestamp(stamp).year
        return self.year

    def _collect_stats(self) -> dict[str, Any]:
        """Assemble all the stats needed for the card."""
        total_commits = self._get_total_commits()
        night_ratio = self._get_night_owl_ratio()
        lines_touched = self._get_total_lines_touched()

        # Fun personality labels
        if night_ratio > 0.4:
            night_label = "Night Owl 🦉"
        elif night_ratio > 0.25:
            night_label = "Evening Coder 🌙"
        elif night_ratio < 0.1:
            night_label = "Early Bird 🌅"
        else:
            night_label = "Balanced ☀️"

        streak = getattr(self.data, "longest_streak", 0)

        return {
            "year": self.year,
            "project_name": getattr(self.data, "project_name", "Repository"),
            "total_commits": total_commits,
            "total_authors": getattr(self.data, "total_authors", 0),
            "total_files": getattr(self.data, "total_files", 0),
            "longest_streak": streak,
            "night_owl_ratio": night_ratio,
            "night_owl_label": night_label,
            "most_active_month": self._get_most_active_month(),
            "busiest_weekday": self._get_busiest_weekday(),
            "top_author": self._get_top_author(),
            "lines_touched": lines_touched,
            "lines_added": getattr(self.data, "total_lines_added", 0),
            "lines_removed": getattr(self.data, "total_lines_removed", 0),
            "active_days": len(getattr(self.data, "active_days", set())),
            "first_commit_year": self._get_first_commit_year(),
            "commits_by_month": getattr(self.data, "activity_by_month_of_year", {}),
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

    def _render_card(self, stats: dict[str, Any]) -> str:
        """Render the full SVG card."""
        c = self.colors
        year = stats["year"]

        # ── accent bar chart for monthly activity ──
        monthly_data = stats.get("commits_by_month", {})
        monthly_chart = self._render_mini_bar_chart(monthly_data)

        return f"""<?xml version="1.0" encoding="utf-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}">
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
  </defs>

  <!-- Background -->
  <rect width="{WIDTH}" height="{HEIGHT}" fill="url(#bg)" rx="32"/>

  <!-- Top accent line -->
  <rect x="0" y="0" width="{WIDTH}" height="6" fill="url(#accent-bar)"/>

  <!-- Header -->
  <text x="60" y="80" font-family="system-ui, -apple-system, sans-serif" font-size="20" font-weight="600" fill="{c["title"]}" letter-spacing="3">
    YOUR {year} IN CODE
  </text>

  <!-- Year – big hero number -->
  <text x="60" y="180" font-family="system-ui, -apple-system, sans-serif" font-size="96" font-weight="800" fill="{c["year"]}" letter-spacing="-2">
    {year}
  </text>

  <!-- Project name -->
  <text x="60" y="220" font-family="system-ui, -apple-system, sans-serif" font-size="22" fill="{c["stat_label"]}">
    {self._escape_xml(stats["project_name"])}
  </text>

  <!-- Separator -->
  <line x1="60" y1="250" x2="1020" y2="250" stroke="{c["separator"]}" stroke-width="1"/>

  <!-- ── Stat grid (3 columns × 2 rows) ── -->
  <!-- Row 1 -->
  {self._stat_card(60, 290, "Total Commits", self._format_number(stats["total_commits"]), c)}
  {self._stat_card(380, 290, "Longest Streak", f"{stats['longest_streak']} days", c)}
  {self._stat_card(700, 290, "Active Days", self._format_number(stats["active_days"]), c)}

  <!-- Row 2 -->
  {self._stat_card(60, 440, "Lines Touched", self._format_number(stats["lines_touched"]), c)}
  {self._stat_card(380, 440, "Contributors", self._format_number(stats["total_authors"]), c)}
  {self._stat_card(700, 440, "Files", self._format_number(stats["total_files"]), c)}

  <!-- ── Bottom section: personality badges + monthly chart ── -->
  <line x1="60" y1="590" x2="1020" y2="590" stroke="{c["separator"]}" stroke-width="1"/>

  <!-- Night owl badge -->
  <text x="60" y="640" font-family="system-ui, -apple-system, sans-serif" font-size="15" font-weight="600" fill="{c["stat_label"]}" letter-spacing="1">
    YOUR CODING PERSONALITY
  </text>

  <rect x="60" y="660" width="260" height="36" rx="18" fill="{c["badge_bg"]}" stroke="{c["badge_text"]}" stroke-width="1" stroke-opacity="0.3"/>
  <text x="190" y="684" font-family="system-ui, -apple-system, sans-serif" font-size="15" font-weight="600" fill="{c["badge_text"]}" text-anchor="middle">
    {stats["night_owl_label"]}
  </text>
  <text x="330" y="684" font-family="system-ui, -apple-system, sans-serif" font-size="14" fill="{c["stat_label"]}">
    {stats["night_owl_ratio"]:.0%} of commits after midnight
  </text>

  <!-- Most active month & weekday -->
  <text x="60" y="740" font-family="system-ui, -apple-system, sans-serif" font-size="14" fill="{c["stat_label"]}">
    <tspan fill="{c["accent"]}" font-weight="600">{stats["most_active_month"]}</tspan> was your most active month
    · <tspan fill="{c["accent"]}" font-weight="600">{stats["busiest_weekday"]}</tspan> was your busiest day
  </text>

  <!-- Top contributor -->
  <text x="60" y="780" font-family="system-ui, -apple-system, sans-serif" font-size="14" fill="{c["stat_label"]}">
    Top contributor: <tspan fill="{c["accent"]}" font-weight="600">{self._escape_xml(stats["top_author"])}</tspan>
  </text>

  <!-- Monthly activity mini-chart -->
  {monthly_chart}

  <!-- Footer -->
  <line x1="60" y1="1000" x2="1020" y2="1000" stroke="{c["separator"]}" stroke-width="1"/>
  <text x="540" y="1035" font-family="system-ui, -apple-system, sans-serif" font-size="13" fill="{c["footer"]}" text-anchor="middle">
    Generated by gitstats · github.com/shenxianpeng/gitstats
  </text>
</svg>"""

    def _stat_card(self, x: int, y: int, label: str, value: str, c: dict[str, str]) -> str:
        """Render a single stat card (300×120 px)."""
        return f"""<rect x="{x}" y="{y}" width="290" height="120" rx="14" fill="{c["card_bg"]}" stroke="{c["card_border"]}" stroke-width="1"/>
  <text x="{x + 20}" y="{y + 35}" font-family="system-ui, -apple-system, sans-serif" font-size="36" font-weight="700" fill="{c["stat_value"]}">
    {value}
  </text>
  <text x="{x + 20}" y="{y + 65}" font-family="system-ui, -apple-system, sans-serif" font-size="13" font-weight="500" fill="{c["stat_label"]}" letter-spacing="0.5">
    {label}
  </text>"""

    def _render_mini_bar_chart(self, monthly_data: dict[int, int]) -> str:
        """Render a tiny bar chart of monthly activity."""
        c = self.colors
        if not monthly_data:
            return ""

        max_val = max(monthly_data.values()) or 1
        bar_w = 50
        gap = 14
        start_x = 60
        bar_y = 840
        bar_max_h = 100

        bars: list[str] = []
        for month_num in range(1, 13):
            val = monthly_data.get(month_num, 0)
            h = max(4, int((val / max_val) * bar_max_h))
            cx = start_x + (month_num - 1) * (bar_w + gap)
            # bar
            bars.append(
                f'<rect x="{cx}" y="{bar_y + bar_max_h - h}" width="{bar_w}" height="{h}" '
                f'rx="4" fill="{c["accent"]}" fill-opacity="0.7"/>'
            )
            # month label
            bars.append(
                f'<text x="{cx + bar_w / 2}" y="{bar_y + bar_max_h + 18}" '
                f'font-family="system-ui, sans-serif" font-size="10" fill="{c["footer"]}" '
                f'text-anchor="middle">{MONTH_NAMES[month_num][:3]}</text>'
            )

        label = (
            f'<text x="{start_x}" y="{bar_y - 12}" '
            f'font-family="system-ui, -apple-system, sans-serif" font-size="13" '
            f'font-weight="600" fill="{c["stat_label"]}" letter-spacing="0.5">'
            f"MONTHLY COMMITS</text>"
        )
        return label + "\n  " + "\n  ".join(bars)

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

    def generate(self, output_path: str | None = None) -> str:
        """Generate the Wrapped card and save to a file.

        Args:
            output_path: Path to save the SVG.  Auto-generated if None.

        Returns:
            The path to the generated SVG file.
        """
        stats = self._collect_stats()
        svg = self._render_card(stats)

        if output_path is None:
            output_path = f"gitstats-wrapped-{self.year}.svg"

        output_path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(svg)

        logger.info(f"Wrapped card saved: {output_path}")
        return output_path
