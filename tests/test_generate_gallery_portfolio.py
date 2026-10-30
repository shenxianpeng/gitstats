"""Tests for scripts/generate_gallery_portfolio.py.

The script lives outside the ``gitstats`` package (it is not installed, only
run directly from a checkout), so it is loaded here by file path.
"""

import importlib.util
import json
import os
import sys

import pytest

_SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts",
    "generate_gallery_portfolio.py",
)


# PyYAML reads the list; it has no wheel yet for every Python the tests run on
needs_yaml = pytest.mark.skipif(
    importlib.util.find_spec("yaml") is None, reason="PyYAML is not installed"
)


@pytest.fixture
def gallery_script():
    spec = importlib.util.spec_from_file_location("generate_gallery_portfolio", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield module
    del sys.modules[spec.name]


def test_load_gallery_summaries_basic(temp_dir, gallery_script):
    repo_dir = os.path.join(temp_dir, "repo")
    os.makedirs(repo_dir)
    with open(os.path.join(repo_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"name": "repo"}, f)

    summaries = gallery_script.load_gallery_summaries(temp_dir)

    assert len(summaries) == 1
    assert summaries[0]["name"] == "repo"
    assert summaries[0]["report_path"] == "repo/index.html"


def test_load_gallery_summaries_skips_dir_without_summary(temp_dir, gallery_script):
    os.makedirs(os.path.join(temp_dir, "empty"))
    assert gallery_script.load_gallery_summaries(temp_dir) == []


def test_load_gallery_summaries_skips_corrupt_json(temp_dir, gallery_script):
    good_dir = os.path.join(temp_dir, "good")
    os.makedirs(good_dir)
    with open(os.path.join(good_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"name": "good"}, f)

    bad_dir = os.path.join(temp_dir, "bad")
    os.makedirs(bad_dir)
    with open(os.path.join(bad_dir, "summary.json"), "w", encoding="utf-8") as f:
        f.write("{not valid json")

    # A corrupt summary.json must be skipped, not abort the whole scan.
    summaries = gallery_script.load_gallery_summaries(temp_dir)
    assert [s["name"] for s in summaries] == ["good"]


def test_load_gallery_summaries_skips_entry_commonpath_cannot_compare(
    temp_dir, gallery_script, monkeypatch
):
    # A symlinked entry whose realpath lands somewhere commonpath() cannot
    # compare to base (e.g. a different drive on Windows) must be skipped,
    # not crash the whole scan: os.path.commonpath() raises ValueError for
    # that case, which the original code did not catch.
    good_dir = os.path.join(temp_dir, "good")
    os.makedirs(good_dir)
    with open(os.path.join(good_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"name": "good"}, f)
    os.makedirs(os.path.join(temp_dir, "outside_link"))

    real_realpath = os.path.realpath

    def fake_realpath(path):
        if "outside_link" in path and path.endswith("summary.json"):
            return r"D:\outside\summary.json"
        return real_realpath(path)

    monkeypatch.setattr(gallery_script.os.path, "realpath", fake_realpath)

    summaries = gallery_script.load_gallery_summaries(temp_dir)
    assert [s["name"] for s in summaries] == ["good"]


def _write_summary(root, entry, **summary):
    os.makedirs(os.path.join(root, entry))
    with open(os.path.join(root, entry, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f)


def test_load_gallery_summaries_names_unnamed_entries(temp_dir, gallery_script):
    _write_summary(temp_dir, "linux", total_commits=5)

    (summary,) = gallery_script.load_gallery_summaries(temp_dir)

    assert summary["name"] == "linux"
    assert summary["report_path"] == "linux/index.html"


def test_main_prints_usage_without_one_argument(gallery_script, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["generate_gallery_portfolio.py"])
    assert gallery_script.main() == 2
    assert "Usage:" in capsys.readouterr().err


def test_main_rejects_a_missing_directory(gallery_script, temp_dir, monkeypatch, capsys):
    missing = os.path.join(temp_dir, "missing")
    monkeypatch.setattr(sys, "argv", ["generate_gallery_portfolio.py", missing])
    assert gallery_script.main() == 1
    assert f"Not a directory: {missing}" in capsys.readouterr().err


def test_main_needs_at_least_one_summary(gallery_script, temp_dir, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["generate_gallery_portfolio.py", temp_dir])
    assert gallery_script.main() == 1
    assert "No summary.json found" in capsys.readouterr().err


def test_main_writes_the_portfolio_page(gallery_script, temp_dir, monkeypatch, capsys):
    _write_summary(temp_dir, "cpython", name="CPython", total_commits=120)
    _write_summary(temp_dir, "git", name="Git", total_commits=80)
    monkeypatch.setattr(sys, "argv", ["generate_gallery_portfolio.py", temp_dir])

    assert gallery_script.main() == 0

    with open(os.path.join(temp_dir, "index.html"), encoding="utf-8") as f:
        page = f.read()
    assert "GitStats Gallery" in page
    # without the list of repositories, no ecosystem pages to lead to
    assert "Ecosystems" not in page
    assert 'href="cpython/index.html"' in page
    assert 'href="git/index.html"' in page
    assert "Portfolio page written for 2 repositories" in capsys.readouterr().out


def test_main_points_to_the_share_cards(gallery_script, temp_dir, monkeypatch):
    from gitstats import load_config

    monkeypatch.setitem(load_config(), "share_card", False)
    _write_summary(temp_dir, "cpython", name="CPython", total_commits=120)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_gallery_portfolio.py",
            temp_dir,
            "--site-url",
            "https://example.com/gallery",
            "--share-card",
        ],
    )
    assert gallery_script.main() == 0
    with open(os.path.join(temp_dir, "index.html"), encoding="utf-8") as f:
        page = f.read()
    # the address gets its slash
    assert '<meta property="og:image" content="https://example.com/gallery/share-card.png">' in page
    assert os.path.exists(os.path.join(temp_dir, "share-card.html"))


