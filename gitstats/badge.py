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
from dataclasses import dataclass
from typing import Any
from xml.sax.saxutils import escape, quoteattr

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


_VERDANA = "Verdana,Geneva,DejaVu Sans,sans-serif"
_MONO = "IBM Plex Mono,JetBrains Mono,ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"


@dataclass(frozen=True)
class _Style:
    """How a badge style draws its segments."""

    height: int = 20
    radius: int = 3
    font: str = _VERDANA
    font_size: float = 11
    pad: float = 5  # space around each segment's text
    shine: bool = True  # the subtle top-to-bottom gradient
    shadow: bool = True  # the dark text shadow under white text
    icon: bool = True  # the three heatmap bars before the label
    label_bg: str = _LABEL_BG
    label_fg: str = "#fff"
    value_bg: str = _VALUE_BG  # used when a segment brings no color of its own
    value_fg: str = "#fff"
    value_border: str = ""  # outline drawn inside each value segment
    char_width: float = 0  # fixed advance per character (monospace); 0: Verdana
    prefix: str = ""  # drawn before the label, in prefix_fg
    prefix_fg: str = ""


_STYLES = {
    "flat": _Style(),
    "flat-square": _Style(radius=0, shine=False),
    # the report's own look: mono, square, "//" before the label, light value
    "terminal": _Style(
        height=22,
        radius=0,
        font=_MONO,
        font_size=12,
        pad=8,
        shine=False,
        shadow=False,
        icon=False,
        label_fg="#f1ecec",
        value_bg="#f1ecec",
        value_fg="#211e1e",
        value_border="#211e1e",
        char_width=7.2,
        prefix="//",
        prefix_fg="#9e9a9a",
    ),
}


@dataclass(frozen=True)
class Segment:
    """One colored block of a badge: text, or a row of bars (``spark``)."""

    text: str = ""
    bg: str = ""  # empty: the style's value color; set: white text on it
    fg: str = ""  # empty: white on a custom bg, else the style's value color
    spark: tuple[float, ...] = ()  # bar heights, 0..1
    spark_color: str = "#40c463"


def _segment_text_width(text: str, style: _Style) -> float:
    if style.char_width:
        return len(text) * style.char_width
    return _text_width(text) * style.font_size / 11


def render_segments(segments: list[Segment], style_name: str = "flat") -> str:
    """Return the SVG markup of a badge made of ``segments``, left to right.

    The first segment is the label and takes the style's label colors and
    icon; the others are values. ``style_name`` is a key of ``_STYLES``.
    """
    style = _STYLES.get(style_name, _STYLES["flat"])
    height = style.height
    icon_w, icon_gap = (13, 4) if style.icon else (0, 0)

    # Lay the segments out left to right
    blocks = []
    x = 0.0
    prefix_w = _segment_text_width(style.prefix + " ", style) if style.prefix else 0.0
    for index, seg in enumerate(segments):
        lead = (style.pad + icon_w + icon_gap) if index == 0 and style.icon else style.pad
        if index == 0:
            lead += prefix_w
        if seg.spark:
            content_w: float = len(seg.spark) * 4 - 1
        else:
            content_w = _segment_text_width(seg.text, style)
        width = lead + content_w + style.pad + (1 if index else 0)
        blocks.append((seg, x, width, lead, content_w))
        x += width
    total_w = round(x)

    title = segments[0].text + ": " + ", ".join(s.text for s in segments[1:] if s.text)
    parts = []
    for index, (seg, bx, bw, lead, cw) in enumerate(blocks):
        bg = style.label_bg if index == 0 else resolve_color(seg.bg or style.value_bg)
        bg = escape(bg, {'"': "&quot;"})
        parts.append(f'<rect x="{bx:.0f}" width="{bw:.0f}" height="{height}" fill="{bg}"/>')
        if index and style.value_border and not seg.bg:
            parts.append(
                f'<rect x="{round(bx) + 0.5}" y="0.5" width="{round(bw) - 1}" height="{height - 1}" '
                f'fill="none" stroke="{style.value_border}"/>'
            )

    marks = []
    texts = []
    baseline = height / 2 + style.font_size * 0.36
    for index, (seg, bx, bw, lead, cw) in enumerate(blocks):
        if seg.spark:
            base = height - 5
            span = height - 10
            for i, level in enumerate(seg.spark):
                h = max(1.0, span * level)
                marks.append(
                    f'<rect x="{bx + lead + i * 4:.1f}" y="{base - h:.1f}" width="3" '
                    f'height="{h:.1f}" fill="{escape(seg.spark_color)}"/>'
                )
            continue
        if index == 0:
            fg = style.label_fg
        else:
            fg = seg.fg or ("#fff" if seg.bg else style.value_fg)
        cx = bx + lead + cw / 2
        text = escape(seg.text)
        if style.shadow:
            texts.append(
                f'<text aria-hidden="true" x="{cx:.1f}" y="{baseline + 1:.1f}" fill="#010101" '
                f'fill-opacity=".3" textLength="{cw:.1f}">{text}</text>'
            )
        texts.append(
            f'<text x="{cx:.1f}" y="{baseline:.1f}" fill="{escape(fg)}" '
            f'textLength="{cw:.1f}">{text}</text>'
        )

    if style.prefix:
        texts.append(
            f'<text x="{style.pad + prefix_w / 2:.1f}" y="{baseline:.1f}" '
            f'fill="{style.prefix_fg}">{escape(style.prefix)}</text>'
        )

    icon = ""
    if style.icon:
        bars = "".join(
            f'<rect x="{bx}" y="{by}" width="3" height="{bh}" rx="1" fill="{color}"/>'
            for (bx, by, bh), color in zip(
                ((0.5, 6.0, 7.0), (5.0, 2.5, 10.5), (9.5, 4.5, 8.5)), _BAR_COLORS
            )
        )
        icon = f'<g transform="translate({style.pad:g},{(height - 13) / 2:g})">{bars}</g>'

    defs = []
    shine = ""
    if style.shine:
        defs.append(
            '<linearGradient id="s" x2="0" y2="100%">'
            '<stop offset="0" stop-color="#bbb" stop-opacity=".1"/>'
            '<stop offset="1" stop-opacity=".1"/></linearGradient>'
        )
        shine = f'<rect width="{total_w}" height="{height}" fill="url(#s)"/>'
    if style.radius:
        defs.append(
            f'<clipPath id="r"><rect width="{total_w}" height="{height}" '
            f'rx="{style.radius}" fill="#fff"/></clipPath>'
        )
        group = '<g clip-path="url(#r)">'
    else:
        group = "<g>"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="{height}" role="img" aria-label={quoteattr(title)}>
  <title>{escape(title)}</title>
  {"".join(defs)}
  {group}{"".join(parts)}{shine}</g>
  {icon}{"".join(marks)}
  <g text-anchor="middle" font-family={quoteattr(style.font)} font-size="{style.font_size:g}" text-rendering="geometricPrecision">{"".join(texts)}</g>
</svg>
"""


def render_badge(label: str, value: str, color: str = "", style: str = "flat") -> str:
    """Return the SVG markup for a badge reading ``label | value``.

    ``color`` overrides the value-segment background (shields color name,
    hex, or any SVG color). ``style`` is a badge style name: "flat" (3px
    radius, subtle gradient), "flat-square" (sharp corners, solid fill) or
    "terminal" (the report's look: monospace, square, "//" before the label).
    """
    return render_segments([Segment(label), Segment(value, bg=color)], style)


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
    if style not in _STYLES:
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
