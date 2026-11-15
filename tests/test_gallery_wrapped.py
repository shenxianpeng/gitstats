"""Tests for scripts/gallery_wrapped.py, the gallery's Repo Wrapped page.

The scripts live outside the ``gitstats`` package (they are run from a
checkout), so the scripts directory is put on the path to import them.
"""

import datetime
import json
import os
import re
import sys

import pytest

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, _SCRIPTS)

import gallery_wrapped as wrapped  # noqa: E402

from gitstats.report_creator import NAV_START, SKIP_LINK  # noqa: E402
from gitstats.wrapped import COMPARED  # noqa: E402

NOW = datetime.datetime(2026, 12, 5, 12, 0)
GROUPS = {"python": "Python", "cncf": "Cloud Native"}


def _numbers(commits, **numbers):
    return {
        "commits": commits,
        "active_days": 50,
        "longest_streak": 4,
        "lines_changed": 9000,
        "contributors": 6,
        "new_contributors": 2,
        "releases": 3,
        **numbers,
    }


def _data(commits=100, before=80, year=2026, complete=False, **numbers):
    """The data of a card, as gitstats writes it next to one; ``before`` is
    the commits of the year before (None: there is no year before), or the
    numbers of it."""
    through = "12-31" if complete else "12-05"
    previous = None
    if before is not None:
        previous = {
            "year": year - 1,
            "through": f"{year - 1}-{through}",
            **(before if isinstance(before, dict) else _numbers(before)),
            "monthly_commits": [0] * 12,
        }
    return {
        "schema_version": 1,
        "generated_by": "gitstats 2.13.0",
        "card": f"wrapped-{year}.svg",
        "theme": "midnight",
        "year": year,
        "project_name": "as the report named it",
        **_numbers(commits, **numbers),
        "top_author": "Somebody",
        "monthly_commits": [0] * 12,
        "through": f"{year}-{through}",
        "complete": complete,
        "previous": previous,
    }


def _report(root, repo_id, data, page=True, card=True):
    """A report's folder with the data of its card, the card and its page."""
    folder = root / repo_id
    folder.mkdir(exist_ok=True)
    name = f"wrapped-{data['year']}.json" if isinstance(data, dict) else "wrapped-2026.json"
    text = json.dumps(data) if not isinstance(data, str) else data
    (folder / name).write_text(text, encoding="utf-8")
    if card:
        (folder / f"wrapped-{name[8:12]}.svg").write_text("<svg/>", encoding="utf-8")
    if page:
        (folder / "wrapped.html").write_text("<html/>", encoding="utf-8")


def _summary(repo_id, name="", group="python"):
    return {"name": name, "report_path": f"{repo_id}/index.html", "group": group}


def _card(repo_id, name=None, group="python", **data):
    """A card as load_cards() gives it."""
    kept = wrapped._card_of(_data(**data))
    return {
        "id": repo_id,
        "name": name or repo_id.title(),
        "group": group,
        "data": f"wrapped-{kept['year']}.json",
        **kept,
    }


# ── the numbers ──────────────────────────────────────────────────────────


def test_what_is_kept_of_a_cards_data():
    kept = wrapped._card_of(_data(commits=100, before=80))
    assert kept == {
        "year": 2026,
        "complete": False,
        "through": "2026-12-05",
        "card": "wrapped-2026.svg",
        **_numbers(100),
        "previous": {"year": 2025, "through": "2025-12-05", **_numbers(80)},
    }
    assert wrapped._card_of(_data(before=None))["previous"] is None
    assert wrapped._card_of(_data(complete=True))["complete"] is True


def test_a_cards_file_is_looked_for_next_to_its_data():
    data = _data()
    data["card"] = "../../elsewhere/card.svg"
    assert wrapped._card_of(data)["card"] == "card.svg"


def _without(key, where=None):
    data = _data()
    del (data["previous"] if where else data)[key]
    return data


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        "wrapped",
        _without("year"),
        _without("commits"),
        _without("releases"),
        _without("card"),
        _without("through"),
        {**_data(), "year": True},
        {**_data(), "year": "2026"},
        {**_data(), "commits": -1},
        {**_data(), "commits": 1.5},
        {**_data(), "card": 7},
        {**_data(), "previous": [1, 2]},
        _without("commits", "previous"),
        _without("year", "previous"),
        _without("through", "previous"),
        {**_data(), "previous": {**_data()["previous"], "contributors": "many"}},
    ],
)
def test_what_is_not_the_data_of_a_card(data):
    assert wrapped._card_of(data) is None


