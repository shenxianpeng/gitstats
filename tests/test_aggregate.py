"""Tests for the multi-repository aggregation module."""

import datetime
import json
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from gitstats.aggregate import (
    AggregateReportCreator,
    _slugify_repo,
    ai_assisted_summary,
    compute_repo_summary,
    last_quarters,
    load_repo_summaries,
    write_repo_summary,
)

# ── _slugify_repo ────────────────────────────────────────────────────────


class TestSlugifyRepo:
    def test_basename(self):
        assert _slugify_repo("/home/user/projects/myrepo") == "myrepo"

    def test_trailing_separator(self):
        assert _slugify_repo("/home/user/projects/myrepo/") == "myrepo"

    def test_trailing_dot_git(self):
        assert _slugify_repo("/srv/git/myrepo.git") == "myrepo"

    def test_unsafe_characters_replaced(self):
        assert _slugify_repo("/tmp/my repo!") == "my-repo-"

    def test_relative_path(self):
        assert _slugify_repo("some-repo") == "some-repo"

    def test_root_rejected(self):
        with pytest.raises(ValueError):
            _slugify_repo("/")


# ── compute_repo_summary ─────────────────────────────────────────────────


class TestComputeRepoSummary:
    def test_basic_fields(self, mock_data_collector):
        summary = compute_repo_summary(mock_data_collector, "repo/index.html")

        assert summary["schema_version"] == 1
        assert summary["report_path"] == "repo/index.html"
        assert summary["name"] == mock_data_collector.project_name
        assert summary["total_commits"] == mock_data_collector.total_commits
        assert summary["total_files"] == mock_data_collector.total_files
        assert summary["total_lines"] == mock_data_collector.total_lines
        assert summary["total_tags"] == len(mock_data_collector.tags)
        assert summary["first_commit"]
        assert summary["last_commit"]
        assert summary["age_days"] >= 1

    def test_bots_excluded(self, mock_data_collector):
        mock_data_collector.authors = {
            "Alice": {"commits": 30, "last_commit_stamp": 1700000000},
            "dependabot[bot]": {"commits": 99, "last_commit_stamp": 1700000000},
        }
        summary = compute_repo_summary(mock_data_collector, "repo/index.html")

        assert summary["total_authors"] == 1
        assert "dependabot[bot]" not in summary["author_commits"]
        assert [a["name"] for a in summary["top_authors"]] == ["Alice"]

    def test_active_authors_window(self, mock_data_collector):
        import time

        now = time.time()
        mock_data_collector.authors = {
            "Fresh": {"commits": 5, "last_commit_stamp": now - 86400},
            "Stale": {"commits": 5, "last_commit_stamp": now - 400 * 86400},
        }
        summary = compute_repo_summary(mock_data_collector, "repo/index.html")

        assert summary["active_authors_12mo"] == 1

    def test_era_label_present(self, mock_data_collector):
        mock_data_collector.commits_by_year = {2021: 10, 2022: 40, 2023: 50}
        summary = compute_repo_summary(mock_data_collector, "repo/index.html")

        assert summary["era"] != ""
        assert list(summary["commits_by_year"]) == ["2021", "2022", "2023"]

    def test_top_authors_sorted_and_capped(self, mock_data_collector):
        mock_data_collector.authors = {
            f"author{i}": {"commits": i, "last_commit_stamp": 0} for i in range(1, 8)
        }
        summary = compute_repo_summary(mock_data_collector, "repo/index.html")

        assert len(summary["top_authors"]) == 5
        assert summary["top_authors"][0] == {"name": "author7", "commits": 7}


# ── write_repo_summary / load_repo_summaries ─────────────────────────────


