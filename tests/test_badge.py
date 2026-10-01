"""Tests for gitstats.badge."""

import datetime
import json
import os
import re
import xml.etree.ElementTree as ET

from gitstats import load_config
from gitstats.badge import (
    BADGE_FILENAME,
    BADGES_DIRNAME,
    STYLE_NAMES,
    _age,
    _compact,
    badge_metrics,
    composite_badges,
    create_badges,
    render_badge,
    render_segments,
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


def test_badge_metrics_release_follows_history(mock_data_collector):
    # v2.0 is the newer commit but carries the earlier date (a rebased or
    # imported history); the badge must name the tag the Tags page calls latest
    mock_data_collector.tags = {
        "v1.0": {"order": 1, "date": "2026-05-01", "stamp": 1777593600},
        "v2.0": {"order": 0, "date": "2026-01-01", "stamp": 1767225600},
    }
    assert badge_metrics(mock_data_collector)["release"] == "v2.0 · 2 tags"


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


# ── composite badges ─────────────────────────────────────────────────────


def test_compact():
    assert _compact(1, "author") == "1 author"
    assert _compact(563, "commit") == "563 commits"
    assert _compact(18458, "line") == "18.5k lines"
    assert _compact(2000, "line") == "2k lines"
    assert _compact(999_950, "line") == "1M lines"
    assert _compact(1_250_000, "line") == "1.2M lines"


def test_summary_badge(mock_data_collector):
    summary = composite_badges(mock_data_collector, "gitstats", "", "flat")["summary"]
    assert summary.message == "50 commits · 3 authors · 2k lines"
    svg = render_segments(summary.segments)
    ET.fromstring(svg)
    for text, bg in (("50 commits", "#4a7ab5"), ("3 authors", "#3b6aa3"), ("2k lines", "#2c5485")):
        assert f">{text}</text>" in svg
        assert f'fill="{bg}"' in svg
    assert "gitstats: 50 commits, 3 authors, 2k lines" in svg


def test_summary_badge_one_segment_when_colored_or_light(mock_data_collector):
    for color, style in (("green", "flat"), ("", "light"), ("", "terminal")):
        summary = composite_badges(mock_data_collector, "gitstats", color, style)["summary"]
        assert [s.text for s in summary.segments] == [
            "gitstats",
            "50 commits · 3 authors · 2k lines",
        ]


def test_activity_badge(mock_data_collector):
    activity = composite_badges(mock_data_collector, "gitstats", "", "flat")["activity"]
    assert activity.message == "8 in Apr"  # the last commit's month
    _, spark, value = activity.segments
    # twelve months ending April 2023; only Jan-Apr have commits, peak is March
    assert len(spark.spark) == 12
    assert spark.spark[:8] == (0,) * 8
    assert spark.spark[8:] == (5 / 15, 10 / 15, 1, 8 / 15)
    assert value.text == "8 in Apr"
    svg = render_segments(activity.segments)
    ET.fromstring(svg)
    assert svg.count('fill="#40c463"') == 12 + 1  # the bars, and the icon's middle one
    assert 'fill="#30363d"' in svg
    assert "gitstats: 8 in Apr" in svg


def test_activity_badge_light_style(mock_data_collector):
    activity = composite_badges(mock_data_collector, "gitstats", "", "light")["activity"]
    svg = render_segments(activity.segments, "light")
    assert "#30363d" not in svg
    assert svg.count('fill="#30a14e"') == 12


def test_age():
    assert _age(0) == "today"
    assert _age(1) == "1 day ago"
    assert _age(29) == "29 days ago"
    assert _age(45) == "1 month ago"
    assert _age(364) == "12 months ago"
    assert _age(800) == "2 years ago"


def test_health_badge(mock_data_collector):
    # the mock's last commit is 2023-04-01
    for now, status, dot, color, message in (
        ((2023, 4, 2), "active", "#40c463", "#1a7f37", "last commit 1 day ago"),
        ((2023, 5, 1), "active", "#40c463", "#1a7f37", "last commit 1 month ago"),
        ((2023, 7, 1), "quiet", "#e3a33b", "#9a6700", "last commit 3 months ago"),
        ((2025, 6, 1), "dormant", "#9e9a9a", "#6e6a6a", "last commit 2 years ago"),
    ):
        health = composite_badges(
            mock_data_collector, "gitstats", "orange", "flat", now=datetime.datetime(*now)
        )["health"]
        assert (health.label, health.message, health.color) == (status, message, color)
        svg = render_segments(health.segments)
        ET.fromstring(svg)
        assert f'<circle cx="8.5" cy="10" r="3.5" fill="{dot}"/>' in svg
        assert f'fill="{color}"' in svg  # ignores badge_color
        assert "#fe7d37" not in svg
        assert f">{status}</text>" in svg


def test_health_badge_dot_replaces_terminal_prefix(mock_data_collector):
    health = composite_badges(mock_data_collector, "gitstats", "", "terminal")["health"]
    svg = render_segments(health.segments, "terminal")
    assert "<circle" in svg
    assert ">//</text>" not in svg


# ── create_badges ────────────────────────────────────────────────────────


def test_create_badges_writes_default_and_variants(mock_data_collector, temp_dir):
    badge_path = create_badges(mock_data_collector, temp_dir)

    assert badge_path == os.path.join(temp_dir, BADGE_FILENAME)
    with open(badge_path, encoding="utf-8") as f:
        svg = f.read()
    ET.fromstring(svg)  # well-formed XML
    assert ">50 commits</text>" in svg

    badges_dir = os.path.join(temp_dir, BADGES_DIRNAME)
    metrics = ("commits", "last-commit", "authors", "files", "lines", "release", "active-days")
    for metric in (*metrics, "summary", "activity", "health"):
        assert os.path.exists(os.path.join(badges_dir, f"{metric}.svg"))
        with open(os.path.join(badges_dir, f"{metric}.json"), encoding="utf-8") as f:
            endpoint = json.load(f)
        assert endpoint["schemaVersion"] == 1
        if metric != "health":
            assert endpoint["label"] == "gitstats"
        assert endpoint["message"]
        assert not endpoint["color"].startswith("#")


def test_create_badges_writes_every_style(mock_data_collector, temp_dir, monkeypatch):
    monkeypatch.setitem(load_config(), "badge_style", "light")
    create_badges(mock_data_collector, temp_dir)
    badges_dir = os.path.join(temp_dir, BADGES_DIRNAME)
    names = sorted(n[:-4] for n in os.listdir(badges_dir) if n.endswith(".svg"))
    assert len(names) == 10
    assert STYLE_NAMES == ("flat", "flat-square", "terminal", "for-the-badge", "light")
    for style in STYLE_NAMES:
        assert sorted(n[:-4] for n in os.listdir(os.path.join(badges_dir, style))) == names
    with open(os.path.join(badges_dir, "terminal", "commits.svg"), encoding="utf-8") as f:
        assert "monospace" in f.read()  # each directory has its own style,
    with open(os.path.join(badges_dir, "flat", "summary.svg"), encoding="utf-8") as f:
        assert ">3 authors</text>" in f.read()  # and style-dependent layouts
    with open(os.path.join(badges_dir, "summary.svg"), encoding="utf-8") as f:
        assert ">3 authors</text>" not in f.read()  # while badges/ follows badge_style


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


def test_create_badges_default_can_be_a_composite(mock_data_collector, temp_dir, monkeypatch):
    monkeypatch.setitem(load_config(), "badge_metric", "summary")
    with open(create_badges(mock_data_collector, temp_dir), encoding="utf-8") as f:
        svg = f.read()
    assert ">3 authors</text>" in svg


def test_create_badges_falls_back_on_unknown_config(mock_data_collector, temp_dir, monkeypatch):
    conf = load_config()
    monkeypatch.setitem(conf, "badge_metric", "nope")
    monkeypatch.setitem(conf, "badge_style", "3d")

    badge_path = create_badges(mock_data_collector, temp_dir)
    with open(badge_path, encoding="utf-8") as f:
        svg = f.read()
    assert ">50 commits</text>" in svg  # fell back to commits
    assert "clip-path" in svg  # fell back to flat