def test_main_takes_its_arguments_from_the_caller(gallery_script, temp_dir, capsys):
    _write_summary(temp_dir, "git", name="Git", total_commits=80)
    assert gallery_script.main([temp_dir]) == 0
    assert gallery_script.main([temp_dir, "--no-such-option"]) == 2
    assert "Usage:" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("summaries", "expected"),
    [
        ([{"generated_by": "gitstats 2.10.0"}, {"generated_by": "gitstats 2.10.0"}], "2.10.0"),
        ([{"generated_by": "gitstats 2.10.0"}, {"generated_by": "gitstats 2.9.0"}], ""),
        ([{"generated_by": "something else"}], ""),
        ([{}], ""),
    ],
)
def test_reports_version(gallery_script, summaries, expected):
    assert gallery_script.reports_version(summaries) == expected


def _page_version(temp_dir):
    with open(os.path.join(temp_dir, "index.html"), encoding="utf-8") as f:
        page = f.read()
    return page.split("generated by gitstats ", 1)[1].split(" on ", 1)[0]


def test_from_a_checkout_the_pages_say_the_reports_version(gallery_script, temp_dir, monkeypatch):
    _write_summary(temp_dir, "git", name="Git", total_commits=80, generated_by="gitstats 2.10.0")
    _write_summary(temp_dir, "nginx", name="nginx", total_commits=8, generated_by="gitstats 2.10.0")
    monkeypatch.setattr(gallery_script, "get_version", lambda: "dev")
    assert gallery_script.main([temp_dir]) == 0
    assert _page_version(temp_dir) == "2.10.0"


def test_from_a_checkout_reports_of_several_versions_leave_it_dev(
    gallery_script, temp_dir, monkeypatch
):
    _write_summary(temp_dir, "git", name="Git", total_commits=80, generated_by="gitstats 2.10.0")
    _write_summary(temp_dir, "nginx", name="nginx", total_commits=8, generated_by="gitstats 2.9.0")
    monkeypatch.setattr(gallery_script, "get_version", lambda: "dev")
    assert gallery_script.main([temp_dir]) == 0
    assert _page_version(temp_dir) == "dev"


def test_installed_the_pages_say_its_own_version(gallery_script, temp_dir, monkeypatch):
    _write_summary(temp_dir, "git", name="Git", total_commits=80, generated_by="gitstats 2.9.0")
    monkeypatch.setattr(gallery_script, "get_version", lambda: "2.10.0")
    assert gallery_script.main([temp_dir]) == 0
    assert _page_version(temp_dir) == "2.10.0"


# ── --repos: groups, and the repositories without a report ──────────────


_REPOS_YML = """\
groups:
  - id: python
    name: Python
    repos:
      - { id: django, name: "Django", url: "django/django" }
      - { id: flask, name: "Flask", url: "pallets/flask" }
  - id: cncf
    name: CNCF graduated
    repos:
      - { id: etcd, name: "etcd", url: "etcd-io/etcd" }
"""

_REPORT_PAGE = (
    "<!DOCTYPE html><html><body><h1>{name}</h1>"
    '<div class="footer">Generated by gitstats</div>\n</body></html>'
)


