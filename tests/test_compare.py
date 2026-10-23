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
        "commits": 250.0,
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
        _summary(f"p{n}", commits=100 - n, group="g", people_last_12mo=_people(authors=n))
        for n in range(6)
    ]
    rows = compare.comparisons(summaries, QUARTERS)
    # p0: the most commits, the fewest contributors; p5 the other way round
    assert compare.headline(rows[0], "Python open source projects") == (
        "p0 had more commits in the last 12 months than any other of the 6 Python open "
        "source projects."
    )
    summaries[1]["people_last_12mo"] = _people(authors=99)
    rows = compare.comparisons(summaries, QUARTERS)
    assert compare.headline(rows[1], "Python open source projects") == (
        "p1 had more contributors in the last 12 months than any other of the 6 Python open "
        "source projects. It is also 2nd for commits."
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
        "a had more new contributors in the last 12 months than any other of the 6 "
        "repositories. It is also 2nd for commits."
    )
    summaries[0]["commits_last_12mo"] = 95
    rows = compare.comparisons(summaries, QUARTERS)
    assert compare.headline(rows[0], "").endswith("It also had the most new contributors.")


def test_headline_second_first():
    rows = _rows([100, 90, 1, 2, 3, 4])
    assert compare.headline(rows[1], "") == "p1 is 2nd of the 6 repositories for commits."


def test_headline_middle_and_below():
    rows = _rows([100, 90, 80, 50, 40, 30, 20, 10, 5])
    assert compare.headline(rows[4], "") == (
        "p4 sits in the middle of the 9 repositories; its highest place is 5th, "
        "for commits."
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


def test_a_shared_place_is_not_named():
    # all at 4 contributors: none of them has "the most"
    summaries = [
        _summary(f"p{n}", commits=100 - n, group="g", people_last_12mo=_people(authors=4))
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