class TestSummaryIO:
    def test_roundtrip(self, temp_dir):
        repo_dir = os.path.join(temp_dir, "repo")
        os.makedirs(repo_dir)
        write_repo_summary({"schema_version": 1, "name": "repo"}, repo_dir)

        with open(os.path.join(repo_dir, "summary.json"), encoding="utf-8") as f:
            assert json.load(f)["name"] == "repo"

        summaries = load_repo_summaries(temp_dir)
        assert len(summaries) == 1
        assert summaries[0]["name"] == "repo"

    def test_load_skips_dirs_without_summary(self, temp_dir):
        os.makedirs(os.path.join(temp_dir, "empty"))
        assert load_repo_summaries(temp_dir) == []

    def test_load_missing_root(self, temp_dir):
        assert load_repo_summaries(os.path.join(temp_dir, "nope")) == []

    def test_load_skips_entry_that_commonpath_cannot_compare(self, temp_dir, monkeypatch):
        # A symlinked entry whose realpath lands on a different drive (or any
        # path commonpath() cannot compare to base) must be skipped, not
        # crash the whole call: os.path.commonpath() raises ValueError for
        # that case, which is not an OSError.
        repo_dir = os.path.join(temp_dir, "good")
        os.makedirs(repo_dir)
        write_repo_summary({"schema_version": 1, "name": "good"}, repo_dir)
        os.makedirs(os.path.join(temp_dir, "outside_link"))

        real_realpath = os.path.realpath

        def fake_realpath(path):
            if "outside_link" in path and path.endswith("summary.json"):
                return r"D:\outside\summary.json"
            return real_realpath(path)

        monkeypatch.setattr(os.path, "realpath", fake_realpath)

        summaries = load_repo_summaries(temp_dir)
        assert [s["name"] for s in summaries] == ["good"]


# ── AggregateReportCreator ───────────────────────────────────────────────


def _summary(name, commits, authors_map, **overrides):
    base = {
        "schema_version": 1,
        "name": name,
        "report_path": f"{name}/index.html",
        "first_commit": "2020-01-01 00:00:00",
        "last_commit": "2023-06-01 00:00:00",
        "age_days": 1200,
        "active_days": 300,
        "total_commits": commits,
        "total_authors": len(authors_map),
        "active_authors_12mo": 1,
        "commits_last_12mo": 10,
        "total_files": 10,
        "total_lines": 1000,
        "lines_added": 1500,
        "lines_removed": 500,
        "total_tags": 2,
        "era": "steady",
        "top_authors": [],
        "author_commits": authors_map,
        "commits_by_year": {},
    }
    base.update(overrides)
    return base


