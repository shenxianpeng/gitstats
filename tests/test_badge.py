"""Tests for gitstats.badge."""

import json
import os
import re
import xml.etree.ElementTree as ET

from gitstats import load_config
from gitstats.badge import (
    BADGE_FILENAME,
    BADGES_DIRNAME,
    badge_metrics,
    create_badges,
    render_badge,
    resolve_color,
)

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


def test_render_badge_escapes_xml_special_characters():
    svg = render_badge("R&D <core>", '5 "commits"')
    root = ET.fromstring(svg)  # would raise on unescaped & or <
    texts = {elem.text for elem in root.iter() if elem.text}
    assert "R&D <core>" in texts
    assert '5 "commits"' in texts
    assert root.get("aria-label") == 'R&D <core>: 5 "commits"'


def test_render_badge_width_grows_with_value():
    short = ET.fromstring(render_badge("gitstats", "9 commits"))
    long = ET.fromstring(render_badge("gitstats", "1,234,567 commits"))
    assert int(long.get("width")) > int(short.get("width"))


def test_render_badge_uses_brand_colors():
    svg = render_badge("gitstats", "50 commits")
    assert "#211e1e" in svg  # label background
    assert "#4a7ab5" in svg  # value background


def test_render_badge_color_override():
    svg = render_badge("gitstats", "50 commits", color="orange")
    assert "#fe7d37" in svg
    assert "#4a7ab5" not in svg
    svg = render_badge("gitstats", "50 commits", color="#123456")
    assert "#123456" in svg


def test_render_badge_flat_square_style():
    svg = render_badge("gitstats", "50 commits", style="flat-square")
    assert "clip-path" not in svg
    assert 'rx="3"' not in svg
    assert "url(#s)" not in svg
    ET.fromstring(svg)  # still well-formed
    flat = render_badge("gitstats", "50 commits", style="flat")
    assert "clip-path" in flat
    assert "url(#s)" in flat


def test_render_badge_terminal_style():
    svg = render_badge("gitstats", "50 commits", style="terminal")
    ET.fromstring(svg)
    assert 'height="22"' in svg
    assert "monospace" in svg
    assert ">//</text>" in svg
    assert ">gitstats</text>" in svg
    assert re.search(r'fill="#211e1e" textLength="[\d.]+">50 commits<', svg)  # dark on light
    assert 'stroke="#211e1e"' in svg  # outlined value segment
    assert "clip-path" not in svg
    assert "url(#s)" not in svg
    assert 'fill-opacity=".3"' not in svg  # no text shadow
    assert "gitstats: 50 commits" in svg


def test_render_badge_for_the_badge_style():
    svg = render_badge("gitstats", "50 commits", style="for-the-badge")
    ET.fromstring(svg)
    assert 'height="28"' in svg
    assert 'font-weight="bold"' in svg
    assert ">GITSTATS</text>" in svg
    assert ">50 COMMITS</text>" in svg
    assert 'aria-label="gitstats: 50 commits"' in svg  # read as written
    assert "clip-path" not in svg
    flat = render_badge("gitstats", "50 commits")
    assert int(re.search(r'width="(\d+)"', svg)[1]) > int(re.search(r'width="(\d+)"', flat)[1])


def test_render_badge_light_style():
    svg = render_badge("gitstats", "50 commits", style="light")
    ET.fromstring(svg)
    assert 'fill="#fff"/>' in svg  # white label
    assert re.search(r'fill="#211e1e" textLength="[\d.]+">gitstats<', svg)
    assert 'fill="#eef3fa"' in svg
    assert re.search(r'fill="#2c5485" textLength="[\d.]+">50 commits<', svg)
    assert 'stroke="#cfcecd"' in svg
    assert "url(#s)" not in svg
    assert 'fill-opacity=".3"' not in svg


def test_render_badge_terminal_custom_color():
    svg = render_badge("gitstats", "50 commits", color="orange", style="terminal")
    assert 'fill="#fe7d37"' in svg
    assert re.search(r'fill="#fff" textLength="[\d.]+">50 commits<', svg)
    assert "stroke=" not in svg


