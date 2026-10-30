"""Tests for scripts/gallery_ecosystems.py, the gallery's ecosystem pages.

The scripts live outside the ``gitstats`` package (they are run from a
checkout), so the scripts directory is put on the path to import them.
"""

import datetime
import json
import os
import sys
import xml.etree.ElementTree as ET

import pytest

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, _SCRIPTS)

import gallery_ecosystems as eco  # noqa: E402
from gallery_repos import Group, Repo  # noqa: E402

from gitstats.report_creator import NAV_START, SKIP_LINK  # noqa: E402

NOW = datetime.datetime(2026, 10, 21, 12, 0)
Q2 = ["2026-04", "2026-05", "2026-06"]
Q3 = ["2026-07", "2026-08", "2026-09"]
PYTHON = Group("python", "Python", "Python open source projects")
CHINA = Group("china", "Open source from China", "Open source projects from China")
EMPTY = Group("empty", "Empty", "Empty projects")


def _ai(q3, q2=(0, 10), assistants=None):
    """An ai_assisted block: (named, all) commits in each of Q2 and Q3."""
    by_month = {Q2[0]: q2[0], Q3[0]: q3[0]}
    all_by_month = {month: 0 for month in Q2 + Q3}
    all_by_month[Q2[0]], all_by_month[Q3[0]] = q2[1], q3[1]
    return {
        "commits": q2[0] + q3[0],
        "assistants": assistants or {},
        "by_month": by_month,
        "commits_by_month": all_by_month,
    }


def _summary(repo_id, name="", ai=None, **fields):
    return {
        "name": name,
        "report_path": f"{repo_id}/index.html",
        "ai_assisted": ai,
        "commits_last_12mo": 100,
        "active_authors_12mo": 7,
        "era": "steady",
        "last_commit": "2026-10-20 10:00:00",
        **fields,
    }


def _repo(repo_id, group="python"):
    return Repo(repo_id, repo_id.title(), f"owner/{repo_id}", group)


# ── the numbers ──────────────────────────────────────────────────────────


def test_quarter_counts():
    ai = _ai((3, 30))
    assert eco.quarter_counts(ai, Q3) == (3, 30)
    assert eco.quarter_counts(ai, ["2026-10"]) is None  # not covered
    assert eco.quarter_counts(None, Q3) is None


@pytest.mark.parametrize(
    ("counts", "share", "text"),
    [
        ((3, 30), 0.1, "10.0%"),
        ((0, 30), 0.0, "0%"),
        # as ai.html writes it: 1 of 1,628 commits is "0.1%" on both pages
        ((1, 1628), 1 / 1628, "0.1%"),
        ((1, 2500), 0.0004, "<0.1%"),
        ((3634, 3635), 3634 / 3635, "99.9%"),
        ((0, 0), None, "–"),
        (None, None, "–"),
    ],
)
def test_share_and_percent(counts, share, text):
    assert eco.share_of(counts) == share
    assert eco.percent(share) == text


def test_rank_rows_by_the_last_quarter():
    repos = [_repo(r) for r in ("low", "high", "tie", "none", "missing", "quiet", "few", "two")]
    summaries = {
        "low": _summary("low", "Low", _ai((1, 100))),
        "high": _summary("high", "High", _ai((50, 100), (5, 10), {"Claude": 9, "Codex": 1})),
        # the same share as "low", with more commits: before it
        "tie": _summary("tie", "Tie", _ai((2, 200))),
        # data from before the assistants were counted
        "none": _summary("none", "", None),
        # no commits in the quarter: no share, so last
        "quiet": _summary("quiet", "Quiet", _ai((0, 0))),
        # one of 3 commits: a third, from too few commits to rank
        "few": _summary("few", "Few", _ai((1, 3))),
        "two": _summary("two", "Two", _ai((1, 29))),
    }
    rows = eco.rank_rows(repos, summaries, NOW)
    assert [row["id"] for row in rows] == ["high", "tie", "low", "few", "two", "none", "quiet"]
    assert [row["rank"] for row in rows] == [1, 2, 3, None, None, None, None]
    high = rows[0]
    assert high["quarter"] == (50, 100)
    assert high["previous_quarter"] == (5, 10)
    assert high["assistants"] == ["Claude", "Codex"]
    assert high["report"] == "../high/"
    assert high["last_commit"] == "2026-10-20"
    none = rows[5]
    assert none["name"] == "None"  # from the list, when the summary has none
    assert none["quarter"] is None
    assert none["assistants"] == []