class TestAggregateReportCreator:
    def _render(self, temp_dir, summaries, failures=()):
        AggregateReportCreator().create(summaries, list(failures), temp_dir)
        with open(os.path.join(temp_dir, "index.html"), encoding="utf-8") as f:
            return f.read()

    def test_page_structure(self, temp_dir):
        html = self._render(
            temp_dir,
            [
                _summary("alpha", 100, {"Alice": 60, "Bob": 40}),
                _summary("beta", 50, {"Alice": 50}, era="dormant"),
            ],
        )

        assert '<table class="sortable" id="portfolio">' in html
        assert 'href="alpha/index.html"' in html
        assert 'href="beta/index.html"' in html
        assert "history-era-steady" in html
        assert "history-era-dormant" in html
        # Totals as stat tiles; distinct authors = union, not the naive per-repo sum
        assert (
            '<dt>Repositories</dt><dd class="stat-value">2</dd>'
            '<dd class="stat-note">2 active in the last 12 months</dd>'
        ) in html
        assert (
            '<dt>Commits</dt><dd class="stat-value">150</dd>'
            '<dd class="stat-note">20 in the last 12 months</dd>'
        ) in html
        assert '<dt>Authors</dt><dd class="stat-value">2</dd>' in html
        assert '<dt>Lines of Code</dt><dd class="stat-value">2,000</dd>' in html
        assert "<h2>Totals</h2>" not in html
        # Repo table: Since column (first-commit year) replaces Age (days)
        assert "<th>Since</th>" in html
        assert "Age (days)" not in html
        assert "<td>2020</td>" in html
        assert '<th class="num">Lines of Code</th>' in html
        # Sorted by commits: alpha row before beta row
        assert html.index('href="alpha/index.html"') < html.index('href="beta/index.html"')

    def test_shares_report_theme_and_nav(self, temp_dir):
        html = self._render(temp_dir, [_summary("alpha", 10, {"Alice": 10})])

        assert "prefers-color-scheme: dark" in html
        assert 'class="icon-sun"' in html
        assert "\U0001f319" not in html
        assert html.count('aria-current="page"') == 1

    def test_tables_scroll_in_their_own_box(self, temp_dir):
        html = self._render(
            temp_dir,
            [_summary("alpha", 10, {"Alice": 10})],
            failures=[{"name": "bad", "path": "/x", "error": "boom"}],
        )
        # the repository and failure tables (totals are stat tiles)
        assert html.count("<table") == 2
        assert html.count('<div class="table-scroll"><table') == 2
        assert html.count("</table></div>") == 2

    def test_thousands_separators(self, temp_dir):
        html = self._render(
            temp_dir,
            [
                _summary(
                    "mega",
                    1234567,
                    {"A": 1234567},
                    total_lines=44025623,
                    commits_last_12mo=78432,
                )
            ],
        )

        assert '<dt>Commits</dt><dd class="stat-value">1,234,567</dd>' in html
        assert '<dd class="stat-note">78,432 in the last 12 months</dd>' in html
        assert '<dt>Lines of Code</dt><dd class="stat-value">44,025,623</dd>' in html
        # Repository table: numeric columns are right-aligned
        assert '<td class="num">1,234,567</td>' in html
        assert '<td class="num">44,025,623</td>' in html

    def test_inactive_repo_counted(self, temp_dir):
        html = self._render(
            temp_dir,
            [
                _summary("alpha", 100, {"A": 100}),
                _summary("stale", 50, {"B": 50}, commits_last_12mo=0),
            ],
        )

        assert '<dd class="stat-note">1 active in the last 12 months</dd>' in html

    def test_assets_copied(self, temp_dir):
        self._render(temp_dir, [_summary("alpha", 1, {"A": 1})])
        assert os.path.exists(os.path.join(temp_dir, "sortable.js"))
        assert os.path.exists(os.path.join(temp_dir, "gitstats.css"))
        assert not os.path.exists(os.path.join(temp_dir, "chart.umd.min.js"))

    def test_failures_section_escaped(self, temp_dir):
        html = self._render(
            temp_dir,
            [_summary("alpha", 1, {"A": 1})],
            failures=[{"name": "bad", "path": "/x", "error": "<script>boom</script>"}],
        )

        assert "Failed repositories" in html
        assert "&lt;script&gt;boom&lt;/script&gt;" in html
        assert "<script>boom</script>" not in html

    def test_no_failures_section_when_empty(self, temp_dir):
        html = self._render(temp_dir, [_summary("alpha", 1, {"A": 1})])
        assert "Failed repositories" not in html

    def test_repo_name_escaped(self, temp_dir):
        html = self._render(temp_dir, [_summary("a<b>", 1, {"A": 1})])
        assert "a&lt;b&gt;" in html


# ── reading summaries and writing the page, unusual paths ────────────────


def test_load_repo_summaries_from_a_missing_directory(tmp_path):
    assert load_repo_summaries(str(tmp_path / "missing")) == []


def test_load_repo_summaries_skips_entries_it_cannot_place(tmp_path):
    """A path that can't be compared with the root (another drive on Windows) is skipped."""
    (tmp_path / "repo").mkdir()
    (tmp_path / "repo" / "summary.json").write_text('{"name": "repo"}', encoding="utf-8")
    with patch("gitstats.aggregate.os.path.commonpath", side_effect=ValueError("different drives")):
        assert load_repo_summaries(str(tmp_path)) == []


def test_compute_repo_summary_without_yearly_commits():
    class Empty:
        project_name = "empty"

    summary = compute_repo_summary(Empty(), "index.html")
    assert summary["era"] == ""
    assert summary["commits_by_year"] == {}
    assert summary["total_commits"] == 0


