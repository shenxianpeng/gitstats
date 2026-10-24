"""Tests for what stands out about a repository next to the others."""

import pytest

from gitstats import insights

MONTHS = [f"2025-{m:02d}" for m in range(10, 13)] + [f"2026-{m:02d}" for m in range(1, 10)]


def _ai(before, after, commits=100):
    """An ai_assisted block: ``before`` share in the first three months,
    ``after`` in the last three, ``commits`` a month."""
    by_month = {}
    for index, month in enumerate(MONTHS):
        share = before if index < 3 else after if index >= 9 else 0
        by_month[month] = round(share * commits)
    return {"by_month": by_month, "commits_by_month": dict.fromkeys(MONTHS, commits)}


def _summary(n, **extra):
    """A summary of the twelve-year-old project number ``n``, every measure
    a little larger than the last project's."""
    summary = {
        "name": f"p{n}",
        "report_path": f"p{n}/index.html",
        "last_commit": "2026-09-30 12:00:00",
        "age_days": 4380,
        "commits_last_12mo": 1000,
        "ai_assisted": _ai(0.0, 0.01 * n),
        "humans": {
            "commits": 9000,
            "commits_by_year": {str(y): 1000 for y in range(2015, 2026)} | {"2026": 500},
            "active_days": 2000 + 100 * n,
        },
        "people_last_12mo": {"commits": 500 + 30 * n},
        "source_lines": {"added": 100_000, "current": 30_000 + 2000 * n},
        "timezones": {"+0800": 300 + 40 * n, "-0700": 300, "+0000": 50},
        "organizations": {
            "top": [
                {"organization": "acme.com", "commits": 900, "commits_last_12mo": 100 + 20 * n},
                {"organization": "other.com", "commits": 400, "commits_last_12mo": 100},
            ]
        },
    }
    summary.update(extra)
    return summary


def _portfolio(count=12):
    return [_summary(n) for n in range(count)]


# ── small helpers ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "text"), [(0.954, "95%"), (0.004, "0.4%"), (0, "0%"), (1, "100%")]
)
def test_pct(value, text):
    assert insights.pct(value) == text


@pytest.mark.parametrize(
    ("zone", "shown"), [("+0800", "UTC+08:00"), ("-0330", "UTC-03:30"), ("UTC+5", "UTC+5")]
)
def test_zone_names(zone, shown):
    assert insights._zone(zone) == shown


def test_possessive_keeps_the_name_whole():
    assert insights._owns({"name": "Requests"}) == "Requests's"


# ── the measures ─────────────────────────────────────────────────────────


def test_ai_change_and_rise():
    summary = _summary(0, ai_assisted=_ai(0.1, 0.4))
    assert insights.ai_change(summary) == (0.1, 0.4)
    assert insights.ai_rise(summary) == pytest.approx(0.3)
    # a fall is not news here
    assert insights.ai_rise(_summary(0, ai_assisted=_ai(0.4, 0.1))) is None


@pytest.mark.parametrize(
    "ai",
    [
        None,
        {"by_month": {}, "commits_by_month": dict.fromkeys(MONTHS[:6], 100)},  # six months
        _ai(0.1, 0.2, commits=5),  # too few commits
    ],
)
def test_ai_change_without_enough(ai):
    assert insights.ai_change(_summary(0, ai_assisted=ai)) is None
    assert insights.ai_rise(_summary(0, ai_assisted=ai)) is None


def test_active_days():
    assert insights.active_days(_summary(0)) == pytest.approx(2000 / 4380)
    assert insights.active_days(_summary(0, age_days=400)) is None  # too young
    assert insights.active_days(_summary(0, humans=None)) is None


def test_busiest_year():
    summary = _summary(0)
    summary["humans"]["commits_by_year"]["2019"] = 1500
    # the year of the last commit is not a full year, whatever its count
    summary["humans"]["commits_by_year"]["2026"] = 9999
    assert insights.busiest_year(summary) == (2019, 1500)
    # of two years as busy, the earlier
    assert insights.busiest_year(_summary(0)) == (2015, 1000)


@pytest.mark.parametrize(
    "extra",
    [
        {"humans": None},
        {"last_commit": "unknown"},
        {"humans": {"commits_by_year": {"2024": 9, "2025": 9}}},  # two full years
    ],
)
def test_busiest_year_without_enough(extra):
    assert insights.busiest_year(_summary(0, **extra)) is None


def test_versus_peak():
    assert insights.versus_peak(_summary(0)) == pytest.approx(0.5)
    assert insights.versus_peak(_summary(0, people_last_12mo=None)) is None
    assert insights.versus_peak(_summary(0, people_last_12mo={"commits": None})) is None
    small = {"commits_by_year": {str(y): 10 for y in range(2015, 2026)}, "active_days": 1}
    assert insights.versus_peak(_summary(0, humans=small)) is None  # a peak of 10


def test_source_kept():
    assert insights.source_kept(_summary(0)) == pytest.approx(0.3)
    assert insights.source_kept(_summary(0, source_lines=None)) is None
    assert insights.source_kept(_summary(0, age_days=100)) is None
    assert insights.source_kept(_summary(0, source_lines={"added": 500, "current": 100})) is None
    # nearly all of it still there: brought in whole, not written here
    assert insights.source_kept(_summary(0, source_lines={"added": 5000, "current": 4900})) is None


def test_top_zone():
    assert insights.top_zone(_summary(1)) == ("+0800", 340 / 690, 3)
    assert insights.zone_share(_summary(1)) == pytest.approx(340 / 690)
    # too few commits
    assert insights.top_zone(_summary(0, timezones={"+0800": 10})) is None
    # mostly UTC+0: a tool's setting, more likely than a place
    assert insights.top_zone(_summary(0, timezones={"+0000": 700, "+0800": 300})) is None
    # UTC+0 the largest, though not most of them
    assert (
        insights.top_zone(_summary(0, timezones={"+0000": 500, "+0800": 300, "-0700": 300})) is None
    )
    assert insights.zone_share(_summary(0, timezones={})) is None


