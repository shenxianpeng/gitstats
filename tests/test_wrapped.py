"""Tests for gitstats.wrapped – WrappedCardGenerator and SVG generation."""

import datetime
import os
import re
import xml.etree.ElementTree as ET
from types import SimpleNamespace

import pytest

from gitstats.wrapped import (
    MONTH_NAMES,
    THEMES,
    WrappedCardGenerator,
    _longest_streak,
    _write_within,
)

SVG = "{http://www.w3.org/2000/svg}"


def test_write_within_strips_traversal(tmp_path):
    base = str(tmp_path)
    # A plain name is written directly inside the directory.
    ok = _write_within(base, "card.svg", "<svg/>")
    assert ok == os.path.join(base, "card.svg")
    assert os.path.exists(ok)
    # Any directory components in the name are stripped, so the write stays in base.
    ok2 = _write_within(base, "../../escape.svg", "<svg/>")
    assert ok2 == os.path.join(base, "escape.svg")
    assert not os.path.exists(os.path.join(os.path.dirname(base), "escape.svg"))


def _stamp(year, month, day):
    return int(datetime.datetime(year, month, day, 12).timestamp())


def _make_data(**overrides):
    """A collector with two years of history, 2024 and 2025.

    The all-time numbers differ from each year's, so a card that showed one
    of them under a year would be caught.
    """
    data = SimpleNamespace(
        project_name="test-repo",
        commits_by_year={2024: 30, 2025: 50},
        commits_by_month={"2024-11": 30, "2025-01": 10, "2025-03": 25, "2025-08": 15},
        author_of_year={
            2024: {"Bob": 30},
            2025: {"Alice": 35, "Bob": 10, "dependabot[bot]": 5},
        },
        authors={
            "Alice": {"first_commit_stamp": _stamp(2025, 1, 10)},
            "Bob": {"first_commit_stamp": _stamp(2024, 11, 2)},
            "dependabot[bot]": {"first_commit_stamp": _stamp(2025, 3, 1)},
        },
        lines_added_by_year={2024: 900, 2025: 4000},
        lines_removed_by_year={2024: 100, 2025: 1500},
        tags={"v0.1": {"date": "2024-11-30"}, "v1.0": {"date": "2025-03-20"}},
        active_days={
            "2024-11-02",
            "2024-11-03",
            "2025-01-10",
            "2025-01-11",
            "2025-01-12",
            "2025-03-05",
            "2025-08-20",
        },
        # year -> weekday -> hour -> commits
        activity_by_hour_of_week_by_year={
            2024: {5: {23: 30}},
            2025: {0: {9: 10, 14: 5}, 2: {10: 25}, 4: {20: 10}},
        },
        # all-time: none of these belongs on a card
        total_commits=80,
        total_authors=3,
        total_files=42,
        total_lines_added=4900,
        total_lines_removed=1600,
        longest_streak=99,
        authors_by_commits=["Bob", "Alice", "dependabot[bot]"],
        activity_by_hour_of_day={9: 10, 10: 25, 14: 5, 20: 10, 23: 30},
        activity_by_day_of_week={0: 15, 2: 25, 4: 10, 5: 30},
        activity_by_month_of_year={1: 10, 3: 25, 8: 15, 11: 30},
    )
    for key, value in overrides.items():
        setattr(data, key, value)
    return data


def _card(data=None, year=2025, theme="midnight"):
    generator = WrappedCardGenerator(data or _make_data(), year=year, theme=theme)
    return generator._render_card(generator._collect_stats())


# ── the card's numbers ───────────────────────────────────────────────────