def test_copy_assets_skips_a_missing_stylesheet(tmp_path):
    import gitstats

    gitstats._config = dict(gitstats.DEFAULT_CONFIG, style="missing.css")
    AggregateReportCreator._copy_assets(str(tmp_path))
    assert (tmp_path / "sortable.js").exists()
    assert not (tmp_path / "missing.css").exists()


def test_copy_assets_refuses_to_write_outside_the_output(tmp_path):
    with (
        patch("gitstats.aggregate.os.path.commonpath", return_value=str(tmp_path / "elsewhere")),
        pytest.raises(ValueError, match="Refusing to write outside report directory"),
    ):
        AggregateReportCreator._copy_assets(str(tmp_path))


def test_portfolio_file_refuses_to_open_outside_the_output(tmp_path):
    with (
        patch("gitstats.aggregate.os.path.commonpath", return_value=str(tmp_path / "elsewhere")),
        pytest.raises(ValueError, match="Refusing to write outside report directory"),
    ):
        AggregateReportCreator._open_portfolio_file(str(tmp_path))
    assert not (tmp_path / "index.html").exists()


def test_load_repo_summaries_skips_unreadable_files(tmp_path, caplog):
    (tmp_path / "good").mkdir()
    (tmp_path / "good" / "summary.json").write_text('{"name": "good"}', encoding="utf-8")
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "summary.json").write_text("{not json", encoding="utf-8")

    assert load_repo_summaries(str(tmp_path)) == [{"name": "good"}]
    assert "Skipping unreadable summary" in caplog.text


def test_write_repo_summary_refuses_to_write_outside_the_report(tmp_path):
    with (
        patch("gitstats.aggregate.os.path.commonpath", return_value=str(tmp_path / "elsewhere")),
        pytest.raises(ValueError, match="Refusing to write outside report directory"),
    ):
        write_repo_summary({"name": "x"}, str(tmp_path))
    assert not (tmp_path / "summary.json").exists()


# ── AI-assisted commits ──────────────────────────────────────────────────


class TestAiAssistedSummary:
    def test_keeps_the_last_two_years_month_by_month(self):
        data = SimpleNamespace(
            ai_assisted_commits=5,
            ai_assisted_authored=1,
            ai_assisted_by_month={"2026-09": 3, "2026-01": 1, "2023-05": 1},
            commits_by_month={"2026-09": 30, "2026-01": 10, "2024-11": 7, "2023-05": 9},
            ai_assistants={
                "Claude": {"commits": 2},
                "GitHub Copilot": {"commits": 3},
                "Aider": {"commits": 2},
            },
        )
        ai = ai_assisted_summary(data, datetime.datetime(2026, 10, 14))
        assert list(ai["by_month"])[0] == "2024-11"
        assert list(ai["by_month"])[-1] == "2026-10"
        assert len(ai["by_month"]) == len(ai["commits_by_month"]) == 24
        assert (ai["by_month"]["2026-09"], ai["commits_by_month"]["2026-09"]) == (3, 30)
        assert (ai["by_month"]["2024-11"], ai["commits_by_month"]["2024-11"]) == (0, 7)
        assert "2023-05" not in ai["by_month"]
        assert (ai["commits"], ai["authored"]) == (5, 1)
        # the most named first, then by name
        assert list(ai["assistants"].items()) == [
            ("GitHub Copilot", 3),
            ("Aider", 2),
            ("Claude", 2),
        ]

    def test_none_for_data_collected_before_they_were_counted(self, mock_data_collector):
        now = datetime.datetime.now()
        assert ai_assisted_summary(SimpleNamespace(commits_by_month={}), now) is None
        # a Mock has every attribute, and none of them is a count
        assert compute_repo_summary(mock_data_collector, "index.html")["ai_assisted"] is None

    def test_in_the_summary_of_a_repository(self, mock_data_collector):
        mock_data_collector.ai_assisted_commits = 2
        mock_data_collector.ai_assisted_authored = 0
        mock_data_collector.ai_assisted_by_month = {"2023-03": 2}
        mock_data_collector.ai_assistants = {"Claude": {"commits": 2}}
        summary = compute_repo_summary(mock_data_collector, "alpha/index.html")
        assert summary["ai_assisted"]["commits"] == 2
        assert summary["ai_assisted"]["assistants"] == {"Claude": 2}
        # it is written as JSON with the rest
        assert json.loads(json.dumps(summary))["ai_assisted"]["commits"] == 2