def _write_report(root, entry, badge=False, **summary):
    _write_summary(root, entry, **summary)
    for page in ("index.html", "authors.html", "share-card.html"):
        with open(os.path.join(root, entry, page), "w", encoding="utf-8") as f:
            f.write(_REPORT_PAGE.format(name=entry))
    if badge:
        os.makedirs(os.path.join(root, entry, "badges"))
        with open(os.path.join(root, entry, "badges", "ai-assisted.svg"), "w") as f:
            f.write("<svg/>")


def _gallery(temp_dir, monkeypatch):
    # the list is read from under the current directory, as in the checkout
    monkeypatch.chdir(temp_dir)
    gallery = os.path.join(temp_dir, "gallery")
    os.makedirs(gallery)
    repos = os.path.join(temp_dir, "repos.yml")
    with open(repos, "w", encoding="utf-8") as f:
        f.write(_REPOS_YML)
    return gallery, repos


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


@needs_yaml
def test_repos_group_the_reports(gallery_script, temp_dir, capsys, monkeypatch):
    gallery, repos = _gallery(temp_dir, monkeypatch)
    _write_report(gallery, "django", name="Django", total_commits=300)
    _write_report(gallery, "etcd", name="etcd", total_commits=200)
    # not in the list: left out
    _write_report(gallery, "removed", name="Removed", total_commits=1)

    assert gallery_script.main([gallery, "--repos", repos]) == 0

    page = _read(gallery, "index.html")
    assert 'data-group="python" aria-pressed="false">Python <span>1</span>' in page
    assert '<tr data-group="cncf"><td><a href="etcd/index.html">etcd</a></td>' in page
    assert "removed/index.html" not in page
    # the repository without a report is listed, and the others are published
    assert "<h2>Failed repositories</h2>" in page
    assert "<td>Flask</td><td>No report: generating it for pallets/flask failed</td>" in page
    captured = capsys.readouterr()
    assert "Flask: No report" in captured.err
    assert "Portfolio page written for 2 repositories" in captured.out
    assert "(1 without a report)" in captured.out


@needs_yaml
def test_repos_with_no_report_at_all(gallery_script, temp_dir, capsys, monkeypatch):
    gallery, repos = _gallery(temp_dir, monkeypatch)
    assert gallery_script.main([gallery, "--repos", repos]) == 1
    assert "No summary.json found" in capsys.readouterr().err


@needs_yaml
def test_repos_that_cannot_be_read(gallery_script, temp_dir, capsys, monkeypatch):
    gallery, _ = _gallery(temp_dir, monkeypatch)
    bad = os.path.join(temp_dir, "bad.yml")
    with open(bad, "w", encoding="utf-8") as f:
        f.write("groups: []\n")
    assert gallery_script.main([gallery, "--repos", bad]) == 1
    assert "no repositories" in capsys.readouterr().err


def test_load_gallery_summaries_skips_what_is_not_an_object(temp_dir, gallery_script, capsys):
    _write_summary(temp_dir, "good", name="good")
    os.makedirs(os.path.join(temp_dir, "list"))
    with open(os.path.join(temp_dir, "list", "summary.json"), "w", encoding="utf-8") as f:
        f.write("[1, 2]")
    assert [s["name"] for s in gallery_script.load_gallery_summaries(temp_dir)] == ["good"]
    assert "not an object" in capsys.readouterr().err


def test_load_gallery_summaries_of_some_ids_in_their_order(temp_dir, gallery_script):
    for entry in ("a", "b", "c"):
        _write_summary(temp_dir, entry, name=entry)
    summaries = gallery_script.load_gallery_summaries(temp_dir, ["c", "missing", "a"])
    assert [s["name"] for s in summaries] == ["c", "a"]


# ── the note under each report ───────────────────────────────────────────