def test_load_cards(tmp_path, capsys):
    _report(tmp_path, "django", _data(commits=300))
    _report(tmp_path, "flask", _data(commits=40, before=None))
    # the card of an earlier year too: the latest is the one read
    _report(tmp_path, "pandas", _data(commits=5, year=2024))
    _report(tmp_path, "pandas", _data(commits=700, year=2026))
    (tmp_path / "plain").mkdir()  # a report made without --wrapped
    _report(tmp_path, "broken", "{not json")
    _report(tmp_path, "other", {"year": 2026, "commits": "many"})
    _report(tmp_path, "nopage", _data(), page=False)  # made before cards had a page
    _report(tmp_path, "nocard", _data(), card=False)
    summaries = [
        _summary("pandas", "pandas"),
        _summary("django", "Django", "web"),
        _summary("flask"),
        _summary("plain"),
        _summary("broken"),
        _summary("other"),
        _summary("nopage"),
        _summary("nocard"),
        _summary("missing"),  # in the list, without a folder
    ]

    cards = wrapped.load_cards(str(tmp_path), summaries)

    # in the order of the summaries, each with the report it belongs to
    assert [(card["id"], card["name"], card["group"]) for card in cards] == [
        ("pandas", "pandas", "python"),
        ("django", "Django", "web"),
        ("flask", "flask", "python"),  # a report without a name goes by its folder
    ]
    assert [(card["year"], card["commits"], card["data"]) for card in cards] == [
        (2026, 700, "wrapped-2026.json"),
        (2026, 300, "wrapped-2026.json"),
        (2026, 40, "wrapped-2026.json"),
    ]
    assert cards[1]["previous"]["commits"] == 80
    assert cards[2]["previous"] is None
    errors = capsys.readouterr().err
    assert "Skipping unreadable card data: broken/wrapped-2026.json (" in errors
    assert "Skipping data that is not a card's: other/wrapped-2026.json" in errors
    assert "nopage" not in errors and "plain" not in errors


def test_load_cards_reads_nothing_outside_the_gallery(tmp_path):
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    _report(tmp_path, "outside", _data())
    _report(gallery, "inside", _data())
    (gallery / "inside" / "nested").mkdir()
    _report(gallery / "inside", "nested", _data())
    summaries = [
        {"name": "Outside", "report_path": "../outside/index.html"},
        {"name": "Up", "report_path": "../index.html"},
        {"name": "Inside", "report_path": "inside/index.html"},
    ]
    cards = wrapped.load_cards(str(gallery), summaries)
    # only the folder directly under the gallery; a summary without a group has none
    assert [(card["id"], card["group"]) for card in cards] == [("inside", "")]


def test_the_year_is_the_one_most_cards_are_for():
    cards = [
        _card("old", commits=900, year=2025),  # kept from an earlier build
        _card("django", commits=300),
        _card("flask", commits=40),
        _card("pandas", commits=700),
    ]
    year, kept = wrapped.cards_of_the_year(cards)
    assert year == 2026
    # the most commits first
    assert [card["id"] for card in kept] == ["pandas", "django", "flask"]

    # as many cards of each year: the later one
    year, kept = wrapped.cards_of_the_year(cards[:2])
    assert (year, [card["id"] for card in kept]) == (2026, ["django"])

    # as many commits: by name, whatever its case
    tied = [_card("b", "beta"), _card("c", "Alpha"), _card("a", "gamma")]
    assert [card["name"] for card in wrapped.cards_of_the_year(tied)[1]] == [
        "Alpha",
        "beta",
        "gamma",
    ]
    assert wrapped.cards_of_the_year([]) == (None, [])


def test_totals_compare_like_with_like():
    cards = [
        _card("pandas", commits=700, before=500),
        _card("django", commits=300, before=350),
        _card("new", commits=40, before=None),
    ]
    assert wrapped.totals(cards) == {
        "repositories": 3,
        "commits": 1040,
        # the project that began this year is not held against nothing
        "compared": {"repositories": 2, "commits": 1000, "previous_commits": 850},
    }


def test_growth_needs_commits_to_grow_from():
    assert wrapped.growth(_card("a", commits=300, before=200)) == pytest.approx(0.5)
    assert wrapped.growth(_card("a", commits=50, before=100)) == pytest.approx(-0.5)
    assert wrapped.growth(_card("a", commits=600, before=99)) is None
    assert wrapped.growth(_card("a", commits=600, before=None)) is None
    assert wrapped.MIN_BASE_COMMITS == 100