@pytest.mark.parametrize(
    "now, labels, last",
    [
        (
            datetime.datetime(2026, 10, 14),
            ["Oct\u2013Dec 2025", "Jan\u2013Mar 2026", "Apr\u2013Jun 2026", "Jul\u2013Sep 2026"],
            ["2026-07", "2026-08", "2026-09"],
        ),
        (
            datetime.datetime(2026, 1, 1),
            ["Jan\u2013Mar 2025", "Apr\u2013Jun 2025", "Jul\u2013Sep 2025", "Oct\u2013Dec 2025"],
            ["2025-10", "2025-11", "2025-12"],
        ),
        (
            datetime.datetime(2026, 3, 31),
            ["Jan\u2013Mar 2025", "Apr\u2013Jun 2025", "Jul\u2013Sep 2025", "Oct\u2013Dec 2025"],
            ["2025-10", "2025-11", "2025-12"],
        ),
        (
            datetime.datetime(2026, 4, 1),
            ["Apr\u2013Jun 2025", "Jul\u2013Sep 2025", "Oct\u2013Dec 2025", "Jan\u2013Mar 2026"],
            ["2026-01", "2026-02", "2026-03"],
        ),
    ],
)
def test_last_quarters_are_the_complete_ones(now, labels, last):
    quarters = last_quarters(now)
    assert [label for label, _ in quarters] == labels
    assert quarters[-1][1] == last


def _ai(by_quarter, assistants):
    """An ai_assisted block for the last four quarters: (commits that name an
    assistant, all commits) in each, put in the quarter's first month."""
    by_month, all_by_month = {}, {}
    for (_, months), (part, whole) in zip(last_quarters(datetime.datetime.now()), by_quarter):
        for month in months:
            by_month[month] = all_by_month[month] = 0
        by_month[months[0]], all_by_month[months[0]] = part, whole
    return {
        "commits": sum(part for part, _ in by_quarter),
        "authored": 0,
        "assistants": assistants,
        "by_month": by_month,
        "commits_by_month": all_by_month,
    }


