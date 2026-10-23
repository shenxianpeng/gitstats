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
    ai_csv,
    ai_dataset,
    compute_repo_summary,
    last_quarters,
    load_repo_summaries,
    organizations_csv,
    organizations_dataset,
    organizations_description,
    organizations_summary,
    quarter_id,
    snapshot_label,
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


def _months(first, last):
    """The months from ``first`` to ``last``, as "YYYY-MM"."""
    year, month = map(int, first.split("-"))
    months = []
    while f"{year:04d}-{month:02d}" <= last:
        months.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


class TestAiDataset:
    NOW = datetime.datetime(2026, 10, 15, 12, 0)

    @staticmethod
    def _ai(counts):
        """An ai_assisted block of 24 months up to October 2026: ``counts``
        gives (commits that name an assistant, all commits) by month, others
        have 10 commits and none of them names one."""
        months = _months("2024-11", "2026-10")
        return {
            "commits": 42,
            "authored": 3,
            "assistants": {"Claude": 30, "GitHub Copilot": 12},
            "by_month": {m: counts.get(m, (0, 10))[0] for m in months},
            "commits_by_month": {m: counts.get(m, (0, 10))[1] for m in months},
        }

    def test_months_and_quarters(self):
        ai = self._ai({"2026-07": (3, 10), "2026-08": (5, 10), "2026-10": (9, 9)})
        summary = _summary("vscode", 500, {}, ai_assisted=ai, generated_by="gitstats 2.10.0")
        data = ai_dataset([summary], self.NOW)
        assert data["schema_version"] == 1
        assert "lower bounds" in data["description"]
        assert data["generated_by"].startswith("gitstats ")
        assert ai_dataset([summary], self.NOW, "2.10.0")["generated_by"] == "gitstats 2.10.0"
        assert data["generated_at"].startswith("2026-10-15T12:00:00")
        # the complete quarters of the 24 months: not Oct-Dec 2024, of which
        # October is missing, nor the quarter under way
        assert data["quarters"] == [
            "2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2", "2026-Q3"
        ]  # fmt: skip
        [repository] = data["repositories"]
        assert repository["name"] == "vscode"
        assert repository["report"] == "vscode/index.html"
        # the version that counted them, not the one that put the data together
        assert repository["counted_by"] == "gitstats 2.10.0"
        assert repository["all_time"] == {
            "commits": 500,
            "ai_assisted": 42,
            "authored": 3,
            "assistants": {"Claude": 30, "GitHub Copilot": 12},
        }
        assert repository["quarters"]["2026-Q3"] == {
            "commits": 30,
            "ai_assisted": 8,
            "share": 0.2667,
        }
        assert repository["quarters"]["2025-Q1"] == {"commits": 30, "ai_assisted": 0, "share": 0.0}
        # complete months only: October 2026 is still under way
        assert list(repository["months"]) == _months("2024-11", "2026-09")
        assert repository["months"]["2026-08"] == {"commits": 10, "ai_assisted": 5}

    def test_repositories_by_name_and_only_those_that_count_them(self):
        summaries = [
            _summary("beta", 10, {}, ai_assisted=self._ai({})),
            _summary("alpha", 10, {}),
            _summary("Gamma", 10, {}, ai_assisted=self._ai({})),
            _summary("Alpha2", 10, {}, ai_assisted=self._ai({})),
        ]
        data = ai_dataset(summaries, self.NOW)
        assert [r["name"] for r in data["repositories"]] == ["Alpha2", "beta", "Gamma"]

    def test_a_quarter_without_commits_has_no_share(self):
        quiet = {m: (0, 0) for m in ("2026-07", "2026-08", "2026-09")}
        data = ai_dataset([_summary("a", 10, {}, ai_assisted=self._ai(quiet))], self.NOW)
        assert data["repositories"][0]["quarters"]["2026-Q3"] == {
            "commits": 0,
            "ai_assisted": 0,
            "share": None,
        }

    def test_a_summary_that_does_not_reach_back_that_far(self):
        old = {"commits": 1, "by_month": {"2001-01": 1}, "commits_by_month": {"2001-01": 10}}
        data = ai_dataset([_summary("a", 10, {}, ai_assisted=old)], self.NOW)
        assert data["quarters"] == []
        assert data["repositories"][0]["quarters"] == {}
        assert data["repositories"][0]["months"] == {"2001-01": {"commits": 10, "ai_assisted": 1}}
        assert data["repositories"][0]["all_time"]["assistants"] == {}

    def test_csv(self):
        ai = self._ai({"2026-09": (4, 8)})
        data = ai_dataset([_summary("a, b", 10, {}, ai_assisted=ai)], self.NOW)
        lines = ai_csv(data).splitlines()
        assert lines[0] == "repository,month,commits,ai_assisted"
        assert lines[1] == '"a, b",2024-11,10,0'
        assert lines[-1] == '"a, b",2026-09,8,4'
        assert len(lines) == 1 + 23