@needs_yaml
def test_every_report_page_says_how_to_make_it(gallery_script, temp_dir, monkeypatch):
    gallery, repos = _gallery(temp_dir, monkeypatch)
    _write_report(gallery, "django", badge=True, name="Django", total_commits=300)
    _write_report(gallery, "etcd", name="etcd", total_commits=200)

    assert (
        gallery_script.main(
            [gallery, "--repos", repos, "--site-url", "https://example.com/gallery"]
        )
        == 0
    )

    for entry in ("django", "etcd"):
        for page in ("index.html", "authors.html"):
            text = _read(gallery, entry, page)
            assert text.count(gallery_script.NOTE_MARK) == 1
            # before the footer
            assert text.index('class="gallery-note"') < text.index('<div class="footer">')
            assert "Generate this report for your own repository" in text
            assert 'href="https://github.com/shenxianpeng/gitstats-action"' in text
            assert "uses: shenxianpeng/gitstats-action@v1" in text
            assert 'href="../index.html">All Gallery reports</a>' in text
        # the share card is an image, not a page to read
        assert gallery_script.NOTE_MARK not in _read(gallery, entry, "share-card.html")

    # the badge, on the overview of a report that has one
    overview = _read(gallery, "django", "index.html")
    assert (
        "[![AI-assisted commits: Django](https://example.com/gallery/django/"
        "badges/ai-assisted.svg)](https://example.com/gallery/django/)"
    ) in overview
    assert '<img src="badges/ai-assisted.svg" alt="AI-assisted commits">' in overview
    assert "navigator.clipboard" in overview
    assert "Badge for your README" not in _read(gallery, "django", "authors.html")
    assert "Badge for your README" not in _read(gallery, "etcd", "index.html")

    # and the gallery's own pages ask for more projects
    index = _read(gallery, "index.html")
    assert "Add your project to the Gallery" in index
    assert "issues/new?template=gallery.yml" in index


@needs_yaml
def test_the_note_is_added_once(gallery_script, temp_dir, monkeypatch):
    gallery, repos = _gallery(temp_dir, monkeypatch)
    _write_report(gallery, "django", badge=True, name="Django", total_commits=300)
    assert gallery_script.main([gallery, "--repos", repos]) == 0
    first = _read(gallery, "django", "index.html")
    # a report kept from an earlier build already has it
    assert gallery_script.main([gallery, "--repos", repos]) == 0
    assert _read(gallery, "django", "index.html") == first
    # without an address, the badge's Markdown points next to the report
    assert "[![AI-assisted commits: Django](badges/ai-assisted.svg)](index.html)" in first


def test_names_in_the_note_are_escaped(gallery_script):
    note = gallery_script.report_note("x", "<b>&</b>", "", badge=True)
    assert "<b>&</b>" not in note
    assert "&lt;b&gt;&amp;&lt;/b&gt;" in note


@pytest.mark.parametrize(
    ("text", "added", "expected"),
    [
        # at the end of the content, inside <main>
        (
            '<main id="main"><p>a</p></main>\n<footer class="footer">f</footer></body>',
            True,
            "<p>a</p>NOTE</main>",
        ),
        # a page made before there was a <main>: before its footer
        ('<p>a</p><div class="footer">f</div></body>', True, '<p>a</p>NOTE<div class="footer">'),
        ("<p>a</p></body>", True, "<p>a</p>NOTE</body>"),
        ("<p>a</p>", False, "<p>a</p>"),
    ],
)
def test_add_note(gallery_script, temp_dir, text, added, expected):
    page = os.path.join(temp_dir, "page.html")
    with open(page, "w", encoding="utf-8") as f:
        f.write(text)
    note = gallery_script.NOTE_MARK + "NOTE"
    assert gallery_script.add_note(temp_dir, page, note) is added
    assert expected.replace("NOTE", note) in _read(page)
    assert gallery_script.add_note(temp_dir, page, note) is False  # once at most
    missing = os.path.join(temp_dir, "missing.html")
    assert gallery_script.add_note(temp_dir, missing, note) is False


def test_add_note_stays_in_its_directory(gallery_script, temp_dir):
    inside = os.path.join(temp_dir, "inside")
    os.makedirs(inside)
    outside = os.path.join(temp_dir, "outside.html")
    with open(outside, "w", encoding="utf-8") as f:
        f.write("<p>a</p></body>")
    assert gallery_script.add_note(inside, outside, "NOTE") is False
    assert gallery_script.add_note(inside, os.path.join(inside, "..", "outside.html"), "N") is False
    assert _read(outside) == "<p>a</p></body>"


def test_add_note_skips_a_page_commonpath_cannot_compare(gallery_script, temp_dir, monkeypatch):
    # A page whose real path lands somewhere commonpath() cannot compare to
    # the gallery (another drive on Windows) is not inside it:
    # os.path.commonpath() raises ValueError for that case.
    page = os.path.join(temp_dir, "page.html")
    with open(page, "w", encoding="utf-8") as f:
        f.write("<p>a</p></body>")
    real_realpath = os.path.realpath

    def fake_realpath(path):
        if path.endswith("page.html"):
            return r"D:\outside\page.html"
        return real_realpath(path)

    monkeypatch.setattr(gallery_script.os.path, "realpath", fake_realpath)
    assert gallery_script.add_note(temp_dir, page, "NOTE") is False
    assert _read(page) == "<p>a</p></body>"