class TestAiAssistedPage:
    @staticmethod
    def _render(temp_dir, summaries):
        AggregateReportCreator().create(summaries, [], temp_dir, title="GitStats Gallery")
        pages = {}
        for name in ("index.html", "ai.html"):
            path = os.path.join(temp_dir, name)
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    pages[name] = f.read()
        return pages

    def test_no_page_when_no_summary_counts_them(self, temp_dir):
        pages = self._render(temp_dir, [_summary("alpha", 10, {"Alice": 10})])
        assert list(pages) == ["index.html"]
        assert "ai.html" not in pages["index.html"]

    def test_repositories_quarter_by_quarter(self, temp_dir):
        pages = self._render(
            temp_dir,
            [
                _summary(
                    "alpha",
                    100,
                    {},
                    ai_assisted=_ai([(0, 10), (1, 10), (2, 10), (5, 10)], {"Claude": 8}),
                ),
                _summary("beta", 100, {}, ai_assisted=_ai([(0, 10)] * 4, {})),
                _summary(
                    "gamma",
                    100,
                    {},
                    ai_assisted=_ai(
                        [(3, 10), (3, 10), (6, 20), (6, 10)], {"GitHub Copilot": 10, "Claude": 8}
                    ),
                ),
                # summarised by a gitstats that did not count them
                _summary("old", 100, {}),
            ],
        )
        index, page = pages["index.html"], pages["ai.html"]
        # reached from the portfolio page, by its navigation and a link under the totals
        assert 'href="ai.html"' in index
        assert "AI-assisted commits, quarter by quarter" in index
        assert page.count('aria-current="page"') == 1
        assert "<h1>AI-assisted commits</h1>" in page
        assert "These are lower bounds." in page

        # the largest share in the last quarter first: gamma 60%, alpha 50%, beta 0, old unknown
        order = [page.index(f">{name}</a>") for name in ("gamma", "alpha", "beta", "old")]
        assert order == sorted(order)
        # each to its Authors page, at the section when the report has one
        assert 'href="gamma/authors.html#ai-assisted_commits"' in page
        assert 'href="beta/authors.html"' in page
        # a cell: the share, shaded, over the two counts
        assert '--share-strength: 75%">60.0%<small>6 / 10</small></td>' in page
        assert '--share-strength: 0%">0<small>0 / 10</small></td>' in page
        assert page.count('<td class="share">&ndash;</td>') == 4
        # the assistants named most in each repository
        assert "<td>GitHub Copilot, Claude</td>" in page
        assert "<td>&ndash;</td>" in page

        last_quarter = last_quarters(datetime.datetime.now())[-1][0]
        assert (
            '<dt>Repositories</dt><dd class="stat-value">2 of 4</dd>'
            '<dd class="stat-note">name an assistant in the last four quarters</dd>'
        ) in page
        assert (
            '<dt>Largest Share</dt><dd class="stat-value">60.0%</dd>'
            f'<dd class="stat-note">gamma, {last_quarter}</dd>'
        ) in page
        assert (
            '<dt>Named Most Widely</dt><dd class="stat-value">Claude</dd>'
            '<dd class="stat-note">in 2 of 4 repositories</dd>'
        ) in page
        assert "<summary>What is counted</summary>" in page
        # on a narrow screen the table starts at its last quarter
        assert "box.scrollLeft = last.offsetLeft + last.offsetWidth - box.clientWidth" in page

    def test_a_summary_that_does_not_reach_back_that_far(self, temp_dir):
        old = _ai([(1, 10)] * 4, {"Claude": 4})
        # made long ago: the last four quarters are not among its months
        old["by_month"] = {"2001-01": 1}
        old["commits_by_month"] = {"2001-01": 10}
        # and its report is elsewhere: linked as it is
        alpha = _summary("alpha", 10, {}, ai_assisted=old, report_path="https://example.com/alpha/")
        page = self._render(temp_dir, [alpha])["ai.html"]
        assert 'href="https://example.com/alpha/"' in page
        assert page.count('<td class="share">&ndash;</td>') == 4
        assert '<dd class="stat-value">0 of 1</dd>' in page
        assert "Largest Share" not in page

    def test_a_quarter_without_commits_has_no_share(self, temp_dir):
        quiet = _ai([(5, 10), (2, 4), (0, 0), (0, 0)], {"Aider": 7})
        page = self._render(temp_dir, [_summary("alpha", 14, {}, ai_assisted=quiet)])["ai.html"]
        assert page.count('<td class="share"><small>no commits</small></td>') == 2
        assert "0 / 0" not in page
        # and it names an assistant in the last four quarters all the same
        assert '<dd class="stat-value">1 of 1</dd>' in page
        assert "Largest Share" not in page

    def test_names_are_escaped(self, temp_dir):
        page = self._render(
            temp_dir,
            [
                _summary(
                    "<b>alpha</b>",
                    10,
                    {},
                    ai_assisted=_ai([(0, 10), (0, 10), (0, 10), (1, 10)], {"<i>bot</i>": 1}),
                )
            ],
        )["ai.html"]
        assert "<b>alpha</b>" not in page
        assert "&lt;b&gt;alpha&lt;/b&gt;" in page
        assert "<i>bot</i>" not in page
        assert "&lt;i&gt;bot&lt;/i&gt;" in page


def test_portfolio_file_opens_only_its_own_pages(tmp_path):
    with pytest.raises(ValueError):
        AggregateReportCreator._open_portfolio_file(str(tmp_path), "../elsewhere.html")