# ── resolve_color ────────────────────────────────────────────────────────


def test_resolve_color_shields_names_and_passthrough():
    assert resolve_color("green") == "#97ca00"
    assert resolve_color("BrightGreen") == "#4c1"
    assert resolve_color("#30a14e") == "#30a14e"
    assert resolve_color("rebeccapurple") == "rebeccapurple"


# ── badge_metrics ────────────────────────────────────────────────────────


def test_badge_metrics(mock_data_collector):
    metrics = badge_metrics(mock_data_collector)
    assert metrics["commits"] == "50 commits"
    assert metrics["last-commit"] == "Apr 2023"
    assert metrics["authors"] == "3 authors"
    assert metrics["files"] == "25 files"
    assert metrics["lines"] == "2,000 lines"
    assert metrics["release"] == "v1.1.0 · 2 tags"
    assert metrics["active-days"] == "4 active days"


def test_badge_metrics_release(mock_data_collector):
    tags = mock_data_collector.tags
    tags["v0.9.0"] = {"stamp": 1600000000}  # newest by name, oldest by date
    assert badge_metrics(mock_data_collector)["release"] == "v1.1.0 · 3 tags"
    mock_data_collector.tags = {"v1.0.0": tags["v1.0.0"]}
    assert badge_metrics(mock_data_collector)["release"] == "v1.0.0"
    mock_data_collector.tags = {}
    assert badge_metrics(mock_data_collector)["release"] == "no tags"


def test_badge_metrics_singular(mock_data_collector):
    mock_data_collector.get_total_commits.return_value = 1
    metrics = badge_metrics(mock_data_collector)
    assert metrics["commits"] == "1 commit"


# ── create_badges ────────────────────────────────────────────────────────


def test_create_badges_writes_default_and_variants(mock_data_collector, temp_dir):
    badge_path = create_badges(mock_data_collector, temp_dir)

    assert badge_path == os.path.join(temp_dir, BADGE_FILENAME)
    with open(badge_path, encoding="utf-8") as f:
        svg = f.read()
    ET.fromstring(svg)  # well-formed XML
    assert ">50 commits</text>" in svg

    badges_dir = os.path.join(temp_dir, BADGES_DIRNAME)
    for metric in ("commits", "last-commit", "authors", "files", "lines", "release", "active-days"):
        assert os.path.exists(os.path.join(badges_dir, f"{metric}.svg"))
        with open(os.path.join(badges_dir, f"{metric}.json"), encoding="utf-8") as f:
            endpoint = json.load(f)
        assert endpoint["schemaVersion"] == 1
        assert endpoint["label"] == "gitstats"
        assert endpoint["message"]
        assert not endpoint["color"].startswith("#")


def test_create_badges_honors_config(mock_data_collector, temp_dir, monkeypatch):
    conf = load_config()
    monkeypatch.setitem(conf, "badge_metric", "last-commit")
    monkeypatch.setitem(conf, "badge_label", "my project")
    monkeypatch.setitem(conf, "badge_color", "green")
    monkeypatch.setitem(conf, "badge_style", "flat-square")

    badge_path = create_badges(mock_data_collector, temp_dir)
    with open(badge_path, encoding="utf-8") as f:
        svg = f.read()
    assert ">Apr 2023</text>" in svg
    assert ">my project</text>" in svg
    assert "#97ca00" in svg
    assert "clip-path" not in svg

    with open(os.path.join(temp_dir, BADGES_DIRNAME, "commits.json"), encoding="utf-8") as f:
        endpoint = json.load(f)
    assert endpoint["label"] == "my project"
    assert endpoint["color"] == "97ca00"


def test_create_badges_falls_back_on_unknown_config(mock_data_collector, temp_dir, monkeypatch):
    conf = load_config()
    monkeypatch.setitem(conf, "badge_metric", "nope")
    monkeypatch.setitem(conf, "badge_style", "3d")

    badge_path = create_badges(mock_data_collector, temp_dir)
    with open(badge_path, encoding="utf-8") as f:
        svg = f.read()
    assert ">50 commits</text>" in svg  # fell back to commits
    assert "clip-path" in svg  # fell back to flat