def test_rank_rows_of_a_summary_kept_from_an_earlier_build():
    # made on 2026-09-14, its report failing since: September was not over,
    # and Jul–Sep is not a quarter it can count
    kept = _summary("kept", "Kept", _ai((5, 50)), generated_at="2026-09-14T04:00:00+00:00")
    fresh = _summary("fresh", "Fresh", _ai((1, 50)), generated_at="2026-10-19T04:00:00+00:00")
    rows = eco.rank_rows([_repo("kept"), _repo("fresh")], {"kept": kept, "fresh": fresh}, NOW)
    assert [(row["id"], row["quarter"]) for row in rows] == [("fresh", (1, 50)), ("kept", None)]
    assert rows[1]["previous_quarter"] == (0, 10)


def test_group_summary():
    rows = eco.rank_rows(
        [_repo(r) for r in "abcde"],
        {
            "a": _summary("a", "A", _ai((60, 100))),
            "b": _summary("b", "B", _ai((10, 100))),
            "c": _summary("c", "C", _ai((0, 100))),
            "d": _summary("d", "D", _ai((0, 0))),
            # the largest share, of 3 commits: not in the median, nor the highest
            "e": _summary("e", "E", _ai((3, 3))),
        },
        NOW,
    )
    assert eco.group_summary(rows) == {
        "repositories": 5,
        "with_commits": 4,
        "ranked": 3,
        "naming": 2,
        "median_share": 0.1,
        "highest": {"id": "a", "name": "A", "share": 0.6},
    }


def test_group_summary_when_none_names_one_or_none_has_commits():
    zero = eco.rank_rows([_repo("a")], {"a": _summary("a", "A", _ai((0, 100)))}, NOW)
    assert eco.group_summary(zero)["highest"] is None
    assert eco.group_summary(zero)["median_share"] == 0.0
    quiet = eco.rank_rows([_repo("a")], {"a": _summary("a", "A", _ai((0, 0)))}, NOW)
    summary = eco.group_summary(quiet)
    assert summary["median_share"] is None
    assert summary["with_commits"] == 0
    few = eco.rank_rows([_repo("a")], {"a": _summary("a", "A", _ai((2, 3)))}, NOW)
    summary = eco.group_summary(few)
    assert (summary["with_commits"], summary["ranked"], summary["highest"]) == (1, 0, None)


def test_summary_sentence():
    summary = {
        "repositories": 4,
        "with_commits": 3,
        "ranked": 3,
        "naming": 2,
        "median_share": 0.1,
        "highest": {"id": "a", "name": "pandas", "share": 0.6674},
    }
    assert eco.summary_sentence(PYTHON, summary, "Jul–Sep 2026") == (
        "In Jul–Sep 2026, the median project among 3 Python open source projects with 30 "
        "commits or more had 10.0% of its commits name an AI coding assistant; the highest "
        "was pandas, at 66.7%. 2 of 3 named one at least once."
    )
    few = {**summary, "ranked": 0, "naming": 0, "median_share": None, "highest": None}
    assert eco.summary_sentence(PYTHON, few, "Q") == (
        "None of the 4 Python open source projects in the Gallery has 30 commits or more "
        "in Q, so none is ranked."
    )
    nobody = {**summary, "naming": 0, "median_share": 0.0, "highest": None}
    assert eco.summary_sentence(CHINA, nobody, "Q").endswith(
        "open source projects from China with 30 commits or more had 0% of its commits "
        "name an AI coding assistant; none of them named one."
    )
    quiet = {**nobody, "with_commits": 0, "ranked": 0, "median_share": None}
    assert eco.summary_sentence(CHINA, quiet, "Q") == (
        "None of the 4 open source projects from China in the Gallery has commits in Q."
    )


def test_page_title():
    assert eco.page_title(PYTHON, "2026-Q3") == (
        "Python open source projects ranked by AI-assisted commits – 2026 Q3"
    )


# ── the files ────────────────────────────────────────────────────────────