@pytest.mark.parametrize(
    ("months", "expected"),
    [
        (["2026-07", "2026-08", "2026-09"], "2026-Q3"),
        (["2025-01"], "2025-Q1"),
        (["2024-12"], "2024-Q4"),
    ],
)
def test_quarter_id(months, expected):
    assert quarter_id(months) == expected


def test_snapshot_label():
    assert snapshot_label("ai/2026-Q3.json") == "Jul\u2013Sep 2026"
    assert snapshot_label("ai/2025-Q1.json") == "Jan\u2013Mar 2025"
    assert snapshot_label("ai/notes.json") == "ai/notes.json"


class TestAiData:
    @staticmethod
    def _create(path, summaries):
        AggregateReportCreator().create(summaries, [], str(path), title="GitStats Gallery")

    @staticmethod
    def _read(path, name):
        with open(os.path.join(path, name), encoding="utf-8") as f:
            return f.read()

    def test_data_files_and_the_snapshot_of_the_last_quarter(self, tmp_path):
        self._create(tmp_path, [_summary("alpha", 40, {}, ai_assisted=_ai([(1, 10)] * 4, {}))])
        last = quarter_id(last_quarters(datetime.datetime.now())[-1][1])
        data = json.loads(self._read(tmp_path, "ai.json"))
        assert data["snapshots"] == [f"ai/{last}.json"]
        assert data["repositories"][0]["quarters"][last]["ai_assisted"] == 1
        snapshot = json.loads(self._read(tmp_path, f"ai/{last}.json"))
        assert snapshot["repositories"] == data["repositories"]
        assert "snapshots" not in snapshot
        assert self._read(tmp_path, "ai.csv").startswith("repository,month,commits,ai_assisted\n")
        page = self._read(tmp_path, "ai.html")
        assert "<h2>Data</h2>" in page
        assert '<a href="ai.json">ai.json</a>, <a href="ai.csv">ai.csv</a>' in page
        assert (
            f'<a href="ai/{last}.json">{last_quarters(datetime.datetime.now())[-1][0]}</a>' in page
        )

    def test_a_snapshot_is_written_once(self, tmp_path):
        self._create(tmp_path, [_summary("alpha", 40, {}, ai_assisted=_ai([(1, 10)] * 4, {}))])
        last = quarter_id(last_quarters(datetime.datetime.now())[-1][1])
        first = self._read(tmp_path, f"ai/{last}.json")
        # a week later: a commit written in the quarter has been merged since
        self._create(
            tmp_path, [_summary("alpha", 41, {}, ai_assisted=_ai([(1, 10)] * 3 + [(2, 11)], {}))]
        )
        assert self._read(tmp_path, f"ai/{last}.json") == first
        data = json.loads(self._read(tmp_path, "ai.json"))
        assert data["repositories"][0]["quarters"][last]["ai_assisted"] == 2

    def test_the_snapshots_already_there_are_listed(self, tmp_path):
        (tmp_path / "ai").mkdir()
        (tmp_path / "ai" / "2001-Q1.json").write_text("{}", encoding="utf-8")
        (tmp_path / "ai" / "notes.json").write_text("{}", encoding="utf-8")
        self._create(tmp_path, [_summary("alpha", 40, {}, ai_assisted=_ai([(1, 10)] * 4, {}))])
        last = quarter_id(last_quarters(datetime.datetime.now())[-1][1])
        data = json.loads(self._read(tmp_path, "ai.json"))
        assert data["snapshots"] == ["ai/2001-Q1.json", f"ai/{last}.json"]
        page = self._read(tmp_path, "ai.html")
        assert '<a href="ai/2001-Q1.json">Jan\u2013Mar 2001</a>, ' in page
        assert "notes.json" not in page

    def test_no_snapshot_without_a_complete_quarter(self, tmp_path):
        old = _ai([(1, 10)] * 4, {})
        old["by_month"], old["commits_by_month"] = {"2001-01": 1}, {"2001-01": 10}
        self._create(tmp_path, [_summary("alpha", 10, {}, ai_assisted=old)])
        assert not (tmp_path / "ai").exists()
        assert json.loads(self._read(tmp_path, "ai.json"))["snapshots"] == []
        page = self._read(tmp_path, "ai.html")
        assert '<a href="ai.csv">ai.csv</a>.</p>' in page
        assert "as it was first published" not in page