def test_what_stands_out():
    cards = [
        _card("pandas", commits=700, before=500, longest_streak=30),
        # five times as many, from 12 commits: not what grew fastest
        _card("tiny", commits=60, before=12, new_contributors=1),
        _card("django", commits=300, before=150, longest_streak=45, new_contributors=9),
        _card("flask", commits=40, before=None, new_contributors=9),
    ]
    _, cards = wrapped.cards_of_the_year(cards)
    assert [(what, card["id"], number) for what, card, number in wrapped.standing_out(cards)] == [
        ("Most commits", "pandas", "700"),
        ("Fastest growing", "django", "+100%"),
        ("Longest streak", "django", "45 days"),
        # as many as Flask: the one with more commits
        ("Most new contributors", "django", "9"),
    ]


def test_a_measure_nobody_has_a_number_for_is_left_out():
    cards = [
        _card("a", commits=40, before=None, longest_streak=0, new_contributors=0),
        _card("b", commits=30, before=200, longest_streak=0, new_contributors=0),
    ]
    assert [what for what, _, _ in wrapped.standing_out(cards)] == ["Most commits"]
    # a year without commits is no card, but the data may say so
    nothing = [_card("a", commits=0, before=None, longest_streak=0, new_contributors=0)]
    assert wrapped.standing_out(nothing) == []


def test_period():
    under_way = [_card("a"), _card("b", before=None)]
    assert wrapped.period(2026, under_way) == ("2026 so far", "the same days of 2025")
    over = [_card("a", complete=True), _card("b", complete=True)]
    assert wrapped.period(2026, over) == ("2026", "2025")
    # one report made before the year ended: the page does not call the year over
    assert wrapped.period(2026, [*over, _card("c")])[0] == "2026 so far"
    assert wrapped.period(2026, [_card("a", before=None)]) == ("2026 so far", "")


def test_index_json():
    cards = [_card("pandas", "pandas", commits=700), _card("flask", before=None, group="web")]
    meta = {"generated_by": "gitstats 2.13.0", "generated_at": "2026-12-05T12:00:00+00:00"}
    data = wrapped.index_json(2026, cards, meta)
    assert list(data) == [
        "schema_version",
        "generated_by",
        "generated_at",
        "year",
        "complete",
        "totals",
        "repositories",
    ]
    assert (data["schema_version"], data["year"], data["complete"]) == (1, 2026, False)
    assert data["totals"] == wrapped.totals(cards)
    assert data["repositories"][0] == {
        "id": "pandas",
        "name": "pandas",
        "group": "python",
        "page": "pandas/wrapped.html",
        "card": "pandas/wrapped-2026.svg",
        "data": "pandas/wrapped-2026.json",
        "through": "2026-12-05",
        **_numbers(700),
        "previous": {"year": 2025, "through": "2025-12-05", **_numbers(80)},
    }
    assert data["repositories"][1]["previous"] is None
    assert set(COMPARED) <= set(data["repositories"][1])


# ── the page ─────────────────────────────────────────────────────────────


def test_a_row_of_the_table():
    card = _card("pandas", "pan<das>", commits=1200, before=1000, contributors=9)
    row = wrapped._row_html(card, GROUPS)
    assert row.startswith(
        '<tr><td><a href="../pandas/wrapped.html">pan&lt;das&gt;</a></td><td>Python</td>'
    )
    # each number alone in its cell; how it moved sorts by how much
    assert (
        '<td class="num">1,200</td><td class="num" data-sort="0.200000">'
        '<span class="wrapped-up">+20%</span></td>'
    ) in row
    assert (
        '<td class="num">9</td><td class="num" data-sort="3.000000">'
        '<span class="wrapped-up">+3</span></td>'
    ) in row
    assert row.endswith(
        '<td class="num">2</td><td class="num">50</td><td class="num">4</td>'
        '<td class="num">9,000</td><td class="num">3</td></tr>'
    )
    # without ecosystems there is no column for one
    assert "<td>Python</td>" not in wrapped._row_html(card, {})
    # a group the list no longer has: an empty cell, not an error
    assert "</a></td><td></td>" in wrapped._row_html(_card("x", group="gone"), GROUPS)


def test_how_a_number_moved_in_its_cell():
    down = _card("a", commits=50, before=100, contributors=6)
    assert wrapped._moved_cell(down, "commits") == (
        '<td class="num" data-sort="-0.500000"><span class="wrapped-down">-50%</span></td>'
    )
    assert wrapped._moved_cell(down, "contributors") == (
        '<td class="num" data-sort="0.000000"><span class="wrapped-same">same</span></td>'
    )
    # no year before, or none of them then: an empty cell
    assert wrapped._moved_cell(_card("a", before=None), "commits") == '<td class="num"></td>'
    nothing = _card("a", before=_numbers(10, lines_changed=0))
    assert wrapped._moved_cell(nothing, "lines_changed") == '<td class="num"></td>'