def _gallery(tmp_path):
    groups = [PYTHON, CHINA, EMPTY]
    repos = [
        _repo("pandas"),
        _repo("flask"),
        _repo("tiny"),
        _repo("dubbo", "china"),
        _repo("gone", "empty"),  # in the list, without a report
    ]
    summaries = [
        _summary("pandas", "pandas", _ai((60, 100), (40, 100), {"Claude": 50})),
        _summary("flask", "Flask", _ai((0, 40)), era=""),
        # a third of 3 commits: listed, not ranked
        _summary("tiny", "Tiny", _ai((1, 3))),
        _summary("dubbo", "Apache <Dubbo>", _ai((0, 0))),
    ]
    return groups, repos, summaries


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_write_ecosystems(tmp_path):
    groups, repos, summaries = _gallery(tmp_path)
    site = "https://example.com/gallery/"
    written = eco.write_ecosystems(
        str(tmp_path), groups, repos, summaries, site, card=True, version="2.12.0", now=NOW
    )
    assert written == [PYTHON, CHINA]  # "empty" has no report, so no page
    folder = tmp_path / "ecosystems"
    assert sorted(os.listdir(folder)) == [
        "china-card.html",
        "china.html",
        "china.json",
        "index-card.html",
        "index.html",
        "index.json",
        "python-card.html",
        "python.html",
        "python.json",
    ]

    page = _read(folder / "python.html")
    title = "Python open source projects ranked by AI-assisted commits – 2026 Q3"
    assert f"<title>{title} | GitStats Gallery</title>" in page
    assert '<meta name="description" content="In Jul–Sep 2026, the median' in page
    assert f'<meta property="og:title" content="{title}">' in page
    assert (
        '<meta property="og:image" content="https://example.com/gallery/ecosystems/'
        'python-card.png">'
    ) in page
    assert (
        '<link rel="canonical" href="https://example.com/gallery/ecosystems/python.html">' in page
    )
    assert '<link rel="stylesheet" href="../gitstats.css"' in page
    # the reports' frame: a skip link, the nav, the content, the footer
    assert (
        page.index(SKIP_LINK)
        < page.index(NAV_START)
        < page.index('<main id="main">')
        < page.index('<table class="sortable" id="ecosystem">')
        < page.index("</main>")
        < page.index('<footer class="footer">')
    )
    # ranked, linked to the reports, the counts on hover
    assert page.index(">pandas</a>") < page.index(">Flask</a>")
    assert '<td class="num" title="60 of 100 commits" data-sort="0.600000">60.0%</td>' in page
    assert '<span class="history-era history-era-steady">steady</span>' in page
    assert "<td>Claude</td>" in page
    # too few commits: after the ranked ones, without a rank, and why
    assert page.index(">Flask</a>") < page.index(">Tiny</a>")
    assert (
        '<td class="num" data-sort="3" title="fewer than 30 commits in Jul–Sep 2026: '
        'not ranked">&ndash;</td><td><a href="../tiny/">Tiny</a>'
    ) in page
    assert "1 project has fewer than 30 commits in Jul–Sep 2026" in page
    assert "<th>Named most (all time)</th>" in page
    assert "the 12 months up to each report" in page
    # every page of the ecosystems is under their tab
    assert 'class="active" aria-current="page">Ecosystems</a>' in page
    assert '<a href="china.html">Open source from China</a>' in page  # the others
    assert 'href="empty.html"' not in page  # no page, so no link

    china = _read(folder / "china.html")
    assert "Apache &lt;Dubbo&gt;" in china
    assert "<Dubbo>" not in china
    assert "none names one" in china

    data = json.loads(_read(folder / "python.json"))
    assert data["schema_version"] == 2
    assert [(row["id"], row["rank"]) for row in data["repositories"]] == [
        ("pandas", 1),
        ("flask", 2),
        ("tiny", None),
    ]
    assert data["summary"]["ranked"] == 2
    assert data["generated_by"] == "gitstats 2.12.0"
    assert data["ecosystem"] == {"id": "python", "name": "Python", "title": PYTHON.title}
    assert data["quarter"] == {"id": "2026-Q3", "label": "Jul–Sep 2026"}
    assert data["previous_quarter"]["id"] == "2026-Q2"
    assert data["summary"]["highest"] == {"id": "pandas", "name": "pandas", "share": 0.6}
    first = data["repositories"][0]
    assert first["quarter"] == {"commits": 100, "ai_assisted": 60, "share": 0.6}
    assert first["repository"] == "owner/pandas"
    assert set(first) == {
        "rank", "id", "name", "repository", "report", "quarter", "previous_quarter",
        "commits_last_12mo", "active_authors_12mo", "health", "last_commit", "assistants",
    }  # fmt: skip
    dubbo = json.loads(_read(folder / "china.json"))["repositories"][0]
    assert dubbo["quarter"] == {"commits": 0, "ai_assisted": 0, "share": None}

    index = json.loads(_read(folder / "index.json"))
    assert [e["id"] for e in index["ecosystems"]] == ["python", "china"]
    assert index["ecosystems"][0]["page"] == "python.html"
    index_page = _read(folder / "index.html")
    assert "Open source ecosystems ranked by AI-assisted commits – 2026 Q3" in index_page
    assert '<link rel="canonical" href="https://example.com/gallery/ecosystems/">' in index_page
    assert 'class="active" aria-current="page">Ecosystems</a>' in index_page
    assert "index-card.png" in index_page
    # "1 / 2" sorts by how many name one
    assert '<td class="num" data-sort="1">1 / 2</td>' in index_page

    card = _read(folder / "python-card.html")
    assert "<b>pandas</b>" in card
    assert "<b>Flask</b>" not in card  # bars are shares above 0
    assert "<b>Tiny</b>" not in card  # and ranked
    assert "<b>Python</b>" in _read(folder / "index-card.html")

    tree = ET.fromstring(_read(tmp_path / "sitemap.xml"))
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    locs = [url.find(f"{ns}loc").text for url in tree]
    assert locs == [
        site,
        site + "ai.html",
        site + "organizations.html",
        site + "ecosystems/",
        site + "ecosystems/python.html",
        site + "ecosystems/china.html",
        site + "pandas/",
        site + "flask/",
        site + "tiny/",
        site + "dubbo/",
    ]
    assert {url.find(f"{ns}lastmod").text for url in tree} == {"2026-10-21"}