@pytest.mark.parametrize("name", ["ai/2026-Q3.json", "ai.json", "ai.csv"])
def test_portfolio_file_opens_its_data(tmp_path, name):
    AggregateReportCreator._open_portfolio_file(str(tmp_path), name).close()
    assert (tmp_path / name).exists()


@pytest.mark.parametrize(
    "name", ["ai/../x.json", "ai/2026-Q5.json", "ai/2026-Q3.json.html", "data.json"]
)
def test_portfolio_file_refuses_other_data(tmp_path, name):
    with pytest.raises(ValueError):
        AggregateReportCreator._open_portfolio_file(str(tmp_path), name)


def test_portfolio_says_the_version_it_is_given(tmp_path):
    summaries = [_summary("alpha", 40, {}, ai_assisted=_ai([(1, 10)] * 4, {}))]
    AggregateReportCreator().create(summaries, [], str(tmp_path), version="2.10.0")
    for page in ("index.html", "ai.html"):
        text = (tmp_path / page).read_text(encoding="utf-8")
        assert "generated by gitstats 2.10.0 on " in text
        assert '<meta name="generator" content="GitStats 2.10.0">' in text
    data = json.loads((tmp_path / "ai.json").read_text(encoding="utf-8"))
    assert data["generated_by"] == "gitstats 2.10.0"


# ── groups: a gallery's ecosystems ───────────────────────────────────────


class TestGroups:
    GROUPS = [("python", "Python"), ("cncf", "CNCF graduated"), ("empty", "Nobody")]

    @staticmethod
    def _render(temp_dir, summaries, groups):
        AggregateReportCreator().create(summaries, [], temp_dir, groups=groups)
        pages = {}
        for name in ("index.html", "ai.html"):
            path = os.path.join(temp_dir, name)
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    pages[name] = f.read()
        return pages

    def _summaries(self):
        ai = _ai([(0, 10), (1, 10), (2, 10), (5, 10)], {"Claude": 8})
        return [
            _summary("django", 300, {}, group="python", ai_assisted=ai),
            _summary("flask", 100, {}, group="python", ai_assisted=ai),
            _summary("etcd", 200, {}, group="cncf", ai_assisted=ai),
        ]

    def test_buttons_for_the_groups_that_have_repositories(self, temp_dir):
        page = self._render(temp_dir, self._summaries(), self.GROUPS)["index.html"]
        assert '<div class="group-filter"' in page
        assert '<button type="button" data-group="" aria-pressed="true">All <span>3</span>' in page
        assert 'data-group="python" aria-pressed="false">Python <span>2</span>' in page
        assert 'data-group="cncf" aria-pressed="false">CNCF graduated <span>1</span>' in page
        # in the order given, and a group without repositories has no button
        assert page.index('data-group="python"') < page.index('data-group="cncf"')
        assert "Nobody" not in page

    def test_rows_say_their_group(self, temp_dir):
        page = self._render(temp_dir, self._summaries(), self.GROUPS)["index.html"]
        assert '<th class="portfolio-group">Ecosystem</th>' in page
        assert '<tr data-group="python"><td><a href="django/index.html">django</a></td>' in page
        assert '<td class="portfolio-group">CNCF graduated</td>' in page
        assert page.count("#group=") >= 1  # the script that narrows them

    def test_ai_page_narrows_too(self, temp_dir):
        page = self._render(temp_dir, self._summaries(), self.GROUPS)["ai.html"]
        assert '<div class="group-filter"' in page
        assert '<tr data-group="cncf"><td><a href="etcd/authors.html' in page

    def test_no_groups_no_filter(self, temp_dir):
        pages = self._render(temp_dir, self._summaries(), None)
        for page in pages.values():
            assert "group-filter" not in page
            assert "data-group" not in page
            assert "Ecosystem" not in page

    def test_group_names_are_escaped(self, temp_dir):
        summaries = [_summary("a", 1, {}, group="x")]
        page = self._render(temp_dir, summaries, [("x", "<b>X</b>")])["index.html"]
        assert "&lt;b&gt;X&lt;/b&gt;" in page
        assert "<b>X</b>" not in page


