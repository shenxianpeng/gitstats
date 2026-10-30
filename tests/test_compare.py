"""Tests for how one repository compares with the others."""

import pytest

from gitstats import compare

QUARTERS = [["2026-01", "2026-02", "2026-03"], ["2026-04", "2026-05", "2026-06"]]


def _summary(name, commits=100, group="", **extra):
    summary = {
        "name": name,
        "report_path": f"{name}/index.html",
        "commits_last_12mo": commits,
    }
    if group:
        summary["group"] = group
    summary.update(extra)
    return summary


def _people(authors=10, new=3, half=2, commits=100):
    return {
        "from": "2025-07",
        "to": "2026-06",
        "commits": commits,
        "authors": authors,
        "new_authors": new,
        "half_of_commits": half,
    }


def test_measures_of_a_full_summary():
    summary = _summary(
        "a",
        commits=250,
        people_last_12mo=_people(),
        organizations={
            "top": [
                {"organization": "x.com", "commits_last_12mo": 5},
                {"organization": "y.com", "commits_last_12mo": 0},
                {"organization": "z.com", "commits_last_12mo": 1},
            ]
        },
        ai_assisted={
            "by_month": {"2026-01": 2, "2026-05": 3, "2025-12": 50},
            "commits_by_month": {"2026-01": 10, "2026-05": 15, "2025-12": 60},
        },
    )
    assert compare.measures_of(summary, QUARTERS) == {
        # people's commits of the 12 months up to the last one, as the other
        # measures: not commits_last_12mo, the 12 months up to the summary
        "commits": 100.0,
        "authors": 10.0,
        "new_authors": 3.0,
        "half_of_commits": 2.0,
        "organizations": 2.0,
        "ai_share": 0.2,  # 5 of 25, the months outside the quarters left out
    }


def test_measures_of_an_older_summary():
    values = compare.measures_of(_summary("a", active_authors_12mo=4), QUARTERS)
    # contributors from active_authors_12mo; the rest unknown
    assert values == {
        "commits": 100.0,
        "authors": 4.0,
        "new_authors": None,
        "half_of_commits": None,
        "organizations": None,
        "ai_share": None,
    }


def test_measures_without_commits():
    summary = _summary(
        "a",
        commits=0,
        people_last_12mo=_people(authors=0, new=0, half=0, commits=0),
        ai_assisted={"by_month": {}, "commits_by_month": {}},
    )
    values = compare.measures_of(summary, QUARTERS)
    assert values["half_of_commits"] is None  # nobody made half of nothing
    assert values["ai_share"] is None


def test_rank():
    assert compare.rank(5.0, [9.0, 5.0, 5.0, 1.0, None]) == (2, 4)
    assert compare.rank(9.0, [9.0, 5.0]) == (1, 2)
    assert compare.rank(None, [1.0]) is None
    assert compare.rank(1.0, [None]) is None