def test_write_ecosystems_without_an_address(tmp_path):
    groups, repos, summaries = _gallery(tmp_path)
    assert eco.write_ecosystems(str(tmp_path), groups, repos, summaries) == [PYTHON, CHINA]
    assert not (tmp_path / "sitemap.xml").exists()  # a sitemap needs addresses
    page = _read(tmp_path / "ecosystems" / "python.html")
    assert "og:image" not in page
    assert 'rel="canonical"' not in page
    assert "og:image" not in _read(tmp_path / "ecosystems" / "index.html")


def test_write_ecosystems_with_no_report(tmp_path):
    assert eco.write_ecosystems(str(tmp_path), [EMPTY], [_repo("gone", "empty")], []) == []
    assert not (tmp_path / "ecosystems").exists()


def test_index_without_any_share(tmp_path):
    groups, repos = [CHINA], [_repo("dubbo", "china")]
    summaries = [_summary("dubbo", "Dubbo", _ai((0, 0)))]
    eco.write_ecosystems(str(tmp_path), groups, repos, summaries, now=NOW)
    index = _read(tmp_path / "ecosystems" / "index.html")
    assert "<td>&ndash;</td>" in index
    assert '<div class="bars"></div>' in _read(tmp_path / "ecosystems" / "index-card.html")


@pytest.mark.parametrize("name", ["../outside.html", "."])
def test_write_stays_in_the_gallery(tmp_path, name):
    with pytest.raises(ValueError, match="outside the gallery"):
        eco._write(str(tmp_path / "gallery"), name, "x")


def test_sitemap_lists_the_organizations_pages(tmp_path):
    groups, repos, summaries = _gallery(tmp_path)
    orgs = tmp_path / "orgs"
    orgs.mkdir()
    for name in ("google.com.html", "google.com.svg", "acme.org.html"):
        (orgs / name).write_text("x", encoding="utf-8")
    site = "https://example.com/gallery/"
    eco.write_ecosystems(str(tmp_path), groups, repos, summaries, site, now=NOW)
    sitemap = _read(tmp_path / "sitemap.xml")
    assert f"<loc>{site}orgs/acme.org.html</loc>" in sitemap
    assert f"<loc>{site}orgs/google.com.html</loc>" in sitemap
    assert "google.com.svg" not in sitemap
    assert sitemap.index("acme.org") < sitemap.index("google.com")