# ── organizations_summary ────────────────────────────────────────────────


def _organization_data():
    return SimpleNamespace(
        affiliation_by_month={
            "2025-12": {"organization": 2, "personal": 1},
            "2026-01": {"organization": 1, "hidden": 1, "bot": 1},
        },
        organizations={
            "google.com": {
                "commits": 3,
                "first_commit_stamp": int(datetime.datetime(2025, 12, 2, 12).timestamp()),
                "last_commit_stamp": int(datetime.datetime(2026, 1, 5, 12).timestamp()),
                "by_month": {"2025-12": 2, "2026-01": 1},
            }
        },
        organization_authors={"google.com": 2},
    )


def test_organizations_summary():
    summary = organizations_summary(_organization_data())
    assert "not who paid for the work" in summary["description"]
    assert summary["commits"] == 6
    assert summary["by_kind"] == {
        "organization": 3,
        "one_person": 0,
        "personal": 1,
        "hidden": 1,
        "unknown": 0,
        "bot": 1,
    }
    assert summary["organization_count"] == 1
    assert summary["last_12mo_from"] == "2025-02"
    assert summary["top"] == [
        {
            "organization": "google.com",
            "commits": 3,
            "commits_last_12mo": 3,
            "addresses": 2,
            "first_commit": "2025-12-02",
            "last_commit": "2026-01-05",
        }
    ]
    assert list(summary["quarters"]) == ["2025-Q4", "2026-Q1"]
    assert summary["quarters"]["2026-Q1"]["bot"] == 1
    # domains only: no address is written
    assert "@" not in json.dumps(summary)


def test_organizations_summary_without_the_data():
    assert organizations_summary(SimpleNamespace()) is None


def test_compute_repo_summary_keeps_organizations():
    data = _organization_data()
    summary = compute_repo_summary(data, "index.html")
    assert summary["organizations"]["top"][0]["organization"] == "google.com"
    assert compute_repo_summary(SimpleNamespace(), "index.html")["organizations"] is None


# ── organizations page ───────────────────────────────────────────────────

_KINDS = ("organization", "one_person", "personal", "hidden", "unknown", "bot")


def _recent_quarters(now=None):
    return [quarter_id(months) for _, months in last_quarters(now or datetime.datetime.now())]


def _orgs(top, by_quarter=None, now=None):
    """An organizations block of a summary: ``top`` as (domain, commits,
    commits in the last 12 months); ``by_quarter``, the commits of each of
    the last four quarters as {kind: commits}."""
    quarters = _recent_quarters(now)
    by_quarter = by_quarter or [{"organization": 1, "personal": 1}] * 4
    return {
        "commits": 100,
        "top": [
            {
                "organization": name,
                "commits": commits,
                "commits_last_12mo": recent,
                "addresses": 2,
                "first_commit": "2020-01-01",
                "last_commit": "2026-01-01",
            }
            for name, commits, recent in top
        ],
        "quarters": {
            quarter: {kind: kinds.get(kind, 0) for kind in _KINDS}
            for quarter, kinds in zip(quarters, by_quarter)
        },
    }


