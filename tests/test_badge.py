"""Tests for gitstats.badge."""

import os
import xml.etree.ElementTree as ET

from gitstats.badge import BADGE_FILENAME, create_badge_svg, render_badge


# ── render_badge ─────────────────────────────────────────────────────────


def test_render_badge_is_valid_svg():
    svg = render_badge("gitstats", "1,234 commits")
    root = ET.fromstring(svg)
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert root.get("height") == "20"
    assert root.get("role") == "img"


def test_render_badge_contains_label_and_value():
    svg = render_badge("gitstats", "1,234 commits")
    assert ">gitstats</text>" in svg
    assert ">1,234 commits</text>" in svg
    assert 'aria-label="gitstats: 1,234 commits"' in svg
    assert "<title>gitstats: 1,234 commits</title>" in svg


def test_render_badge_width_grows_with_value():
    short = ET.fromstring(render_badge("gitstats", "9 commits"))
    long = ET.fromstring(render_badge("gitstats", "1,234,567 commits"))
    assert int(long.get("width")) > int(short.get("width"))


def test_render_badge_uses_brand_colors():
    svg = render_badge("gitstats", "50 commits")
    assert "#211e1e" in svg  # label background
    assert "#4a7ab5" in svg  # value background


# ── create_badge_svg ─────────────────────────────────────────────────────


def test_create_badge_svg_writes_file(mock_data_collector, temp_dir):
    badge_path = create_badge_svg(mock_data_collector, temp_dir)

    assert badge_path == os.path.join(temp_dir, BADGE_FILENAME)
    assert os.path.exists(badge_path)

    with open(badge_path, encoding="utf-8") as f:
        svg = f.read()
    ET.fromstring(svg)  # well-formed XML
    assert ">50 commits</text>" in svg
