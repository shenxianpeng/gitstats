# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
"""Render a shareable SVG badge for a generated gitstats report.

The badge is written next to ``index.html`` so that wherever the report is
hosted (GitHub Pages, GitLab Pages, Netlify, an internal web server, ...)
the badge is served from the same place and can be embedded in a README:

    [![GitStats](https://example.com/report/badge.svg)](https://example.com/report/)

It is a self-contained vector image in the familiar shields.io "flat" style,
using the gitstats brand palette, and shows the live commit count so it
refreshes automatically every time the report is regenerated.
"""

import os
from typing import Any

from gitstats.utils import format_int

BADGE_FILENAME = "badge.svg"

# Brand palette (matches gitstats.css)
_LABEL_BG = "#211e1e"  # OpenCode warm near-black
_VALUE_BG = "#4a7ab5"  # report link/bar blue
_BAR_COLORS = ("#9be9a8", "#40c463", "#30a14e")  # heatmap greens

# Approximate character widths for 11px Verdana, the font shields.io uses.
# The rendered text is force-fitted with ``textLength``, so these only need
# to be close enough for pleasant padding.
_NARROW = set("iljI.,':;|!ft[]() ")
_WIDE = set("mwMW@%")


def _text_width(text: str) -> float:
    """Estimate the rendered width in px of ``text`` at 11px Verdana."""
    width = 0.0
    for ch in text:
        if ch in _NARROW:
            width += 4.0
        elif ch in _WIDE:
            width += 10.0
        elif ch.isdigit():
            width += 7.0
        elif ch.isupper():
            width += 8.0
        else:
            width += 6.5
    return width


def render_badge(label: str, value: str) -> str:
    """Return the SVG markup for a flat badge reading ``label | value``."""
    icon_x = 5  # left padding before the icon
    icon_w = 13
    gap = 4  # gap between icon and label text
    pad = 5  # padding around text blocks

    label_tw = _text_width(label)
    value_tw = _text_width(value)

    label_x = icon_x + icon_w + gap
    label_w = label_x + label_tw + pad
    value_w = pad + value_tw + pad + 1
    total_w = label_w + value_w

    # Text coordinates are in shields' 10x scaled space for crisp rendering.
    label_cx = (label_x + label_tw / 2.0) * 10
    label_len = label_tw * 10
    value_cx = (label_w + value_w / 2.0) * 10
    value_len = value_tw * 10

    title = f"{label}: {value}"

    bars = "".join(
        f'<rect x="{x}" y="{y}" width="3" height="{h}" rx="1" fill="{color}"/>'
        for (x, y, h), color in zip(
            ((0.5, 6.0, 7.0), (5.0, 2.5, 10.5), (9.5, 4.5, 8.5)), _BAR_COLORS
        )
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_w:.0f}" height="20" role="img" aria-label="{title}">
  <title>{title}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r">
    <rect width="{total_w:.0f}" height="20" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#r)">
    <rect width="{label_w:.0f}" height="20" fill="{_LABEL_BG}"/>
    <rect x="{label_w:.0f}" width="{value_w:.0f}" height="20" fill="{_VALUE_BG}"/>
    <rect width="{total_w:.0f}" height="20" fill="url(#s)"/>
  </g>
  <g transform="translate({icon_x},3.5)">{bars}</g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" text-rendering="geometricPrecision" font-size="110">
    <text aria-hidden="true" x="{label_cx:.0f}" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)" textLength="{label_len:.0f}">{label}</text>
    <text x="{label_cx:.0f}" y="140" transform="scale(.1)" textLength="{label_len:.0f}">{label}</text>
    <text aria-hidden="true" x="{value_cx:.0f}" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)" textLength="{value_len:.0f}">{value}</text>
    <text x="{value_cx:.0f}" y="140" transform="scale(.1)" textLength="{value_len:.0f}">{value}</text>
  </g>
</svg>
"""


def create_badge_svg(data: Any, path: str) -> str:
    """Write ``badge.svg`` into the report directory and return its path.

    The badge shows the repository's total commit count, so regenerating the
    report keeps the badge up to date automatically.
    """
    value = f"{format_int(data.get_total_commits())} commits"
    badge_path = os.path.join(path, BADGE_FILENAME)
    with open(badge_path, "w", encoding="utf-8") as f:
        f.write(render_badge("gitstats", value))
    return badge_path