@pytest.mark.parametrize(
    ("number", "text"),
    [(1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th"), (11, "11th"), (12, "12th"),
     (13, "13th"), (21, "21st"), (22, "22nd"), (101, "101st"), (111, "111th")],
)  # fmt: skip
def test_ordinal(number, text):
    assert compare.ordinal(number) == text


def _rows(values, groups=None):
    summaries = [
        _summary(f"p{n}", commits=value, group=(groups or {}).get(n, ""))
        for n, value in enumerate(values)
    ]
    return compare.comparisons(summaries, QUARTERS)


def test_comparisons_rank_in_group_and_in_all():
    rows = _rows([10, 50, 30, 20, 40, 5], {0: "g", 1: "g", 2: "h"})
    first = rows[0]["ranks"]["commits"]
    assert first == {"group": (2, 2), "all": (5, 6)}
    # no group, no rank in one
    assert rows[3]["ranks"]["commits"]["group"] is None
    assert rows[3]["values"]["commits"] == 20.0


def test_headline_first_and_second():
    summaries = [
        _summary(
            f"p{n}", commits=0, group="g", people_last_12mo=_people(authors=n, commits=100 - n)
        )
        for n in range(6)
    ]
    rows = compare.comparisons(summaries, QUARTERS)
    # p0: the most commits, the fewest contributors; p5 the other way round
    assert compare.headline(rows[0], "Python open source projects") == (
        "p0 had more commits in the last 12 months than any other of the 6 Python open "
        "source projects."
    )
    summaries[1]["people_last_12mo"] = _people(authors=99, commits=99)
    rows = compare.comparisons(summaries, QUARTERS)
    # 2nd for commits too, but commits rise with contributors: no second sentence
    assert compare.headline(rows[1], "Python open source projects") == (
        "p1 had more contributors in the last 12 months than any other of the 6 Python open "
        "source projects."
    )


def test_headline_second_place_and_also_first():
    summaries = [
        _summary("a", commits=10, people_last_12mo=_people(new=50)),
        _summary("b", commits=90, people_last_12mo=_people(new=1)),
        *(_summary(f"c{n}", commits=n, people_last_12mo=_people(new=0)) for n in range(4)),
    ]
    rows = compare.comparisons(summaries, QUARTERS)
    # among all: "a" is 1st for new contributors and 2nd for commits
    assert compare.headline(rows[0], "") == (
        "a had more new contributors in the last 12 months than any other of the 6 repositories."
    )
    # a second place of another kind is named
    for n, summary in enumerate(summaries):
        summary["people_last_12mo"]["half_of_commits"] = [7, 9, 1, 2, 3, 4][n]
    rows = compare.comparisons(summaries, QUARTERS)
    assert compare.headline(rows[0], "").endswith(
        "It is also 2nd for how widely its commits are spread."
    )
    summaries[0]["people_last_12mo"]["half_of_commits"] = 10
    rows = compare.comparisons(summaries, QUARTERS)
    assert compare.headline(rows[0], "").endswith(
        "It also had the most people behind half of its commits."
    )


def test_headline_second_first():
    rows = _rows([100, 90, 1, 2, 3, 4])
    assert compare.headline(rows[1], "") == "p1 is 2nd of the 6 repositories for commits."


def test_headline_middle_and_below():
    rows = _rows([100, 90, 80, 50, 40, 30, 20, 10, 5])
    assert compare.headline(rows[4], "") == (
        "p4 sits in the middle of the 9 repositories; its highest place is 5th, for commits."
    )
    assert compare.headline(rows[7], "") == (
        "p7 ranks below most of the 9 repositories on every measure here; its highest "
        "place is 8th, for commits."
    )


def test_headline_too_few():
    assert compare.headline(_rows([3, 2, 1])[0], "") == ""


def test_show():
    commits, share = compare.MEASURES[0], compare.MEASURES[-1]
    assert compare.show(12345.0, commits) == "12,345"
    assert compare.show(0.4219, share) == "42.2%"
    assert compare.show(0.0001, share) == "&lt;0.1%"
    assert compare.show(0.0, share) == "0.0%"
    assert compare.show(None, commits) == "&ndash;"


def test_strip():
    commits, share = compare.MEASURES[0], compare.MEASURES[-1]
    svg = compare.strip_svg(commits, 100.0, [10.0, None], [1000.0, 0.0])
    assert svg.startswith('<div class="compare-strip"><svg class="strip"')
    assert svg.count('class="strip-all"') == 2
    assert svg.count('class="strip-group"') == 1
    assert svg.count('class="strip-own"') == 1
    assert "<span>0</span><span>1,000</span>" in svg
    assert 'aria-label="Commits: 100 among 3"' in svg
    # counts on a log scale: 100 sits two thirds of the way to 1,000
    assert 'cx="398.1"' in svg
    # shares on a straight one, from 0%
    svg = compare.strip_svg(share, 0.25, [], [0.5])
    assert "<span>0%</span><span>50.0%</span>" in svg
    assert 'cx="300.0"' in svg
    assert compare.strip_svg(commits, None, [1.0], []) == ""
    assert compare.strip_svg(commits, 1.0, [None], []) == ""
    # everything at zero
    assert 'cx="8.0"' in compare.strip_svg(commits, 0.0, [0.0], [])


def test_card_rows():
    rows = _rows([100, 50, 10])
    assert compare.card_rows(rows[1], "all") == [("Commits", 0.5, "2nd / 3")]
    assert compare.card_rows(rows[0], "all")[0][1] == 1.0
    assert compare.card_rows(_rows([1])[0], "all") == []  # alone: no rank to show


def test_card_rows_with_shared_places():
    # a place another holds too says so
    rows = _rows([100, 50, 50])
    assert compare.card_rows(rows[1], "all") == [("Commits", 0.5, "2nd / 3, shared")]
    # a value all of them have is no place: its full bar would say it leads
    assert compare.card_rows(_rows([50, 50, 50])[0], "all") == []


@pytest.mark.parametrize(
    "place, same, words",
    [
        ((1, 5), 1, ("1st of 5", "")),
        ((4, 5), 2, ("4th of 5", ", shared with 1 other")),
        ((2, 7), 3, ("2nd of 7", ", shared with 2 others")),
        ((1, 5), 5, ("Same for all", "5")),
        # one repository alone is first, not "the same for all"
        ((1, 1), 1, ("1st of 1", "")),
    ],
)
def test_rank_words(place, same, words):
    assert compare.rank_words(place, same) == words


def test_a_shared_place_is_not_named():
    # all at 4 contributors: none of them has "the most"
    summaries = [
        _summary(f"p{n}", group="g", people_last_12mo=_people(authors=4, commits=100 - n))
        for n in range(6)
    ]
    rows = compare.comparisons(summaries, QUARTERS)
    assert rows[0]["alone"]["authors"] is False
    assert rows[0]["alone"]["commits"] is True
    assert "contributors" not in compare.headline(rows[0], "g projects")
    # nor is a first place at zero
    rows = _rows([0, 0, 0, 0, 0, 0])
    assert rows[0]["alone"]["commits"] is False
    assert compare.headline(rows[0], "") == ""


def test_a_shared_place_among_all():
    rows = _rows([5, 5, 3, 2, 1])
    assert rows[0]["alone"]["commits"] is False
    assert rows[2]["alone"]["commits"] is True


def test_headline_last_even_on_its_best_measure():
    rows = _rows([100, 90, 80, 70, 60, 50])
    assert compare.headline(rows[5], "") == (
        "p5 had fewer commits in the last 12 months than any other of the 6 repositories."
    )


def _ai(share):
    return {"by_month": {"2026-01": share}, "commits_by_month": {"2026-01": 100}}


def test_ai_share_is_named_only_for_a_first_place():
    # p0: 2nd for commits and first for AI; p1: 1st for commits, 2nd for AI
    summaries = [
        _summary("p0", commits=90, ai_assisted=_ai(40)),
        _summary("p1", commits=100, ai_assisted=_ai(30)),
        *(_summary(f"q{n}", commits=n, ai_assisted=_ai(n)) for n in range(4)),
    ]
    rows = compare.comparisons(summaries, QUARTERS)
    assert compare.headline(rows[0], "") == (
        "p0 had a larger share of commits that name an AI coding assistant than any other "
        "of the 6 repositories. It is also 2nd for commits."
    )
    # 2nd for AI is not named, not even as a second sentence
    assert compare.headline(rows[1], "") == (
        "p1 had more commits in the last 12 months than any other of the 6 repositories."
    )


def test_its_highest_place_counts_the_ai_share():
    summaries = [
        _summary(f"p{n}", commits=100 - 10 * n, ai_assisted=_ai([1, 2, 3, 8, 4, 9, 6][n]))
        for n in range(7)
    ]
    rows = compare.comparisons(summaries, QUARTERS)
    # p3 is 4th for commits and 2nd for AI: its highest place is the 2nd, which
    # a headline does not name for AI, but must not leave out
    assert compare.headline(rows[3], "") == (
        "p3's highest place among the 7 repositories is 2nd, for AI-assisted commits."
    )
    # on equal places, a people measure is named over the AI share
    summaries[3]["ai_assisted"] = _ai(2)
    rows = compare.comparisons(summaries, QUARTERS)
    assert compare.headline(rows[3], "") == (
        "p3 sits in the middle of the 7 repositories; its highest place is 4th, for commits."
    )


def test_its_highest_place_counts_shared_places():
    # p4 shares the most people behind half of the commits: Vue's case
    summaries = [
        _summary(f"p{n}", people_last_12mo=_people(commits=100 - 10 * n, half=[1, 2, 3, 6, 6][n]))
        for n in range(5)
    ]
    rows = compare.comparisons(summaries, QUARTERS)
    assert rows[4]["shared"]["half_of_commits"] == 1
    assert compare.headline(rows[4], "") == (
        "p4's highest place among the 5 repositories is 1st, shared, for how widely its "
        "commits are spread."
    )
    # shared low places: below most on every measure, ties said
    summaries[3]["people_last_12mo"]["half_of_commits"] = 0
    summaries[4]["people_last_12mo"]["half_of_commits"] = 0
    rows = compare.comparisons(summaries, QUARTERS)
    assert compare.headline(rows[3], "") == (
        "p3 ranks below most of the 5 repositories on every measure here; its highest place "
        "is 4th, shared, for how widely its commits are spread."
    )


def test_only_ai_to_name():
    summaries = [_summary(f"p{n}", commits=10, ai_assisted=_ai(n)) for n in range(6)]
    rows = compare.comparisons(summaries, QUARTERS)
    # commits all tie: the AI share is all there is, at any place
    assert compare.headline(rows[2], "") == (
        "p2 sits in the middle of the 6 repositories; its highest place is 4th, for "
        "AI-assisted commits."
    )


def test_complete_ai():
    ai = {
        "commits": 6,
        "by_month": {"2026-08": 1, "2026-09": 2, "2026-10": 3},
        "commits_by_month": {"2026-08": 10, "2026-09": 20, "2026-10": 5},
    }
    assert compare.complete_ai({}) is None
    assert compare.complete_ai({"ai_assisted": "?"}) is None
    # a summary that does not say when it was made: as it is
    assert compare.complete_ai({"ai_assisted": ai}) is ai
    assert compare.complete_ai({"ai_assisted": ai, "generated_at": "soon"}) is ai
    # October, the month it was made in, was not over
    done = compare.complete_ai({"ai_assisted": ai, "generated_at": "2026-10-05T04:00:00+00:00"})
    assert done == {
        "commits": 6,
        "by_month": {"2026-08": 1, "2026-09": 2},
        "commits_by_month": {"2026-08": 10, "2026-09": 20},
    }
    assert compare.complete_ai({"ai_assisted": {}, "generated_at": "2026-10-05"}) == {
        "by_month": {},
        "commits_by_month": {},
    }


def test_the_ai_share_of_a_summary_kept_from_an_earlier_build():
    # made in May 2026: May was not over, and its commits are not counted
    ai = {
        "by_month": {"2026-04": 1, "2026-05": 9},
        "commits_by_month": {"2026-04": 10, "2026-05": 10},
    }
    summary = _summary("a", ai_assisted=ai, generated_at="2026-05-14T04:00:00+00:00")
    assert compare.measures_of(summary, QUARTERS)["ai_share"] == 0.1