class TestShareCards:
    @staticmethod
    def _render(temp_dir, summaries, site_url="", share_card=False, monkeypatch=None):
        if monkeypatch is not None:
            from gitstats import load_config

            monkeypatch.setitem(load_config(), "share_card", share_card)
        AggregateReportCreator().create(
            summaries, [], temp_dir, title="GitStats Gallery", site_url=site_url
        )
        pages = {}
        for name in ("index.html", "ai.html", "share-card.html", "ai-share-card.html"):
            path = os.path.join(temp_dir, name)
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    pages[name] = f.read()
        return pages

    def test_pages_and_cards(self, temp_dir, monkeypatch):
        summaries = [
            _summary(
                "alpha",
                300,
                {"Alice": 3},
                ai_assisted=_ai([(0, 10), (1, 10), (2, 10), (5, 10)], {"Claude": 8}),
            ),
            _summary("beta", 200, {"Bob": 2}, ai_assisted=_ai([(0, 10)] * 4, {})),
            _summary(
                "<b>gamma</b>",
                100,
                {"Alice": 1},
                ai_assisted=_ai([(1, 10)] * 3 + [(6, 10)], {"Aider": 9}),
            ),
        ]
        pages = self._render(temp_dir, summaries, "https://example.com/g/", True, monkeypatch)
        index, ai = pages["index.html"], pages["ai.html"]
        assert '<meta property="og:url" content="https://example.com/g/">' in index
        assert '<meta property="og:image" content="https://example.com/g/share-card.png">' in index
        assert (
            '<meta property="og:description" content="Reports made with gitstats for 3 '
            'repositories, 600 commits: alpha, beta, &lt;b&gt;gamma&lt;/b&gt;.">'
        ) in index
        assert '<meta property="og:url" content="https://example.com/g/ai.html">' in ai
        assert '<meta property="og:image" content="https://example.com/g/ai-share-card.png">' in ai
        quarter = last_quarters(datetime.datetime.now())[-1][0]
        assert f"{quarter}: &lt;b&gt;gamma&lt;/b&gt;, 60.0%." in ai

        card = pages["share-card.html"]
        assert "<h1>GitStats Gallery</h1>" in card
        assert "3 repositories &middot; 600 commits &middot; 2 authors" in card
        assert "alpha&nbsp;&middot; beta&nbsp;&middot; &lt;b&gt;gamma&lt;/b&gt;" in card

        ai_card = pages["ai-share-card.html"]
        assert f"<h1>{quarter}</h1>" in ai_card
        # the largest shares of the last quarter, as bars; none for a share of 0
        assert ai_card.index("&lt;b&gt;gamma&lt;/b&gt;") < ai_card.index("<b>alpha</b>")
        assert '<i style="width:100.0%"></i><span>60.0%</span>' in ai_card
        assert "<b>beta</b>" not in ai_card
        assert "of 3 repositories. A lower bound." in ai_card

    def test_no_address_no_image(self, temp_dir, monkeypatch):
        pages = self._render(temp_dir, [_summary("alpha", 10, {})], "", True, monkeypatch)
        assert "og:image" not in pages["index.html"]
        assert '<meta property="og:title" content="GitStats Gallery">' in pages["index.html"]
        # the card is written all the same, and there is no AI page to have one
        assert "share-card.html" in pages
        assert "ai-share-card.html" not in pages

    def test_no_card_unless_asked(self, temp_dir, monkeypatch):
        summaries = [_summary("alpha", 10, {}, ai_assisted=_ai([(0, 10)] * 4, {}))]
        pages = self._render(temp_dir, summaries, "https://example.com/g/", False, monkeypatch)
        assert "og:image" not in pages["index.html"]
        assert "og:image" not in pages["ai.html"]
        # no share in the last quarter: the description and the card say nothing of one
        assert "repositories, quarter by quarter." in pages["ai.html"]
        assert '<div class="bars"></div>' in pages["ai-share-card.html"]

    def test_description_of_a_large_portfolio(self, temp_dir):
        from gitstats.aggregate import portfolio_description

        summaries = [_summary(f"r{i}", 10 - i, {}) for i in range(6)]
        assert portfolio_description(summaries) == (
            "Reports made with gitstats for 6 repositories, 45 commits: r0, r1, r2, r3 and more."
        )