def test_tiles():
    cards = [
        _card("pandas", "pan<das>", commits=700, before=500, longest_streak=30),
        _card("django", commits=300, before=350),
    ]
    assert wrapped._tiles(2026, cards) == [
        ("Commits", "1,000", "+18% on the same days of 2025"),
        ("Most commits", "700", '<a href="../pandas/wrapped.html">pan&lt;das&gt;</a>'),
        ("Fastest growing", "+40%", '<a href="../pandas/wrapped.html">pan&lt;das&gt;</a>'),
        ("Longest streak", "30 days", '<a href="../pandas/wrapped.html">pan&lt;das&gt;</a>'),
        ("Most new contributors", "2", '<a href="../pandas/wrapped.html">pan&lt;das&gt;</a>'),
    ]


def test_the_commits_tile_says_what_it_is_compared_with():
    new = _card("new", commits=40, before=None)
    some = [_card("pandas", commits=700, before=500), new]
    assert wrapped._tiles(2026, some)[0] == (
        "Commits",
        "740",
        "+40% on the same days of 2025 &middot; in the 1 with commits then",
    )
    assert wrapped._tiles(2026, [new])[0] == ("Commits", "40", "in 1 project")
    over = [_card("a", commits=500, before=500, complete=True)]
    assert wrapped._tiles(2026, over)[0] == ("Commits", "500", "level with 2025")


def test_description():
    cards = [_card("pandas", commits=700, before=500), _card("django", commits=300, before=350)]
    assert wrapped.description(2026, cards) == (
        "2026 so far in 2 open source projects: 1,000 commits, +18% on the same days of "
        "2025. Each project's year on a card."
    )
    alone = [_card("new", commits=40, before=None, complete=True)]
    assert wrapped.description(2026, alone) == (
        "2026 in 1 open source project: 40 commits. Each project's year on a card."
    )


def test_index_page():
    cards = [
        _card("pandas", "pan<das>", commits=700, before=500),
        _card("django", "Django", commits=300, before=350, group="cncf"),
    ]
    tabs = [("ai.html", "AI-assisted commits"), ("ecosystems/index.html", "Eco<systems>")]
    site = "https://example.com/gallery/"
    page = wrapped.index_page(2026, cards, GROUPS, tabs, site, True, "2026-12-05")

    assert page.startswith("<!DOCTYPE html>")
    assert "<title>Repo Wrapped 2026: 2 open source projects | GitStats Gallery</title>" in page
    assert '<link rel="canonical" href="https://example.com/gallery/wrapped/">' in page
    assert (
        '<meta property="og:image" content="https://example.com/gallery/wrapped/index-card.png">'
    ) in page
    assert '<meta property="og:url" content="https://example.com/gallery/wrapped/">' in page
    assert f'content="{wrapped.description(2026, cards).replace(chr(39), "&#x27;")}"' in page
    assert '<link rel="stylesheet" href="../gitstats.css" type="text/css">' in page
    assert SKIP_LINK in page

    # the gallery's nav, this page the current one, after the others
    nav = page[page.index(NAV_START) : page.index("<h1>")]
    assert re.findall(r'<li><a href="([^"]+)"[^>]*>([^<]+)</a></li>', nav) == [
        ("../index.html", "GitStats Gallery"),
        ("../ai.html", "AI-assisted commits"),
        ("../ecosystems/index.html", "Eco&lt;systems&gt;"),
        ("index.html", "Wrapped 2026"),
    ]
    assert '<a href="index.html" class="active" aria-current="page">Wrapped 2026</a>' in nav

    assert "<h1>Repo Wrapped 2026</h1>" in page
    assert (
        '<p class="portfolio-subtitle">2 projects &middot; 2026 so far &middot; updated '
        '2026-12-05 &middot; <a href="index.json">data</a></p>'
    ) in page
    assert "One year in each project of the Gallery, compared with the same days of 2025:" in page
    assert "<dt>Fastest growing</dt>" in page
    assert '<table class="sortable" id="wrapped"><tr><th>Project</th><th>Ecosystem</th>' in page
    assert page.count("<tr>") == 3
    assert "<td>Cloud Native</td>" in page
    # the cards, each leading to the repository's own page
    assert (
        '<div class="wrapped-wall"><a href="../pandas/wrapped.html" title="pan&lt;das&gt;">'
        '<img loading="lazy" src="../pandas/wrapped-2026.svg" width="270" height="270" '
        'alt="Repo Wrapped card for pan&lt;das&gt; in 2026"></a>'
    ) in page
    assert page.count('<img loading="lazy"') == 2
    assert page.rstrip().endswith("</body>\n</html>")