class TestWrappedCardStats:
    def test_init_defaults(self):
        gen = WrappedCardGenerator(_make_data())
        assert gen.year == datetime.datetime.now().year
        assert gen.theme_name == "midnight"
        assert gen.colors is THEMES["midnight"]

    def test_init_custom_year_and_theme(self):
        gen = WrappedCardGenerator(_make_data(), year=2024, theme="sunset")
        assert gen.year == 2024
        assert gen.theme_name == "sunset"
        assert gen.colors is THEMES["sunset"]

    def test_init_fallback_theme(self):
        gen = WrappedCardGenerator(_make_data(), theme="nonexistent")
        assert gen.colors is THEMES["midnight"]

    def test_every_number_is_the_years(self):
        stats = WrappedCardGenerator(_make_data(), year=2025)._collect_stats()
        assert stats == {
            "year": 2025,
            "project_name": "test-repo",
            "commits": 50,
            "active_days": 5,
            "longest_streak": 3,
            "lines_changed": 5500,
            "contributors": 3,
            "new_contributors": 1,  # Alice; the bot that also arrived is not counted
            "releases": 1,
            "top_author": "Alice",
            "top_author_commits": 35,
            "monthly_commits": [10, 0, 25, 0, 0, 0, 0, 15, 0, 0, 0, 0],
            "busiest_month": "March",
            "busiest_weekday": "Wednesday",
            "day_part": {"name": "Early Bird", "start": 6, "end": 12, "share": 0.7},
        }

    def test_another_year_gets_its_own_numbers(self):
        stats = WrappedCardGenerator(_make_data(), year=2024)._collect_stats()
        assert stats["commits"] == 30
        assert stats["active_days"] == 2
        assert stats["longest_streak"] == 2
        assert stats["lines_changed"] == 1000
        assert stats["contributors"] == 1
        assert (stats["top_author"], stats["top_author_commits"]) == ("Bob", 30)
        assert stats["monthly_commits"] == [0] * 10 + [30, 0]
        assert stats["busiest_month"] == "November"
        assert stats["busiest_weekday"] == "Saturday"
        assert stats["day_part"] == {"name": "Evening Coder", "start": 18, "end": 24, "share": 1.0}

    @pytest.mark.parametrize(
        ("years", "year", "message"),
        [
            # before the first commit
            ({2024: 30, 2025: 50}, 2019, "no commits in 2019; the last year with commits is 2025"),
            # after the last one
            ({2024: 30, 2025: 50}, 2026, "no commits in 2026; the last year with commits is 2025"),
            # a quiet year between two active ones
            ({2023: 5, 2025: 50}, 2024, "no commits in 2024; the last year with commits is 2025"),
            # no commits at all
            ({}, 2025, "no commits in 2025"),
        ],
    )
    def test_a_year_without_commits_has_no_card(self, years, year, message, tmp_path):
        """Not a card of zeros, and not the all-time numbers under that year."""
        generator = WrappedCardGenerator(_make_data(commits_by_year=years), year=year)
        with pytest.raises(ValueError, match=f"^{message}$"):
            generator._collect_stats()
        with pytest.raises(ValueError):
            generator.generate(output_path="card.svg", base_dir=str(tmp_path))
        assert not list(tmp_path.iterdir())

    def test_longest_streak(self):
        assert _longest_streak([]) == 0
        assert _longest_streak(["2025-03-05"]) == 1
        # across a month boundary, then a gap, then a shorter run
        days = ["2025-01-30", "2025-01-31", "2025-02-01", "2025-02-03", "2025-02-04"]
        assert _longest_streak(days) == 3

    def test_streak_and_active_days_stop_at_the_year(self):
        days = {"2024-12-30", "2024-12-31", "2025-01-01", "2025-01-02", "2025-01-03"}
        data = _make_data(active_days=days)
        stats_2025 = WrappedCardGenerator(data, year=2025)._collect_stats()
        assert (stats_2025["active_days"], stats_2025["longest_streak"]) == (3, 3)
        stats_2024 = WrappedCardGenerator(data, year=2024)._collect_stats()
        assert (stats_2024["active_days"], stats_2024["longest_streak"]) == (2, 2)

    @pytest.mark.parametrize(
        ("hour", "name"),
        [
            (0, "Night Owl"),
            (5, "Night Owl"),
            (6, "Early Bird"),
            (11, "Early Bird"),
            (12, "Afternoon Coder"),
            (17, "Afternoon Coder"),
            (18, "Evening Coder"),
            (23, "Evening Coder"),
        ],
    )
    def test_day_part_is_named_after_its_hours(self, hour, name):
        data = _make_data(activity_by_hour_of_week_by_year={2025: {1: {hour: 4}}})
        part = WrappedCardGenerator(data, year=2025)._day_part()
        assert part["name"] == name
        assert part["start"] <= hour < part["end"]
        assert part["share"] == 1.0

    def test_day_part_share_and_ties(self):
        # 20 in the morning, 20 in the evening, 10 at night: the earlier one wins
        grid = {0: {8: 20}, 3: {21: 15}, 6: {19: 5, 2: 10}}
        data = _make_data(activity_by_hour_of_week_by_year={2025: grid})
        part = WrappedCardGenerator(data, year=2025)._day_part()
        assert part == {"name": "Early Bird", "start": 6, "end": 12, "share": 0.4}

    def test_busiest_weekday_tie_goes_to_the_earlier_day(self):
        grid = {4: {10: 7}, 1: {10: 7}, 6: {10: 3}}
        data = _make_data(activity_by_hour_of_week_by_year={2025: grid})
        assert WrappedCardGenerator(data, year=2025)._busiest_weekday() == "Tuesday"

    def test_without_the_hours_of_the_year(self):
        """Data collected before the per-year grid existed: the rest still stands."""
        data = _make_data()
        del data.activity_by_hour_of_week_by_year
        stats = WrappedCardGenerator(data, year=2025)._collect_stats()
        assert stats["day_part"] is None
        assert stats["busiest_weekday"] == ""
        assert stats["busiest_month"] == "March"

        card = _card(data)
        ET.fromstring(card)
        assert "CODING PERSONALITY" not in card
        assert "Busiest weekday" not in card
        assert "Busiest month" in card

    def test_top_contributor_is_a_person(self):
        data = _make_data(author_of_year={2025: {"dependabot[bot]": 40, "Alice": 10}})
        stats = WrappedCardGenerator(data, year=2025)._collect_stats()
        assert (stats["top_author"], stats["top_author_commits"]) == ("Alice", 10)

        # unless only bots committed that year
        data = _make_data(author_of_year={2025: {"dependabot[bot]": 50}})
        stats = WrappedCardGenerator(data, year=2025)._collect_stats()
        assert stats["top_author"] == "dependabot[bot]"

    def test_format_number_thousands(self):
        assert WrappedCardGenerator._format_number(1234) == "1,234"
        assert WrappedCardGenerator._format_number(1000000) == "1.0M"
        assert WrappedCardGenerator._format_number(0) == "0"
        assert WrappedCardGenerator._format_number(999) == "999"

    def test_escape_xml(self):
        assert WrappedCardGenerator._escape_xml("<hello>") == "&lt;hello&gt;"
        assert WrappedCardGenerator._escape_xml('a & b "c"') == "a &amp; b &quot;c&quot;"

    def test_clip(self):
        assert WrappedCardGenerator._clip("short", 10) == "short"
        assert WrappedCardGenerator._clip("exactly-10", 10) == "exactly-10"
        assert WrappedCardGenerator._clip("a name too long", 7) == "a name…"


