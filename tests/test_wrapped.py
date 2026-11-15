"""Tests for gitstats.wrapped – WrappedCardGenerator and SVG generation."""

import datetime
import json
import os
import re
import xml.etree.ElementTree as ET
from types import SimpleNamespace

import pytest

from gitstats.share_card import SHARE_CARD_CSS
from gitstats.wrapped import (
    COMPARED,
    MONTH_NAMES,
    NUMBERS,
    PAGE,
    SHARE_CARD,
    SHARE_IMAGE,
    THEMES,
    WRAPPED_SCRIPT,
    WrappedCardGenerator,
    _longest_streak,
    _write_within,
    card_data,
    change,
    compared_text,
    day_text,
    numbers_table_html,
    page_body_html,
    period_text,
    remove_wrapped_page,
    share_card_html,
    summary_text,
    write_card_data,
    write_wrapped_page,
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


@pytest.mark.parametrize("name", ["", ".", "..", "cards/"])
def test_write_within_refuses_a_name_that_is_no_file(tmp_path, name):
    with pytest.raises(ValueError, match="Invalid output file name"):
        _write_within(str(tmp_path), name, "<svg/>")
    assert os.listdir(tmp_path) == []


def test_write_within_checks_the_path_it_built(tmp_path, monkeypatch):
    """Should a name ever keep a directory, the path built from it is
    still checked before anything is written."""
    monkeypatch.setattr(os.path, "basename", lambda name: name)
    with pytest.raises(ValueError, match="Refusing to write outside"):
        _write_within(str(tmp_path), "../escape.svg", "<svg/>")
    assert not os.path.exists(os.path.join(os.path.dirname(str(tmp_path)), "escape.svg"))


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


def _card(data=None, year=2025, theme="midnight", today=None):
    generator = WrappedCardGenerator(data or _make_data(), year=year, theme=theme, today=today)
    return generator._render_card(generator._collect_stats())


def _dated_data(**overrides):
    """_make_data() with what a year is compared with the one before by: the
    commits and the changed lines of each day, and the days each author
    committed on. 2026 has begun: twelve commits, on February 3."""
    data = _make_data(
        commits_by_year={2024: 30, 2025: 50, 2026: 12},
        commits_by_month={
            "2024-11": 30,
            "2025-01": 10,
            "2025-03": 25,
            "2025-08": 15,
            "2026-02": 12,
        },
        commits_by_day={
            "2024-11-02": 20,
            "2024-11-03": 10,
            "2025-01-10": 4,
            "2025-01-11": 3,
            "2025-01-12": 3,
            "2025-03-05": 25,
            "2025-08-20": 15,
            "2026-02-03": 12,
        },
        lines_changed_by_day={
            "2024-11-02": 600,
            "2024-11-03": 400,
            "2025-01-10": 500,
            "2025-03-05": 3000,
            "2025-08-20": 2000,
            "2026-02-03": 70,
        },
        lines_added_by_year={2024: 900, 2025: 4000, 2026: 50},
        lines_removed_by_year={2024: 100, 2025: 1500, 2026: 20},
        author_of_year={
            2024: {"Bob": 30},
            2025: {"Alice": 35, "Bob": 10, "dependabot[bot]": 5},
            2026: {"Alice": 12},
        },
        authors={
            "Alice": {
                "first_commit_stamp": _stamp(2025, 1, 10),
                "active_days": {
                    "2025-01-10",
                    "2025-01-11",
                    "2025-01-12",
                    "2025-03-05",
                    "2025-08-20",
                    "2026-02-03",
                },
            },
            "Bob": {
                "first_commit_stamp": _stamp(2024, 11, 2),
                "active_days": {"2024-11-02", "2024-11-03", "2025-03-05"},
            },
            "dependabot[bot]": {
                "first_commit_stamp": _stamp(2025, 3, 1),
                "active_days": {"2025-03-05"},
            },
        },
        active_days={
            "2024-11-02",
            "2024-11-03",
            "2025-01-10",
            "2025-01-11",
            "2025-01-12",
            "2025-03-05",
            "2025-08-20",
            "2026-02-03",
        },
        activity_by_hour_of_week_by_year={
            2024: {5: {23: 30}},
            2025: {0: {9: 10, 14: 5}, 2: {10: 25}, 4: {20: 10}},
            2026: {1: {15: 12}},
        },
    )
    for key, value in overrides.items():
        setattr(data, key, value)
    return data


# The whole of 2024, as the card of 2025 made after it sets its numbers against
YEAR_2024 = {
    "year": 2024,
    "through": "2024-12-31",
    "commits": 30,
    "active_days": 2,
    "longest_streak": 2,
    "lines_changed": 1000,
    "contributors": 1,
    "new_contributors": 1,
    "releases": 1,
    "monthly_commits": [0] * 10 + [30, 0],
}
# 2025 up to March 10, as the card of 2026 made on March 10 does
EARLY_2025 = {
    "year": 2025,
    "through": "2025-03-10",
    "commits": 35,
    "active_days": 4,
    "longest_streak": 3,
    "lines_changed": 3500,
    # Alice, Bob and the bot; of them only Alice arrived, and she is a person
    "contributors": 3,
    "new_contributors": 1,
    # v1.0 was tagged on March 20
    "releases": 0,
    "monthly_commits": [10, 0, 25, 0, 0, 0, 0, 15, 0, 0, 0, 0],
}
MARCH_10 = datetime.date(2026, 3, 10)


# ── the card's numbers ───────────────────────────────────────────────────


class TestWrappedCardStats:
    def test_init_defaults(self):
        gen = WrappedCardGenerator(_make_data())
        assert gen.year == datetime.datetime.now().year
        assert gen.theme_name == "midnight"
        assert gen.colors is THEMES["midnight"]

    def test_init_year_is_todays(self):
        gen = WrappedCardGenerator(_make_data(), today=datetime.date(2030, 3, 1))
        assert (gen.year, gen.today) == (2030, datetime.date(2030, 3, 1))

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
            "through": "2025-12-31",
            "complete": True,
            # this data does not say which days the commits of 2024 were made on
            "previous": None,
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


# ── the year before ──────────────────────────────────────────────────────


class TestTheYearBefore:
    def test_a_year_that_is_over_is_compared_with_the_whole_one_before(self):
        stats = WrappedCardGenerator(_dated_data(), year=2025, today=MARCH_10)._collect_stats()
        assert (stats["through"], stats["complete"]) == ("2025-12-31", True)
        assert stats["previous"] == YEAR_2024

    def test_a_year_under_way_is_compared_with_the_same_days(self):
        """Made on March 10: the year before counts up to its own March 10,
        not the commits of August, nor the release of March 20."""
        stats = WrappedCardGenerator(_dated_data(), today=MARCH_10)._collect_stats()
        assert (stats["year"], stats["through"], stats["complete"]) == (2026, "2026-03-10", False)
        assert stats["previous"] == EARLY_2025

    def test_the_last_day_compared_is_counted(self):
        on_the_day = WrappedCardGenerator(_dated_data(), today=datetime.date(2026, 3, 5))
        assert on_the_day._previous()["commits"] == 35
        the_day_before = WrappedCardGenerator(_dated_data(), today=datetime.date(2026, 3, 4))
        assert the_day_before._previous()["commits"] == 10

    def test_february_29_is_compared_with_february_28(self):
        data = _dated_data(
            commits_by_year={2023: 9, 2024: 4},
            commits_by_day={"2023-02-28": 5, "2023-03-01": 4, "2024-02-10": 4},
            active_days={"2023-02-28", "2023-03-01", "2024-02-10"},
        )
        generator = WrappedCardGenerator(data, today=datetime.date(2024, 2, 29))
        previous = generator._previous()
        assert (previous["through"], previous["commits"]) == ("2023-02-28", 5)

    @pytest.mark.parametrize(
        ("year", "today", "why"),
        [
            (2024, MARCH_10, "the repository began in 2024"),
            (2025, datetime.date(2025, 8, 25), "2024 had no commit before November"),
        ],
    )
    def test_nothing_to_compare_with(self, year, today, why):
        generator = WrappedCardGenerator(_dated_data(), year=year, today=today)
        assert generator._collect_stats()["previous"] is None, why

    def test_data_without_the_days_is_not_compared(self):
        """Collected before the commits of each day were kept: no guess is made
        from the months."""
        data = _dated_data()
        del data.commits_by_day
        assert WrappedCardGenerator(data, year=2025, today=MARCH_10)._previous() is None

    def test_the_rest_of_the_year_before_waits_for_its_numbers(self):
        """Only the commits of each day: the other numbers are none, not an error."""
        data = _make_data(commits_by_day={"2024-11-02": 30}, tags={}, commits_by_month={})
        del data.active_days
        previous = WrappedCardGenerator(data, year=2025, today=MARCH_10)._previous()
        assert previous == {
            **YEAR_2024,
            "active_days": 0,
            "longest_streak": 0,
            "lines_changed": 0,
            "contributors": 0,
            "releases": 0,
            "monthly_commits": [0] * 12,
        }

    @pytest.mark.parametrize(
        ("now", "before", "relative", "moved"),
        [
            (120, 100, True, (1, "+20%")),
            (80, 100, True, (-1, "-20%")),
            (100, 100, True, (0, "same")),
            # a third of a percent is not a change worth a sign
            (1003, 1000, True, (0, "same")),
            (997, 1000, True, (0, "same")),
            (990, 100, True, (1, "+890%")),
            # from ten times on, a factor
            (1000, 100, True, (1, "10x")),
            (2540, 100, True, (1, "25x")),
            (0, 100, True, (-1, "-100%")),
            # no percentage of nothing
            (500, 0, True, None),
            (0, 0, True, None),
            (8, 6, False, (1, "+2")),
            (3, 5, False, (-1, "-2")),
            (4, 4, False, (0, "same")),
            (2, 0, False, (1, "+2")),
            (2500, 1000, False, (1, "+1,500")),
        ],
    )
    def test_change(self, now, before, relative, moved):
        assert change(now, before, relative) == moved

    def test_every_number_compared_is_one_the_card_has(self):
        stats = WrappedCardGenerator(_dated_data(), year=2025, today=MARCH_10)._collect_stats()
        assert set(COMPARED) <= set(stats) & set(stats["previous"])
        assert {key for _, key in NUMBERS} == set(COMPARED)

    def test_day_text(self):
        assert day_text("2025-12-05") == "December 5"
        assert day_text("2024-02-29") == "February 29"


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

    def test_the_months_to_come_are_not_drawn(self):
        """A card of the current year, made in mid-August: September to
        December have not happened, so they have no bar and no baseline."""
        generator = WrappedCardGenerator(_make_data(), year=2025, today=datetime.date(2025, 8, 15))
        card = generator._render_card(generator._collect_stats())
        ET.fromstring(card)
        assert ">MONTHLY COMMITS SO FAR</text>" in card
        bars = re.findall(r'<rect x="(\d+)" y="\d+" width="58" height="(\d+)" rx="4"', card)
        assert [int(x) for x, _ in bars] == [60, 224, 634]  # January, March, August
        # February and April to July had no commits: a baseline each
        assert len(re.findall(r'width="58" height="2"', card)) == 5
        # the months to come: their names, faint, and nothing more
        for month in ("Sep", "Oct", "Nov", "Dec"):
            assert f'fill-opacity="0.5" text-anchor="middle">{month}</text>' in card
        assert 'fill-opacity="0.5" text-anchor="middle">Aug</text>' not in card
        # a past year is whole
        generator = WrappedCardGenerator(_make_data(), year=2025, today=datetime.date(2026, 1, 2))
        card = generator._render_card(generator._collect_stats())
        assert ">MONTHLY COMMITS</text>" in card
        assert 'fill-opacity="0.5" text-anchor' not in card

    def test_bars_are_scaled_to_the_months_drawn(self):
        # November's 100 commits (the clock of a test: today is in October)
        # would make October's 50 a short bar
        generator = WrappedCardGenerator(_make_data(), year=2025, today=datetime.date(2025, 10, 1))
        chart = generator._render_mini_bar_chart([0] * 9 + [50, 100, 0])
        assert 'width="58" height="90" rx="4"' in chart  # October is the tallest drawn
        assert generator._render_mini_bar_chart([0] * 10 + [100, 0]) == ""

    def test_facts_and_chart_wait_for_their_numbers(self):
        """Without the year's authors, months and hours: no top contributor,
        busiest month or weekday, and no bars; the card still stands."""
        data = _make_data(author_of_year={2025: {}}, commits_by_month={})
        del data.activity_by_hour_of_week_by_year
        generator = WrappedCardGenerator(data, year=2025)
        stats = generator._collect_stats()
        assert (stats["top_author"], stats["busiest_month"], stats["busiest_weekday"]) == (
            "",
            "",
            "",
        )
        assert stats["monthly_commits"] == [0] * 12
        assert generator._render_facts(stats) == ""
        assert generator._render_mini_bar_chart(stats["monthly_commits"]) == ""
        card = generator._render_card(stats)
        ET.fromstring(card)
        assert "Top contributor" not in card
        assert "MONTHLY COMMITS" not in card
        assert 'width="58"' not in card

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


def _moved(card):
    """How each of the six numbers moved, as {label: (text, colour)}."""
    return {
        label: (text, colour)
        for label, colour, text in re.findall(
            r'font-size="14" font-weight="500"[^>]*>([^<]+)</text>\s*<text[^>]*font-size="14" '
            r'font-weight="600" fill="([^"]+)" text-anchor="end">([^<]+)</text>',
            card,
        )
    }


class TestWrappedCardComparison:
    def test_each_number_says_how_it_moved(self):
        card = _card(_dated_data(), today=MARCH_10)
        ET.fromstring(card)
        up, down = THEMES["midnight"]["up"], THEMES["midnight"]["down"]
        assert _moved(card) == {
            "Commits": ("+67%", up),
            "Active Days": ("+3", up),
            "Longest Streak": ("+1", up),
            "Lines Changed": ("+450%", up),
            "Contributors": ("+2", up),
            # one release in each year
            "Releases": ("same", THEMES["midnight"]["stat_label"]),
        }
        # the numbers themselves are where they were
        assert _numbers(card)["Commits"] == "50"
        assert ">Compared with 2024</text>" in card

        # 2026, by March 10: less than the same days of 2025 in every way
        card = _card(_dated_data(), year=2026, today=MARCH_10)
        assert _moved(card) == {
            "Commits": ("-66%", down),
            "Active Days": ("-3", down),
            "Longest Streak": ("-2", down),
            "Lines Changed": ("-98%", down),
            "Contributors": ("-2", down),
            "Releases": ("same", THEMES["midnight"]["stat_label"]),
        }
        assert ">Compared with the same days of 2025: January 1 to March 10</text>" in card

    @pytest.mark.parametrize("theme", sorted(THEMES))
    def test_up_and_down_have_their_colours_in_each_theme(self, theme):
        colors = THEMES[theme]
        assert colors["up"] != colors["down"]
        card = _card(_dated_data(), theme=theme, today=MARCH_10)
        ET.fromstring(card)
        assert f'fill="{colors["up"]}" text-anchor="end">+67%</text>' in card

    def test_a_number_without_a_year_before_says_nothing(self):
        """No lines were counted in 2024: there is no percentage to give."""
        data = _dated_data(lines_changed_by_day={"2025-03-05": 5500})
        moved = _moved(_card(data, today=MARCH_10))
        assert "Lines Changed" not in moved
        assert moved["Commits"] == ("+67%", THEMES["midnight"]["up"])

    def test_a_card_with_nothing_to_compare_is_the_card_it_was(self):
        card = _card(_dated_data(), year=2024, today=MARCH_10)
        assert _moved(card) == {}
        assert "Compared with" not in card
        assert len(re.findall(r'width="58" height="\d+" rx="4"', card)) == 1  # November

    def test_the_year_before_stands_beside_each_month(self):
        card = _card(_dated_data(), today=MARCH_10)
        ET.fromstring(card)
        # this year's months, narrower, where they were
        bars = re.findall(r'<rect x="(\d+)" y="(\d+)" width="40" height="(\d+)" rx="4"', card)
        assert [(int(x), int(h)) for x, _, h in bars] == [(60, 30), (224, 75), (634, 45)]
        # November of 2024, the tallest of both years, to the right of this year's
        ghosts = re.findall(r'<rect x="(\d+)" y="(\d+)" width="14" height="(\d+)" rx="3"', card)
        assert [(int(x), int(y), int(h)) for x, y, h in ghosts] == [
            (966, 816, 10),  # the legend's
            (60 + 10 * 82 + 44, 850, 90),
        ]
        assert 'text-anchor="end">2024</text>' in card
        # the count stays over its own bar, the month's name under the two
        assert '<text x="80" y="904" font-size="11"' in card
        assert f'<text x="89" y="958" font-size="11" fill="{THEMES["midnight"]["footer"]}"' in card
        assert 'width="58"' not in card
        # the months without commits keep their place, as wide as the bars
        assert len(re.findall(r'width="40" height="2"', card)) == 9

    def test_the_month_under_way_has_no_year_before_beside_it(self):
        """Made on March 10 of 2026: January and February of 2025 stand beside
        this year's, March of 2025 does not, whole as it is."""
        card = _card(_dated_data(), year=2026, today=MARCH_10)
        ET.fromstring(card)
        ghosts = re.findall(r'<rect x="(\d+)" y="\d+" width="14" height="(\d+)" rx="3"', card)
        # the legend's, and January of 2025: 10 commits to this February's 12
        assert [(int(x), int(h)) for x, h in ghosts] == [(966, 10), (104, 75)]
        assert 'width="40" height="90" rx="4"' in card
        assert 'text-anchor="end">2025</text>' in card

    def test_january_has_no_month_before_it_to_compare(self):
        data = _dated_data(
            commits_by_year={2025: 50, 2026: 3},
            commits_by_month={"2025-01": 10, "2025-03": 40, "2026-01": 3},
            commits_by_day={"2025-01-10": 10, "2025-03-05": 40, "2026-01-05": 3},
        )
        card = _card(data, year=2026, today=datetime.date(2026, 1, 20))
        # compared, but with no month of the year before to draw
        assert ">Compared with the same days of 2025: January 1 to January 20</text>" in card
        assert 'width="14"' not in card
        assert 'width="58" height="90" rx="4"' in card

    def test_generate_keeps_the_card_and_its_numbers(self, tmp_path):
        generator = WrappedCardGenerator(_dated_data(), year=2025, today=MARCH_10)
        assert (generator.svg, generator.stats) == (None, None)
        path = generator.generate(output_path="card.svg", base_dir=str(tmp_path))
        with open(path, encoding="utf-8") as f:
            assert f.read() == generator.svg
        assert generator.stats["previous"] == YEAR_2024


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


# ── next to a report: the data, the page and its share card ──────────────


def _stats(year=2025, today=MARCH_10, data=None):
    return WrappedCardGenerator(data or _dated_data(), year=year, today=today)._collect_stats()


def _report_card(year=2025, today=MARCH_10, data=None):
    """What the report shows a card by, as main._write_wrapped_card() returns it."""
    generator = WrappedCardGenerator(data or _dated_data(), year=year, today=today)
    stats = generator._collect_stats()
    return {
        "year": year,
        "theme": "midnight",
        "file": f"wrapped-{year}.svg",
        "data": f"wrapped-{year}.json",
        "stats": stats,
        "svg": generator._render_card(stats),
    }


class TestWrappedCardData:
    def test_the_numbers_as_data(self):
        stats = _stats()
        data = card_data(stats, "sunset", "wrapped-2025.svg")
        assert list(data)[:5] == ["schema_version", "generated_by", "generated_at", "card", "theme"]
        assert data["schema_version"] == 1
        assert data["generated_by"].startswith("gitstats ")
        assert datetime.datetime.fromisoformat(data["generated_at"]).tzinfo is not None
        assert (data["card"], data["theme"]) == ("wrapped-2025.svg", "sunset")
        # and every number of the card, the year before with them
        assert {key: data[key] for key in stats} == stats
        assert data["previous"] == YEAR_2024

    def test_written_next_to_the_card(self, tmp_path):
        name = write_card_data(str(tmp_path), _stats(), "clean", "wrapped-2025.svg")
        assert name == "wrapped-2025.json"
        text = (tmp_path / name).read_text(encoding="utf-8")
        assert text.endswith("}\n")
        data = json.loads(text)
        assert (data["year"], data["commits"], data["theme"]) == (2025, 50, "clean")
        assert data["previous"]["commits"] == 30

    def test_a_name_from_another_alphabet_stays_readable(self, tmp_path):
        stats = _stats(data=_dated_data(project_name="统计"))
        name = write_card_data(str(tmp_path), stats, "midnight", "wrapped-2025.svg")
        assert '"project_name": "统计"' in (tmp_path / name).read_text(encoding="utf-8")


class TestWrappedTexts:
    def test_a_year_that_is_over(self):
        stats = _stats()
        assert period_text(stats) == "in 2025"
        assert compared_text(stats) == ", compared with 2024"
        assert summary_text(stats) == (
            "test-repo in 2025: 50 commits (+67% on 2024), 3 contributors, 5 active days."
        )

    def test_a_year_under_way(self):
        stats = _stats(year=2026)
        assert period_text(stats) == "from January 1 to March 10, 2026"
        assert compared_text(stats) == ", compared with the same days of 2025"
        assert summary_text(stats) == (
            "test-repo in 2026 so far: 12 commits (-66% on the same days of 2025), "
            "1 contributor, 1 active day."
        )

    def test_with_nothing_to_compare(self):
        stats = _stats(year=2024)
        assert compared_text(stats) == ""
        assert summary_text(stats) == "test-repo in 2024: 30 commits, 1 contributor, 2 active days."

    def test_commits_that_did_not_move_are_not_given_a_change(self):
        data = _dated_data(commits_by_day={"2024-11-02": 50})
        assert summary_text(_stats(data=data)) == (
            "test-repo in 2025: 50 commits, 3 contributors, 5 active days."
        )


class TestWrappedNumbersTable:
    def test_beside_the_year_before(self):
        table = numbers_table_html(_stats())
        assert table.startswith('<div class="table-scroll"><table class="wrapped-numbers">')
        assert (
            '<tr><th></th><th class="num">2025</th><th class="num">2024</th>'
            '<th class="num">Change</th></tr>'
        ) in table
        assert (
            '<tr><td>Commits</td><td class="num">50</td><td class="num">30</td>'
            '<td class="num"><span class="wrapped-up">+67%</span></td></tr>'
        ) in table
        assert (
            '<tr><td>Lines changed</td><td class="num">5,500</td><td class="num">1,000</td>'
            '<td class="num"><span class="wrapped-up">+450%</span></td></tr>'
        ) in table
        assert '<td class="num"><span class="wrapped-same">same</span></td></tr>' in table
        assert table.count("<tr>") == 1 + len(NUMBERS)

    def test_a_number_that_went_down(self):
        table = numbers_table_html(_stats(year=2026))
        assert (
            '<tr><td>Contributors</td><td class="num">1</td><td class="num">3</td>'
            '<td class="num"><span class="wrapped-down">-2</span></td></tr>'
        ) in table

    def test_alone(self):
        table = numbers_table_html(_stats(year=2024))
        assert '<tr><th></th><th class="num">2024</th></tr>' in table
        assert '<tr><td>Commits</td><td class="num">30</td></tr>' in table
        assert "Change" not in table
        assert "wrapped-" not in table.replace("wrapped-numbers", "")

    def test_no_percentage_of_nothing(self):
        """No lines were counted in 2024: the cell is there, and empty."""
        data = _dated_data(lines_changed_by_day={"2025-03-05": 5500})
        table = numbers_table_html(_stats(data=data))
        assert (
            '<tr><td>Lines changed</td><td class="num">5,500</td><td class="num">0</td>'
            '<td class="num"></td></tr>'
        ) in table


class TestWrappedShareCard:
    def test_the_year_on_a_share_card(self):
        card = share_card_html(_stats(data=_dated_data(project_name="a<b>&c")))
        assert card.startswith("<!DOCTYPE html>")
        assert "<title>a&lt;b&gt;&amp;c: Repo Wrapped 2025</title>" in card
        assert '<div class="brand">// Repo Wrapped 2025</div><h1>a&lt;b&gt;&amp;c</h1>' in card
        assert '<p class="sub">In 2025, compared with 2024</p>' in card
        assert (
            '<div><dt>Commits</dt><dd>50<span class="wrapped-up">+67%</span></dd></div>'
            '<div><dt>Contributors</dt><dd>3<span class="wrapped-up">+2</span></dd></div>'
            '<div><dt>Active days</dt><dd>5<span class="wrapped-up">+3</span></dd></div>'
            '<div><dt>Lines changed</dt><dd>5,500<span class="wrapped-up">+450%</span></dd></div>'
        ) in card
        # twelve months, the tallest of them March
        assert card.count("<i style=") == 12
        assert '<i style="height:40.0%"></i><i style="height:0.0%"></i>' in card
        assert '<i style="height:100.0%"></i>' in card
        assert "<span>Jan</span><span>commits per month</span><span>Dec</span>" in card
        # the colours of a number that moved are the card's own
        assert ".tiles dd .wrapped-up{" in SHARE_CARD_CSS
        assert ".tiles dd .wrapped-down{" in SHARE_CARD_CSS

    def test_the_months_to_come_are_not_on_it(self):
        card = share_card_html(_stats(year=2026))
        assert (
            '<p class="sub">From January 1 to March 10, 2026, compared with the same days of '
            "2025</p>"
        ) in card
        assert '<dd>12<span class="wrapped-down">-66%</span></dd>' in card
        # January, February and March, which has begun
        assert card.count("<i style=") == 3
        assert "<span>Jan</span><span>commits per month</span><span>Mar</span>" in card

    def test_a_year_without_its_months(self):
        data = _dated_data(commits_by_month={})
        card = share_card_html(_stats(year=2024, data=data))
        assert '<p class="sub">In 2024</p>' in card
        assert card.count('<i style="height:0.0%"></i>') == 12
        assert "wrapped-up" not in card.split("</style>", 1)[1]


def _page_data(body):
    text = re.search(r'<script type="application/json" id="wrapped-data">(.*?)</script>', body)
    return json.loads(text.group(1))


class TestWrappedPage:
    def test_the_card_its_numbers_and_what_to_share(self):
        card = _report_card()
        body = page_body_html(card)
        assert body.startswith("<h1>Repo Wrapped 2025</h1>")
        assert '<p class="section-note">test-repo in 2025, compared with 2024.</p>' in body
        assert (
            '<a class="wrapped-card" href="wrapped-2025.svg"><img src="wrapped-2025.svg" '
            'width="1080" height="1080" alt="Repo Wrapped card for test-repo in 2025"></a>'
        ) in body
        assert numbers_table_html(card["stats"]) in body
        assert '<button type="button" id="wrapped-png">Download PNG</button>' in body
        assert '<a href="wrapped-2025.svg" download>Download SVG</a>' in body
        assert '<a href="wrapped-2025.json">Data</a>' in body
        text = summary_text(card["stats"]) + " #RepoWrapped"
        assert f'<pre class="badge-code" id="wrapped-text">{text}</pre>' in body
        assert '<a href="badges.html#repo_wrapped">Show it in a README &rarr;</a>' in body
        for name in ("wrapped-x", "wrapped-bluesky", "wrapped-copy"):
            assert f'id="{name}"' in body
        assert body.endswith(WRAPPED_SCRIPT)
        assert _page_data(body) == {
            "svg": card["svg"],
            "png": "wrapped-2025.png",
            "size": 1080,
            "text": text,
            "url": "",
        }

    def test_the_line_to_post_ends_with_the_address_when_it_is_known(self):
        body = page_body_html(_report_card(), "https://example.org/r/wrapped.html")
        assert "#RepoWrapped https://example.org/r/wrapped.html</pre>" in body
        assert _page_data(body)["url"] == "https://example.org/r/wrapped.html"

    def test_a_year_under_way(self):
        body = page_body_html(_report_card(year=2026))
        assert (
            '<p class="section-note">test-repo from January 1 to March 10, 2026, compared '
            "with the same days of 2025.</p>"
        ) in body

    def test_names_are_escaped(self):
        card = _report_card(data=_dated_data(project_name='a<b>&"c'))
        card["file"] = 'card"<.svg'
        body = page_body_html(card)
        assert 'href="card&quot;&lt;.svg"' in body
        assert 'alt="Repo Wrapped card for a&lt;b&gt;&amp;&quot;c in 2025"' in body
        assert "a&lt;b&gt;&amp;&quot;c in 2025: 50 commits" in body
        # the card closes its tags: none of them may end the script that carries it
        data = body[body.index('id="wrapped-data">') :]
        assert "</svg>" not in data[: data.index("</script>")]
        assert _page_data(body)["svg"] == card["svg"]
        assert _page_data(body)["png"] == 'card"<.png'

    def test_the_script_draws_the_card_it_carries(self):
        """A page opened from a file cannot read the card next to it: the PNG
        is drawn from the SVG in the page, at the card's own size."""
        assert "new Blob([data.svg], {type: 'image/svg+xml'})" in WRAPPED_SCRIPT
        assert "canvas.width = canvas.height = data.size;" in WRAPPED_SCRIPT
        assert "link.download = data.png;" in WRAPPED_SCRIPT
        # the address is the one given, or the page's own when it is served
        assert "data.url || (served ? window.location.href.split(/[?#]/)[0] : '')" in (
            WRAPPED_SCRIPT
        )


class _Report:
    """Stands in for the HTMLReportCreator that wrote the other pages."""

    site_url = ""

    def __init__(self):
        self.header = None

    def print_header(self, file, page, image="", description=None):
        self.header = (page, image, description)
        file.write("<head>")

    def print_nav(self, file, current=None):
        file.write(f"<nav {current}>")

    def print_footer(self, file):
        file.write("<footer>")


class TestWrappedPageFiles:
    def test_the_page_and_its_share_card_are_written(self, tmp_path):
        report, card = _Report(), _report_card()
        write_wrapped_page(report, str(tmp_path), card)

        page = (tmp_path / PAGE).read_text(encoding="utf-8")
        assert page == (f"<head><nav {PAGE}>" + page_body_html(card) + "<footer></body></html>")
        # a link to the page shows its own card, and says the year in a sentence
        assert report.header == (PAGE, SHARE_IMAGE, summary_text(card["stats"]))
        assert (SHARE_IMAGE, SHARE_CARD) == ("wrapped-card.png", "wrapped-card.html")
        assert (tmp_path / SHARE_CARD).read_text(encoding="utf-8") == share_card_html(card["stats"])

    def test_the_page_knows_its_address_from_the_reports(self, tmp_path):
        report = _Report()
        report.site_url = "https://example.org/r/"
        write_wrapped_page(report, str(tmp_path), _report_card())
        page = (tmp_path / PAGE).read_text(encoding="utf-8")
        assert "#RepoWrapped https://example.org/r/wrapped.html</pre>" in page

    def test_an_earlier_page_is_removed(self, tmp_path):
        write_wrapped_page(_Report(), str(tmp_path), _report_card())
        (tmp_path / "index.html").write_text("report", encoding="utf-8")
        remove_wrapped_page(str(tmp_path))
        assert sorted(os.listdir(tmp_path)) == ["index.html"]
        # and nothing to remove is not an error
        remove_wrapped_page(str(tmp_path))
        assert sorted(os.listdir(tmp_path)) == ["index.html"]