def test_index_page_alone():
    """Without an address, ecosystems or a year before."""
    cards = [_card("new", commits=40, before=None, complete=True)]
    page = wrapped.index_page(2026, cards, {}, [], "", False, "2027-01-04")
    assert "og:image" not in page
    assert 'rel="canonical"' not in page
    assert "<th>Project</th><th class=" in page
    assert "One year in each project of the Gallery: its commits," in page
    assert "<title>Repo Wrapped 2026: 1 open source project | GitStats Gallery</title>" in page
    assert '<p class="portfolio-subtitle">1 project &middot; 2026 &middot;' in page
    assert "<dt>Fastest growing</dt>" not in page
    assert re.findall(r'<li><a href="([^"]+)"', page) == ["../index.html", "index.html"]


def test_index_card():
    cards = [_card(f"p{n}", f"Project <{n}>", commits=700 - 100 * n) for n in range(8)]
    card = wrapped.index_card(2026, cards)
    assert "<title>Repo Wrapped 2026</title>" in card
    assert '<div class="brand">// Repo Wrapped 2026</div><h1>8 open source projects</h1>' in card
    assert '<p class="sub">Commits in 2026 so far. Each project has its card.</p>' in card
    # the six with the most commits, the first the full width
    assert card.count("<div><b>") == 6
    assert (
        '<div><b>Project &lt;0&gt;</b><i style="width:100.0%"></i><span>700</span></div>'
    ) in card
    assert '<i style="width:28.6%"></i><span>200</span></div>' in card
    assert "Project &lt;6&gt;" not in card


def test_index_card_of_cards_without_commits():
    card = wrapped.index_card(2026, [_card("a", commits=0, before=None, complete=True)])
    assert '<i style="width:0.0%"></i><span>0</span>' in card
    assert "Commits in 2026." in card
    assert "<h1>1 open source project</h1>" in card


# ── writing them ─────────────────────────────────────────────────────────


def test_write_wrapped(tmp_path):
    cards = [
        _card("django", "Django", commits=300, before=350),
        _card("old", commits=900, year=2025),
        _card("pandas", "pandas", commits=700, before=500),
    ]
    year = wrapped.write_wrapped(
        str(tmp_path),
        cards,
        GROUPS,
        [("ai.html", "AI-assisted commits")],
        "https://example.com/gallery/",
        True,
        "2.13.0",
        NOW,
    )
    assert year == 2026
    folder = tmp_path / "wrapped"
    assert sorted(os.listdir(folder)) == ["index-card.html", "index.html", "index.json"]

    text = (folder / "index.json").read_text(encoding="utf-8")
    assert text.endswith("}\n")
    data = json.loads(text)
    assert data["generated_by"] == "gitstats 2.13.0"
    assert datetime.datetime.fromisoformat(data["generated_at"]).replace(tzinfo=None) == NOW
    # the cards of the year, the most commits first; the other year's is left out
    assert [entry["id"] for entry in data["repositories"]] == ["pandas", "django"]
    assert data["totals"]["commits"] == 1000

    page = (folder / "index.html").read_text(encoding="utf-8")
    assert "updated 2026-12-05" in page
    assert page.index("../pandas/wrapped.html") < page.index("../django/wrapped.html")
    assert "../old/" not in page
    assert "<h1>2 open source projects</h1>" in (folder / "index-card.html").read_text(
        encoding="utf-8"
    )


def test_write_wrapped_without_a_card_writes_nothing(tmp_path):
    assert wrapped.write_wrapped(str(tmp_path), []) is None
    assert os.listdir(tmp_path) == []


def test_write_wrapped_with_only_the_cards(tmp_path):
    """No ecosystems, other pages, address or version: the page stands."""
    assert wrapped.write_wrapped(str(tmp_path), [_card("a", before=None)]) == 2026
    data = json.loads((tmp_path / "wrapped" / "index.json").read_text(encoding="utf-8"))
    assert data["generated_by"] == "gitstats"
    assert "og:image" not in (tmp_path / "wrapped" / "index.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["../outside.html", "."])
def test_write_stays_in_the_gallery(tmp_path, name):
    with pytest.raises(ValueError, match="outside the gallery"):
        wrapped._write(str(tmp_path / "gallery"), name, "x")