class TestOrganizationsDataset:
    NOW = datetime.datetime(2026, 10, 23, 12)

    def _summaries(self):
        return [
            _summary(
                "kubernetes",
                1000,
                {},
                group="cncf",
                organizations=_orgs(
                    [("google.com", 500, 40), ("redhat.com", 300, 60)],
                    [{"organization": 30, "personal": 10}] * 4,
                    self.NOW,
                ),
            ),
            _summary(
                "django",
                500,
                {},
                organizations=_orgs(
                    [("redhat.com", 5, 0), ("acme.org", 10, 3)],
                    [{"organization": 1, "personal": 9, "bot": 2}] * 4,
                    self.NOW,
                ),
            ),
            # data from before organizations were counted
            _summary("old", 10, {}),
            _summary("none", 10, {}, organizations=None),
        ]

    def test_organizations_added_up(self):
        data = organizations_dataset(self._summaries(), self.NOW, "9.9")
        assert data["generated_by"] == "gitstats 9.9"
        assert data["quarters"] == ["2025-Q4", "2026-Q1", "2026-Q2", "2026-Q3"]
        assert "not who paid for the work" in data["description"]
        # the most commits in the last 12 months first
        assert data["organizations"] == [
            {
                "organization": "redhat.com",
                "commits_last_12mo": 60,
                "commits": 305,
                "repositories": ["django", "kubernetes"],
            },
            {
                "organization": "google.com",
                "commits_last_12mo": 40,
                "commits": 500,
                "repositories": ["kubernetes"],
            },
            {
                "organization": "acme.org",
                "commits_last_12mo": 3,
                "commits": 10,
                "repositories": ["django"],
            },
        ]

    def test_repositories_by_kind(self):
        data = organizations_dataset(self._summaries(), self.NOW)
        assert [entry["name"] for entry in data["repositories"]] == ["kubernetes", "django"]
        kubernetes, django = data["repositories"]
        assert kubernetes["group"] == "cncf"
        assert "group" not in django
        assert kubernetes["report"] == "kubernetes/index.html"
        assert kubernetes["commits"] == 160
        assert kubernetes["by_kind"]["organization"] == 120
        assert django["by_kind"] == {
            "organization": 4,
            "one_person": 0,
            "personal": 36,
            "hidden": 0,
            "unknown": 0,
            "bot": 8,
        }
        # by their commits in the last 12 months; none for an organization without
        assert kubernetes["organizations_last_12mo"] == [
            {"organization": "redhat.com", "commits": 60},
            {"organization": "google.com", "commits": 40},
        ]
        assert django["organizations_last_12mo"] == [{"organization": "acme.org", "commits": 3}]

    def test_quarters_outside_the_last_four_are_left_out(self):
        block = _orgs([("acme.org", 1, 1)], now=self.NOW)
        block["quarters"]["2020-Q1"] = {"organization": 99}
        data = organizations_dataset([_summary("a", 1, {}, organizations=block)], self.NOW)
        assert data["repositories"][0]["by_kind"]["organization"] == 4

    def test_csv(self):
        data = organizations_dataset(self._summaries(), self.NOW)
        assert organizations_csv(data).splitlines() == [
            "organization,repositories,commits_last_12mo,commits",
            "redhat.com,2,60,305",
            "google.com,1,40,500",
            "acme.org,1,3,10",
        ]

    def test_description(self):
        data = organizations_dataset(self._summaries(), self.NOW)
        assert organizations_description(data) == (
            "The organizations whose addresses commit to 2 repositories, by the domain of "
            "the address. Most commits in the last 12 months: redhat.com, 60 in 2 "
            "repositories."
        )
        data["organizations"] = []
        assert organizations_description(data).endswith("by the domain of the address.")