def test_add_report_notes_skips_a_report_without_a_folder(gallery_script, temp_dir):
    gallery = os.path.join(temp_dir, "gallery")
    os.makedirs(gallery)
    summaries = [
        {"report_path": "missing/index.html", "name": "no folder"},
        {"report_path": "../index.html", "name": "outside the gallery"},
        {"report_path": "./index.html", "name": "the gallery itself"},
    ]
    assert gallery_script.add_report_notes(gallery, summaries, "") == 0


# ── the ecosystem pages ──────────────────────────────────────────────────


@needs_yaml
def test_repos_write_the_ecosystem_pages_and_link_them(gallery_script, temp_dir, monkeypatch):
    gallery, repos = _gallery(temp_dir, monkeypatch)
    _write_report(gallery, "django", name="Django", total_commits=300)
    _write_report(gallery, "etcd", name="etcd", total_commits=200)

    site = "https://example.com/gallery/"
    assert gallery_script.main([gallery, "--repos", repos, "--site-url", site]) == 0

    for page in ("python.html", "python.json", "cncf.html", "index.html", "index.json"):
        assert os.path.isfile(os.path.join(gallery, "ecosystems", page))
    assert "<loc>https://example.com/gallery/ecosystems/cncf.html</loc>" in _read(
        gallery, "sitemap.xml"
    )
    # the gallery's pages link to every ranking, and each report to its own
    index = _read(gallery, "index.html")
    assert '<a href="ecosystems/index.html">Ecosystems ranked by AI-assisted commits' in index
    assert '<a href="ecosystems/python.html">Python</a>' in index
    # and their nav bars, as the ecosystem pages' own do
    assert '<li><a href="ecosystems/index.html">Ecosystems</a></li>' in index
    assert (
        '<a href="../ecosystems/python.html">How Django ranks among Python projects by '
        "AI-assisted commits &rarr;</a>"
    ) in _read(gallery, "django", "authors.html")


def test_notes_without_groups_have_no_ranking_links(gallery_script):
    assert "ecosystems/" not in gallery_script.gallery_note()
    assert "ecosystems/" not in gallery_script.report_note("x", "X", "", badge=False)


_FIVE_REPOS_YML = """\
groups:
  - id: python
    name: Python
    title: Python open source projects
    repos:
      - { id: django, name: "Django", url: "django/django" }
      - { id: flask, name: "Flask", url: "pallets/flask" }
      - { id: pandas, name: "pandas", url: "pandas-dev/pandas" }
      - { id: numpy, name: "NumPy", url: "numpy/numpy" }
      - { id: pip, name: "pip", url: "pypa/pip" }
"""


@needs_yaml
def test_comparison_pages_are_linked_and_listed(gallery_script, temp_dir, monkeypatch):
    gallery, repos = _gallery(temp_dir, monkeypatch)
    with open(repos, "w", encoding="utf-8") as f:
        f.write(_FIVE_REPOS_YML)
    for n, entry in enumerate(("django", "flask", "pandas", "numpy", "pip")):
        _write_report(gallery, entry, name=entry, total_commits=100, commits_last_12mo=10 * n)
    site = "https://example.com/gallery/"
    assert gallery_script.main([gallery, "--repos", repos, "--site-url", site]) == 0

    # each report links to its comparison, which says so in the group's words
    assert (
        '<a href="compare.html">How pandas compares with other Python open source projects '
        "&rarr;</a>"
    ) in _read(gallery, "pandas", "authors.html")
    assert (
        "pip had more commits in the last 12 months than any other of the 5 Python open "
        "source projects." in _read(gallery, "pip", "compare.html")
    )
    # the comparison and its card get no note of their own
    assert gallery_script.NOTE_MARK not in _read(gallery, "pandas", "compare.html")
    assert gallery_script.NOTE_MARK not in _read(gallery, "pandas", "compare-card.html")
    assert f"<loc>{site}pandas/compare.html</loc>" in _read(gallery, "sitemap.xml")
    # each summary knows its repository: its own domain is not an employer
    data = json.loads(_read(gallery, "compare.json"))
    assert {r["name"] for r in data["repositories"]} == {
        "django",
        "flask",
        "pandas",
        "numpy",
        "pip",
    }


def test_note_links_to_the_comparison(gallery_script):
    note = gallery_script.report_note("x", "X", "", badge=False, compared=True)
    assert ('<a href="compare.html">How X compares with the Gallery&#x27;s other projects') in note
