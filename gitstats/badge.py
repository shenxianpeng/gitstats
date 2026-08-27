# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
"""Render shareable SVG badges for a generated gitstats report.

Badges are written next to ``index.html`` so that wherever the report is
hosted (GitHub Pages, GitLab Pages, Netlify, an internal web server, ...)
they are served from the same place and can be embedded in a README:

    [![GitStats](https://example.com/report/badge.svg)](https://example.com/report/)

Each badge is a self-contained vector image in the familiar shields.io
style, using the gitstats brand palette, and shows live repository data so
it refreshes automatically every time the report is regenerated.

Static hosting cannot vary a response on query parameters, so customization
works through files and configuration instead:

- ``badge.svg`` — the default badge; its metric, label, color and style are
  chosen with the ``badge_*`` config keys (``-c badge_metric=last-commit``).
- ``badges/<metric>.svg`` — every metric, pre-rendered, so switching what
  the badge says is just switching the URL.
- ``badges/<metric>.json`` — the same data in the shields.io endpoint
  schema. Users who want full URL-parameter customization can point
  ``https://img.shields.io/endpoint?url=...&style=...&color=...`` at these
  and get every shields style/color option while the numbers stay ours.
"""

import json
import logging
import os
from typing import Any

from gitstats import load_config
from gitstats.utils import format_int

logger = logging.getLogger(__name__)

BADGE_FILENAME = "badge.svg"
BADGES_DIRNAME = "badges"

# Brand palette (matches gitstats.css)
_LABEL_BG = "#211e1e"  # OpenCode warm near-black
_VALUE_BG = "#4a7ab5"  # report link/bar blue
_BAR_COLORS = ("#9be9a8", "#40c463", "#30a14e")  # heatmap greens

# Familiar shields.io color names, resolvable in badge_color.
_NAMED_COLORS = {
    "brightgreen": "#4c1",
    "green": "#97ca00",
    "yellowgreen": "#a4a61d",
    "yellow": "#dfb317",
    "orange": "#fe7d37",
    "red": "#e05d44",
    "blue": "#007ec6",
    "lightgrey": "#9f9f9f",
    "lightgray": "#9f9f9f",
}

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

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


def _count(value: Any, noun: str) -> str:
    """Format ``value`` with a pluralized noun: (1, "commit") -> "1 commit"."""
    suffix = "" if value == 1 else "s"
    return f"{format_int(value)} {noun}{suffix}"


def resolve_color(color: str) -> str:
    """Map shields.io color names to hex; pass anything else through."""
    return _NAMED_COLORS.get(color.lower(), color)


def badge_metrics(data: Any) -> dict[str, str]:
    """Return the message text of every available badge metric."""
    last = data.get_last_commit_date()
    return {
        "commits": _count(data.get_total_commits(), "commit"),
        "last-commit": f"{_MONTHS[last.month - 1]} {last.year}",
        "authors": _count(data.get_total_authors(), "author"),
        "files": _count(data.get_total_files(), "file"),
        "lines": _count(data.get_total_loc(), "line"),
    }


def render_badge(label: str, value: str, color: str = "", style: str = "flat") -> str:
    """Return the SVG markup for a badge reading ``label | value``.

    ``color`` overrides the value-segment background (shields color name,
    hex, or any SVG color). ``style`` is "flat" (3px radius, subtle
    gradient) or "flat-square" (sharp corners, solid fill — matches the
    report's angular terminal aesthetic).
    """
    icon_x = 5  # left padding before the icon
    icon_w = 13
    gap = 4  # gap between icon and label text
    pad = 5  # padding around text blocks

    value_bg = resolve_color(color) if color else _VALUE_BG

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

    if style == "flat-square":
        shine = ""
        clip = ""
        clip_open = "<g>"
    else:
        shine = f'<rect width="{total_w:.0f}" height="20" fill="url(#s)"/>'
        clip = f'<clipPath id="r"><rect width="{total_w:.0f}" height="20" rx="3" fill="#fff"/></clipPath>'
        clip_open = '<g clip-path="url(#r)">'

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_w:.0f}" height="20" role="img" aria-label="{title}">
  <title>{title}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  {clip}
  {clip_open}
    <rect width="{label_w:.0f}" height="20" fill="{_LABEL_BG}"/>
    <rect x="{label_w:.0f}" width="{value_w:.0f}" height="20" fill="{value_bg}"/>
    {shine}
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


def _endpoint_json(label: str, message: str, color: str) -> str:
    """Return shields.io endpoint-schema JSON for a badge."""
    return json.dumps(
        {
            "schemaVersion": 1,
            "label": label,
            "message": message,
            "color": color.lstrip("#"),
        },
        indent=2,
    )


def create_badges(data: Any, path: str) -> str:
    """Write the badge set into the report directory; return the default badge path.

    Writes ``badge.svg`` (metric chosen by the ``badge_metric`` config key)
    plus ``badges/<metric>.svg`` and ``badges/<metric>.json`` for every
    metric. All honor the ``badge_label``, ``badge_color`` and
    ``badge_style`` config keys. Regenerating the report keeps every badge
    up to date automatically.
    """
    conf = load_config()
    label = str(conf.get("badge_label", "") or "gitstats")
    color = str(conf.get("badge_color", "") or "")
    style = str(conf.get("badge_style", "") or "flat")
    if style not in ("flat", "flat-square"):
        logger.warning(f"Unknown badge_style '{style}', using 'flat'")
        style = "flat"

    metrics = badge_metrics(data)

    metric = str(conf.get("badge_metric", "") or "commits")
    if metric not in metrics:
        logger.warning(
            f"Unknown badge_metric '{metric}', using 'commits' (available: {', '.join(metrics)})"
        )
        metric = "commits"

    endpoint_color = resolve_color(color) if color else _VALUE_BG

    badges_dir = os.path.join(path, BADGES_DIRNAME)
    os.makedirs(badges_dir, exist_ok=True)
    for name, message in metrics.items():
        with open(os.path.join(badges_dir, f"{name}.svg"), "w", encoding="utf-8") as f:
            f.write(render_badge(label, message, color, style))
        with open(os.path.join(badges_dir, f"{name}.json"), "w", encoding="utf-8") as f:
            f.write(_endpoint_json(label, message, endpoint_color))

    badge_path = os.path.join(path, BADGE_FILENAME)
    with open(badge_path, "w", encoding="utf-8") as f:
        f.write(render_badge(label, metrics[metric], color, style))
    return badge_path
