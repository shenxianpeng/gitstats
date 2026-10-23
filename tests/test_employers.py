"""Tests for sorting commit addresses by the organization they belong to."""

from types import SimpleNamespace

import pytest

from gitstats.employers import (
    BOT,
    HIDDEN,
    ORGANIZATION,
    PERSONAL,
    UNKNOWN,
    Affiliation,
    classify,
    quarter_of,
    registrable_domain,
    summarize,
)


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("google.com", "google.com"),
        ("git.kernel.org", "kernel.org"),
        ("Mail.Corp.Example.co.uk", "example.co.uk"),
        ("cs.ox.ac.uk", "ox.ac.uk"),
        ("mails.tsinghua.edu.cn", "tsinghua.edu.cn"),
        ("redhat.com.", "redhat.com"),
        ("localhost", "localhost"),
        ("", ""),
    ],
)
def test_registrable_domain(host, expected):
    assert registrable_domain(host) == expected


@pytest.mark.parametrize(
    ("author", "email", "expected"),
    [
        ("Ann", "ann@google.com", Affiliation(ORGANIZATION, "google.com")),
        # a subdomain counts under the organization's own domain
        ("Ann", "ann@linux.ibm.com", Affiliation(ORGANIZATION, "ibm.com")),
        ("Ann", "Ann@Corp.Example.CO.UK", Affiliation(ORGANIZATION, "example.co.uk")),
        # one organization under two domains
        ("Ann", "ann@fb.com", Affiliation(ORGANIZATION, "meta.com")),
        ("Ann", "ann@amazon.co.uk", Affiliation(ORGANIZATION, "amazon.com")),
        # mail providers anyone can sign up for
        ("Ann", "ann@gmail.com", Affiliation(PERSONAL)),
        ("Ann", "ann@qq.com", Affiliation(PERSONAL)),
        ("Ann", "ann@yahoo.co.uk", Affiliation(PERSONAL)),
        ("Ann", "ann@eu.mail.yahoo.com", Affiliation(PERSONAL)),
        # a code host's private address, and no-reply senders
        ("Ann", "123+ann@users.noreply.github.com", Affiliation(HIDDEN)),
        ("Ann", "ann@users.noreply.gitlab.com", Affiliation(HIDDEN)),
        ("Ann", "ann@x.noreply.github.com", Affiliation(HIDDEN)),
        ("Ann", "noreply@example.org", Affiliation(HIDDEN)),
        # nothing to go by
        ("Ann", "ann", Affiliation(UNKNOWN)),
        ("Ann", "", Affiliation(UNKNOWN)),
        ("Ann", "@google.com", Affiliation(UNKNOWN)),
        ("Ann", "ann@", Affiliation(UNKNOWN)),
        ("Ann", "ann@laptop", Affiliation(UNKNOWN)),
        ("Ann", "ann@ann-mbp.local", Affiliation(UNKNOWN)),
        ("Ann", "ann@localhost.localdomain", Affiliation(UNKNOWN)),
        ("Ann", "ann@(none)", Affiliation(UNKNOWN)),
        ("Ann", "ann@example.com", Affiliation(UNKNOWN)),
        ("Ann", "ann@build.example.com", Affiliation(UNKNOWN)),
        # an account named [bot] is a bot, whatever its address
        ("dependabot[bot]", "49699333+dependabot[bot]@users.noreply.github.com", Affiliation(BOT)),
        ("renovate[bot] ", "bot@renovateapp.com", Affiliation(BOT)),
    ],
)
def test_classify(author, email, expected):
    assert classify(author, email) == expected


@pytest.mark.parametrize(
    ("month", "quarter"),
    [("2026-01", "2026-Q1"), ("2026-03", "2026-Q1"), ("2026-07", "2026-Q3"), ("2025-12", "2025-Q4")],
)
def test_quarter_of(month, quarter):
    assert quarter_of(month) == quarter


def _data(**fields):
    defaults = {
        "affiliation_by_month": {
            "2025-06": {ORGANIZATION: 2, PERSONAL: 1},
            "2025-11": {ORGANIZATION: 1, HIDDEN: 1},
            "2026-02": {ORGANIZATION: 3, BOT: 2, UNKNOWN: 1},
        },
        "organizations": {
            "google.com": {
                "commits": 4,
                "first_commit_stamp": 100,
                "last_commit_stamp": 400,
                "by_month": {"2025-06": 2, "2026-02": 2},
            },
            "redhat.com": {
                "commits": 2,
                "first_commit_stamp": 200,
                "last_commit_stamp": 300,
                "by_month": {"2025-11": 1, "2026-02": 1},
            },
            "acme.org": {
                "commits": 2,
                "first_commit_stamp": 50,
                "last_commit_stamp": 60,
                "by_month": {"2025-03": 2},
            },
        },
        "organization_authors": {"google.com": 2},
    }
    defaults.update(fields)
    return SimpleNamespace(**defaults)


def test_summarize():
    overview = summarize(_data(), limit=2, quarters=2)

    assert overview["commits"] == 11
    assert overview["by_kind"] == {
        ORGANIZATION: 6,
        PERSONAL: 1,
        HIDDEN: 1,
        UNKNOWN: 1,
        BOT: 2,
    }
    assert overview["organization_count"] == 3
    # the 12 months that end with the last month with commits
    assert overview["last_month"] == "2026-02"
    assert overview["year_start"] == "2025-03"
    # most commits first, ties by name; only the first two
    assert [row["organization"] for row in overview["organizations"]] == [
        "google.com",
        "acme.org",
    ]
    google, acme = overview["organizations"]
    assert google == {
        "organization": "google.com",
        "commits": 4,
        "commits_last_12mo": 4,
        "authors": 2,
        "first_commit_stamp": 100,
        "last_commit_stamp": 400,
    }
    # no address was kept for it
    assert acme["authors"] == 0
    assert acme["commits_last_12mo"] == 2
    # the last two quarters, oldest first
    assert [quarter["quarter"] for quarter in overview["quarters"]] == ["2025-Q4", "2026-Q1"]
    assert overview["quarters"][1] == {
        "quarter": "2026-Q1",
        "commits": 6,
        "by_kind": {ORGANIZATION: 3, PERSONAL: 0, HIDDEN: 0, UNKNOWN: 1, BOT: 2},
    }


def test_summarize_window_leaves_out_older_months():
    data = _data(
        affiliation_by_month={"2027-02": {ORGANIZATION: 1}, "2025-06": {ORGANIZATION: 2}},
    )
    google = summarize(data)["organizations"][0]
    # 2025-06 and 2026-02 are both before 2026-03
    assert google["commits_last_12mo"] == 0


def test_summarize_without_the_data():
    assert summarize(SimpleNamespace()) is None
    assert summarize(_data(affiliation_by_month={})) is None
    assert summarize(_data(organizations=None)) is None


def test_summarize_without_addresses():
    overview = summarize(_data(organization_authors=None))
    assert all(row["authors"] == 0 for row in overview["organizations"])