@pytest.mark.parametrize(
    ("domain", "own"),
    [
        ("apache.org", True),  # a foundation
        ("pytorch.org", True),  # the project's own
        ("acme.com", False),
        ("cilium.io", True),  # the repository's name
        ("isovalent.com", True),  # the repository's owner
        ("node.com", True),  # the start of the name
        ("ab.com", False),  # too short to be the start of a name
    ],
)
def test_own_domain(domain, own):
    summary = _summary(0, name="PyTorch", repository="isovalent/cilium")
    summary["name"] = "node-and-pytorch" if domain == "node.com" else "PyTorch"
    summary["report_path"] = "pytorch/index.html"
    assert insights.own_domain(summary, domain) is own


def test_employers_and_one_employer():
    summary = _summary(5, repository="acme/thing")
    # acme.com is the project's own: other.com is all there is
    assert [row["organization"] for row in insights.employers(summary)] == ["other.com"]
    assert insights.one_employer(_summary(5)) == pytest.approx(200 / 300)
    assert insights.employers(_summary(0, organizations=None)) == []
    # too few commits from companies
    few = {"top": [{"organization": "acme.com", "commits_last_12mo": 50}]}
    assert insights.one_employer(_summary(0, organizations=few)) is None
    # or too small a part of all the commits
    assert insights.one_employer(_summary(0, commits_last_12mo=100_000)) is None


# ── the facts ────────────────────────────────────────────────────────────


def test_facts_of_the_extremes():
    portfolio = _portfolio()
    found = insights.facts(portfolio, "Gallery projects")
    assert len(found) == len(portfolio)
    last = found[-1]
    # the last project is the largest on everything: three facts, the most unusual first
    assert len(last) == 3
    assert [fact["score"] for fact in last] == sorted((f["score"] for f in last), reverse=True)
    first = last[0]
    assert set(first) == {"kind", "label", "value", "big", "sentence", "compared", "score"}
    assert first["compared"] == "The highest of the 12 Gallery projects."
    # the middle of the portfolio has nothing that stands out
    assert found[6] == []
    # the first is the lowest on the measures where that is news too
    low = {fact["kind"]: fact for fact in found[0]}
    assert low["source"]["compared"] == "The lowest of the 12 Gallery projects."
    assert "peak" in low


def test_facts_compare_a_place_below_the_first():
    found = insights.facts(_portfolio(20), "Gallery projects")
    second = {fact["kind"]: fact for fact in found[-2]}
    assert second["days"]["compared"] == "2nd highest of 20; the median project: 67% of days."


def test_facts_need_enough_projects():
    assert insights.facts(_portfolio(9)) == [[] for _ in range(9)]


KIND = {kind.id: kind for kind in insights.KINDS}


def _said(kind, summary):
    value = KIND[kind].measure(summary)
    return KIND[kind].big(summary, value), KIND[kind].say(summary, value)


def test_sentences():
    p11 = _summary(11)
    assert _said("ai", p11) == (
        "11%",
        "The share of p11's commits that name an AI coding assistant went from 0% to 11% "
        "in a year.",
    )
    assert _said("days", p11) == (
        "71%",
        "p11 has had a commit by a person on 71% of the days since its first one: 3,100 days "
        "in 12 years.",
    )
    assert _said("zone", p11) == (
        "68%",
        "68% of p11's commits were made in one time zone, UTC+08:00, of the 3 it has commits from.",
    )
    assert _said("employer", p11)[1] == (
        "Of p11's commits from company addresses in the last 12 months, 76% came from one "
        "company: acme.com."
    )


def test_peak_and_source_sentences_both_ways():
    busy = _summary(11, people_last_12mo={"commits": 1600})
    busy["source_lines"]["current"] = 88_000
    quiet = _summary(0, people_last_12mo={"commits": 30})
    quiet["source_lines"]["current"] = 10_000
    assert _said("peak", busy) == (
        "1.6×",
        "p11's last 12 months were its busiest yet: 1,600 commits by people, more than in "
        "any full year before (1,000 in 2015).",
    )
    assert _said("peak", quiet) == (
        "3%",
        "People made 3% as many commits to p0 in the last 12 months as in 2015, its busiest "
        "year (30 against 1,000).",
    )
    assert _said("source", quiet)[1] == (
        "Of the 100,000 lines ever written into p0's own source, 10% are still there; the "
        "rest were rewritten or removed."
    )
    assert _said("source", busy) == (
        "88%",
        "88% of the 100,000 lines ever written into p11's own source are still there.",
    )


# ── how a page shows them ────────────────────────────────────────────────


def test_facts_html():
    found = insights.facts(_portfolio(), "projects")[-1]
    page = insights.facts_html(found)
    assert page.startswith('<ul class="insights">')
    assert page.count('<li class="insight">') == 3
    assert '<span class="insight-big">' in page


def test_overview_html():
    found = insights.facts(_portfolio(), "projects")[-1]
    section = insights.overview_html("<p11>", found, 11, "My <Portfolio>")
    assert '<section class="insights-section" id="what-stands-out">' in section
    assert "What stands out" in section
    assert "Next to the 11 other projects of" in section
    assert "My &lt;Portfolio&gt;" in section
    assert "&lt;p11&gt;" in section and "<p11>" not in section
    assert '<a href="compare.html">How &lt;p11&gt; compares' in section
    assert insights.overview_html("x", [], 11, "y") == ""