# ── the SVG ──────────────────────────────────────────────────────────────


def _numbers(card):
    """The six numbers on the card as {label: value}."""
    return {
        label: value
        for value, label in re.findall(
            r'font-size="36"[^>]*>([^<]+)</text>\s*<text[^>]*font-size="14"[^>]*>([^<]+)</text>',
            card,
        )
    }


class TestWrappedCardSvg:
    @pytest.mark.parametrize("theme", sorted(THEMES))
    def test_each_theme_renders_valid_xml(self, theme):
        card = _card(theme=theme)
        root = ET.fromstring(card)
        assert root.tag == f"{SVG}svg"
        assert root.get("viewBox") == "0 0 1080 1080"
        assert THEMES[theme]["bg_start"] in card
        assert THEMES[theme]["accent"] in card

    def test_header_and_footer(self):
        card = _card()
        assert card.startswith('<?xml version="1.0"')
        assert ">REPO WRAPPED</text>" in card
        assert ">2025</text>" in card
        assert ">test-repo</text>" in card
        assert "Generated by gitstats · github.com/shenxianpeng/gitstats" in card
        # a repository is not one person, and its year is not all of its history
        assert "YOUR" not in card

    def test_the_six_numbers(self):
        assert _numbers(_card()) == {
            "Commits": "50",
            "Active Days": "5",
            "Longest Streak": "3 days",
            "Lines Changed": "5,500",
            "Contributors": "3",
            "Releases": "1",
        }
        assert _numbers(_card(year=2024))["Commits"] == "30"

    def test_no_all_time_number_is_on_the_card(self):
        card = _card()
        for all_time in ("80", "42", "6,500", "99 days", "Files"):
            assert f">{all_time}</text>" not in card
        # Bob has the most commits ever, but 2025 was Alice's year
        assert ">Bob</tspan>" not in card

    def test_one_day_streak_is_singular(self):
        data = _make_data(active_days={"2025-03-05"})
        assert _numbers(_card(data))["Longest Streak"] == "1 day"

    def test_sixth_number_is_releases_or_newcomers(self):
        # no release in 2025, but Alice arrived
        data = _make_data(tags={"v0.1": {"date": "2024-11-30"}})
        numbers = _numbers(_card(data))
        assert numbers["New Contributors"] == "1"
        assert "Releases" not in numbers

        # neither: the count of releases, which is zero
        data.authors["Alice"]["first_commit_stamp"] = _stamp(2024, 12, 1)
        numbers = _numbers(_card(data))
        assert numbers["Releases"] == "0"
        assert "New Contributors" not in numbers

    def test_personality_and_facts(self):
        card = _card()
        assert ">CODING PERSONALITY</text>" in card
        assert ">Early Bird</text>" in card
        assert ">70% of commits between 06:00 and 12:00</text>" in card
        assert re.search(r"Busiest month: <tspan[^>]*>March</tspan>", card)
        assert re.search(r"Busiest weekday: <tspan[^>]*>Wednesday</tspan>", card)
        assert re.search(r"Top contributor: <tspan[^>]*>Alice</tspan> · 35 commits<", card)
        # the card is text only: an emoji is drawn differently, or not at all,
        # wherever the SVG is rendered
        assert card.isascii() or set(c for c in card if not c.isascii()) <= {"·", "…"}

    def test_names_are_escaped_and_clipped(self):
        data = _make_data(
            project_name="a<b>&c",
            author_of_year={2025: {"Eve <eve@example.com> " + "x" * 60: 50}},
        )
        card = _card(data)
        ET.fromstring(card)
        assert ">a&lt;b&gt;&amp;c</text>" in card
        # 40 characters of the name: 22, then 17 of the x's and the ellipsis
        assert "Eve &lt;eve@example.com&gt; " + "x" * 17 + "…</tspan>" in card

        card = _card(_make_data(project_name="p" * 80))
        assert ">" + "p" * 59 + "…</text>" in card

    def test_monthly_chart_is_the_years(self):
        card = _card()
        for month_num in range(1, 13):
            assert f">{MONTH_NAMES[month_num][:3]}</text>" in card

        bars = re.findall(r'<rect x="(\d+)" y="(\d+)" width="58" height="(\d+)" rx="4"', card)
        # January, March and August of 2025; November is 2024's
        assert [(int(x), int(h)) for x, _, h in bars] == [(60, 36), (224, 90), (634, 54)]
        # every bar stands on the same baseline, with its count above it
        assert {int(y) + int(h) for _, y, h in bars} == {940}
        for count in ("10", "25", "15"):
            assert f'text-anchor="middle">{count}</text>' in card
        # the nine months without commits keep their place
        assert len(re.findall(r'width="58" height="2"', card)) == 9
        assert ">30</text>" not in card

    def test_layout_fills_the_content_column(self):
        root = ET.fromstring(_card())
        group = root.find(f"{SVG}g")
        assert group.get("clip-path") == "url(#card)"
        # the rounded corners belong to the clip, which the accent bar is inside
        assert root.find(f"{SVG}defs/{SVG}clipPath/{SVG}rect").get("rx") == "32"
        assert all(rect.get("rx") != "32" for rect in group.iter(f"{SVG}rect"))

        children = list(group)
        boxes = [i for i, el in enumerate(children) if el.get("rx") == "14"]
        assert len(boxes) == 6
        assert sorted({int(children[i].get("x")) for i in boxes}) == [60, 390, 720]
        for i in boxes:
            box, value, label = children[i], children[i + 1], children[i + 2]
            top = int(box.get("y"))
            # the number and its label sit inside the box, clear of its border
            assert top + 40 <= int(value.get("y")) <= top + 80
            assert int(value.get("y")) < int(label.get("y")) <= top + 100
            assert int(box.get("x")) + int(box.get("width")) <= 1020

        # twelve months from the left edge of the column to the right one
        months = [el for el in children if el.get("width") == "58"]
        assert len(months) == 12
        assert int(months[0].get("x")) == 60
        assert int(months[-1].get("x")) + 58 == 1020


# ── writing the file ─────────────────────────────────────────────────────


class TestWrappedCardFile:
    def test_generate_writes_the_card(self, temp_dir):
        gen = WrappedCardGenerator(_make_data(), year=2025)
        path = gen.generate(output_path=os.path.join(temp_dir, "wrapped-test.svg"))

        assert path == os.path.join(os.path.abspath(temp_dir), "wrapped-test.svg")
        with open(path, encoding="utf-8") as f:
            content = f.read()
        ET.fromstring(content)
        assert ">2025</text>" in content

    def test_generate_writes_into_base_dir(self, tmp_path):
        gen = WrappedCardGenerator(_make_data(), year=2025)
        path = gen.generate(output_path="elsewhere/card.svg", base_dir=str(tmp_path))
        assert path == str(tmp_path / "card.svg")
        assert (tmp_path / "card.svg").exists()

    def test_generate_default_filename(self, temp_dir):
        """Without output_path, file should be named automatically."""
        gen = WrappedCardGenerator(_make_data(), year=2025)
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            path = gen.generate()
            assert path.endswith("gitstats-wrapped-2025.svg")
            assert os.path.exists(path)
        finally:
            os.chdir(original_cwd)