class TestOrganizationsPage:
    @staticmethod
    def _render(temp_dir, summaries, groups=None):
        AggregateReportCreator().create(summaries, [], temp_dir, groups=groups)
        pages = {}
        for name in ("index.html", "ai.html", "organizations.html"):
            path = os.path.join(temp_dir, name)
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    pages[name] = f.read()
        return pages

    @staticmethod
    def _summaries():
        return [
            _summary(
                "kubernetes",
                1000,
                {},
                group="cncf",
                organizations=_orgs(
                    [("google.com", 500, 40), ("redhat.com", 300, 60)],
                    [{"organization": 30, "personal": 10}] * 4,
                ),
            ),
            _summary(
                "django",
                500,
                {},
                group="python",
                organizations=_orgs([("acme.org", 10, 0)], [{"personal": 9, "bot": 1}] * 4),
            ),
        ]

    def test_page_and_data(self, temp_dir):
        pages = self._render(temp_dir, self._summaries())
        page = pages["organizations.html"]
        assert "<h1>Organizations</h1>" in page
        assert "not who paid for the" in page
        assert '<table class="sortable" id="organizations">' in page
        assert (
            '<tr><td>redhat.com</td><td class="num">1</td><td class="num">60</td>'
            '<td class="num">300</td><td>kubernetes</td></tr>'
        ) in page
        # tiles: organizations with commits in the last 12 months, the widest, the largest share
        assert "with commits in the last 12 months, of 3" in page
        # all in one repository: the one with the most recent commits
        assert "redhat<wbr>.com" in page
        assert "75.0%" in page and "of kubernetes&rsquo;s commits" in page
        # each repository: links to its organizations, the largest share first
        mix = page[page.index('id="organization-mix"') :]
        assert 'href="kubernetes/authors.html#commits_by_organization"' in mix
        assert mix.index("kubernetes") < mix.index("django")
        assert "redhat.com (60), google.com (40)" in mix
        assert "<td>&ndash;</td>" in mix  # django: none in the last 12 months
        assert '<a href="organizations.json">' in page
        with open(os.path.join(temp_dir, "organizations.json"), encoding="utf-8") as f:
            data = json.load(f)
        assert data["organizations"][0]["organization"] == "redhat.com"
        with open(os.path.join(temp_dir, "organizations.csv"), encoding="utf-8") as f:
            assert f.readline().startswith("organization,")
        # linked from the portfolio page and the nav of every page
        assert '<a href="organizations.html">Organizations, by the' in pages["index.html"]
        assert 'href="organizations.html"' in pages["index.html"].split("</div>")[0] + page

    def test_no_page_without_organizations(self, temp_dir):
        summaries = [_summary("a", 1, {}), _summary("b", 1, {}, organizations=_orgs([]))]
        pages = self._render(temp_dir, summaries)
        assert "organizations.html" not in pages
        assert not os.path.exists(os.path.join(temp_dir, "organizations.json"))
        assert "organizations.html" not in pages["index.html"]

    def test_groups_narrow_the_repositories(self, temp_dir):
        groups = [("python", "Python"), ("cncf", "CNCF graduated")]
        page = self._render(temp_dir, self._summaries(), groups)["organizations.html"]
        assert '<div class="group-filter"' in page
        assert '<tr data-group="cncf"><td><a href="kubernetes/authors.html' in page

    def test_long_list_is_cut(self, temp_dir):
        top = [(f"org{n:03d}.com", 100 - n % 50, 1) for n in range(60)]
        page = self._render(temp_dir, [_summary("a", 1, {}, organizations=_orgs(top))])[
            "organizations.html"
        ]
        table = page[page.index('id="organizations"') : page.index('id="organization-mix"')]
        assert table.count("<tr><td>") == 50
        assert "The first 50 of 60; all of them are in the data below." in page

    def test_many_repositories_are_summed_up(self, temp_dir):
        summaries = [
            _summary(f"r{n}", 1, {}, organizations=_orgs([("acme.org", 1, 1)])) for n in range(6)
        ]
        page = self._render(temp_dir, summaries)["organizations.html"]
        assert "<td>r0, r1, r2, r3 and 2 more</td>" in page
        assert "6 of 6 repositories" in page

    def test_escapes(self, temp_dir):
        summary = _summary("<i>x</i>", 1, {}, organizations=_orgs([("<b>.org", 1, 1)]))
        summary["report_path"] = "elsewhere.html"
        page = self._render(temp_dir, [summary])["organizations.html"]
        assert "<b>.org" not in page and "&lt;b&gt;" in page
        assert "<i>x</i>" not in page
        # a report that is not an index page is linked as it is
        assert 'href="elsewhere.html"' in page

    def test_repositories_without_commits_in_the_quarters(self, temp_dir):
        quiet = _orgs([("acme.org", 5, 0)], [{}] * 4)
        page = self._render(temp_dir, [_summary("a", 1, {}, organizations=quiet)])[
            "organizations.html"
        ]
        assert "Largest Share" not in page
        assert '<td class="num">0</td><td class="num">0%</td>' in page
