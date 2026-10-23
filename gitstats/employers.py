"""Which organization a commit's email address belongs to.

Git keeps an email address for every author. Its domain often names the
company, university or foundation the address belongs to: ``@google.com``,
``@redhat.com``, ``@python.org``. Counting commits by that domain shows where
a project's commits come from.

It shows where the address is, not who pays for the work. People commit to
open source from personal addresses on paid time, and from work addresses on
their own time. Addresses at a mail provider anyone can sign up for
(``@gmail.com``, ``@qq.com``) are grouped as personal, GitHub's private
``noreply`` addresses as hidden, and accounts named ``…[bot]`` as bots, so
none of them is mistaken for an organization. A domain only one address
commits from is most often a person's own (``@jane.dev``): a report counts
it as a one-address domain, not as an organization.

Only domains are kept. No address or name leaves this module.
"""

from __future__ import annotations

from typing import Any, NamedTuple

ORGANIZATION = "organization"
ONE_ADDRESS = "one_address"
PERSONAL = "personal"
HIDDEN = "hidden"
UNKNOWN = "unknown"
BOT = "bot"

# The kinds in the order a report lists them.
KINDS: tuple[str, ...] = (ORGANIZATION, ONE_ADDRESS, PERSONAL, HIDDEN, UNKNOWN, BOT)

KIND_LABELS: dict[str, str] = {
    ORGANIZATION: "Organizations",
    ONE_ADDRESS: "One-address domains",
    PERSONAL: "Personal email",
    HIDDEN: "Hidden (noreply)",
    UNKNOWN: "Unknown",
    BOT: "Bots",
}

# Mail providers anyone can sign up for, matched on the registrable domain.
PERSONAL_DOMAINS: frozenset[str] = frozenset(
    {
        "126.com",
        "139.com",
        "163.com",
        "aliyun.com",
        "aol.com",
        "fastmail.com",
        "fastmail.fm",
        "foxmail.com",
        "gmail.com",
        "gmx.at",
        "gmx.com",
        "gmx.de",
        "gmx.net",
        "googlemail.com",
        "hey.com",
        "hotmail.co.uk",
        "hotmail.com",
        "hotmail.de",
        "hotmail.fr",
        "icloud.com",
        "live.com",
        "mac.com",
        "mail.com",
        "mail.ru",
        "me.com",
        "msn.com",
        "naver.com",
        "outlook.com",
        "outlook.de",
        "outlook.fr",
        "pm.me",
        "posteo.de",
        "posteo.net",
        "proton.me",
        "protonmail.ch",
        "protonmail.com",
        "qq.com",
        "rambler.ru",
        "seznam.cz",
        "sina.cn",
        "sina.com",
        "sohu.com",
        "t-online.de",
        "tutanota.com",
        "web.de",
        "yahoo.co.jp",
        "yahoo.co.uk",
        "yahoo.com",
        "yahoo.de",
        "yahoo.fr",
        "yandex.com",
        "yandex.ru",
        "ya.ru",
        "zoho.com",
    }
)

# Addresses that hide the person's own: a code host's private address.
HIDDEN_DOMAINS: frozenset[str] = frozenset(
    {
        "users.noreply.github.com",
        "noreply.github.com",
        "users.noreply.gitlab.com",
        "noreply.codeberg.org",
    }
)

# Suffixes under which an organization registers the third label from the
# right: "ox.ac.uk", not "ac.uk".
TWO_LABEL_SUFFIXES: frozenset[str] = frozenset(
    {
        "ac.at",
        "ac.cn",
        "ac.il",
        "ac.in",
        "ac.jp",
        "ac.kr",
        "ac.nz",
        "ac.uk",
        "ac.za",
        "co.at",
        "co.il",
        "co.in",
        "co.jp",
        "co.kr",
        "co.nz",
        "co.uk",
        "co.za",
        "com.au",
        "com.br",
        "com.cn",
        "com.hk",
        "com.mx",
        "com.sg",
        "com.tr",
        "com.tw",
        "edu.au",
        "edu.cn",
        "edu.hk",
        "edu.sg",
        "edu.tw",
        "gov.cn",
        "gov.uk",
        "ne.jp",
        "net.au",
        "net.cn",
        "or.jp",
        "org.au",
        "org.cn",
        "org.uk",
    }
)

# Domains of one organization, under the one a report names it by. Kept short
# on purpose: only merges that are not in doubt.
ORGANIZATION_ALIASES: dict[str, str] = {
    "fb.com": "meta.com",
    "amazon.de": "amazon.com",
    "amazon.co.uk": "amazon.com",
    "amazon.co.jp": "amazon.com",
}

# Host names that machines make up when git is not told an address.
_LOCAL_SUFFIXES: tuple[str, ...] = (".local", ".localdomain", ".lan", ".home", ".internal")
_LOCAL_HOSTS: frozenset[str] = frozenset({"localhost", "(none)", "none", "example.com"})
_NOREPLY_USERS: frozenset[str] = frozenset({"noreply", "no-reply", "donotreply", "do-not-reply"})
# Addresses that CI services commit under, whatever name they give.
BOT_ADDRESSES: frozenset[str] = frozenset(
    {
        "action@github.com",
        "actions@github.com",
        "github-actions@github.com",
        "bot@renovateapp.com",
    }
)
_BOT_USERS: frozenset[str] = frozenset({"bot", "buildbot", "ci", "jenkins"})


class Affiliation(NamedTuple):
    """Where a commit's address belongs: one of KINDS, and for an
    organization its domain ("" for the others)."""

    kind: str
    organization: str = ""


def registrable_domain(domain: str) -> str:
    """The part of a host name an organization registers.

    "mail.corp.example.co.uk" -> "example.co.uk", "git.kernel.org" ->
    "kernel.org". A name of one label is returned as it is.
    """
    labels = [label for label in domain.strip().strip(".").lower().split(".") if label]
    if len(labels) <= 2:
        return ".".join(labels)
    keep = 3 if ".".join(labels[-2:]) in TWO_LABEL_SUFFIXES else 2
    return ".".join(labels[-keep:])


def classify(author: str, email: str) -> Affiliation:
    """Where the address of a commit by ``author`` <``email``> belongs."""
    if author.rstrip().endswith("[bot]"):
        return Affiliation(BOT)
    user, at, host = email.strip().rpartition("@")
    host = host.strip().strip(".").lower()
    if not at or not user or not host:
        return Affiliation(UNKNOWN)
    user = user.lower()
    if f"{user}@{host}" in BOT_ADDRESSES or user in _BOT_USERS or user.endswith("-bot"):
        return Affiliation(BOT)
    if host in HIDDEN_DOMAINS or host.endswith(".noreply.github.com"):
        return Affiliation(HIDDEN)
    if user in _NOREPLY_USERS:
        return Affiliation(HIDDEN)
    if "." not in host or host in _LOCAL_HOSTS or host.endswith(_LOCAL_SUFFIXES):
        return Affiliation(UNKNOWN)
    domain = registrable_domain(host)
    if domain in PERSONAL_DOMAINS or host in PERSONAL_DOMAINS:
        return Affiliation(PERSONAL)
    if domain in _LOCAL_HOSTS:
        return Affiliation(UNKNOWN)
    return Affiliation(ORGANIZATION, ORGANIZATION_ALIASES.get(domain, domain))


def quarter_of(month: str) -> str:
    """The quarter of a "YYYY-MM" month: "2026-07" -> "2026-Q3"."""
    year, _, number = month.partition("-")
    return f"{year}-Q{(int(number) - 1) // 3 + 1}"


def _months_back(month: str, count: int) -> str:
    year, number = map(int, month.split("-"))
    year, number = divmod(year * 12 + number - 1 - count, 12)
    return f"{year:04d}-{number + 1:02d}"


def summarize(data: object, limit: int = 20, quarters: int = 8) -> dict[str, Any] | None:
    """What a report and a summary show of where the commits come from.

    ``organizations``: the ``limit`` organizations with the most commits, each
    with its commits in all and in the 12 months that end with the last
    commit, and how many addresses committed from it. ``quarters``: the last
    ``quarters`` quarters with commits, each with its commits by kind of
    address. A domain that one address commits from counts as ONE_ADDRESS,
    not as an organization. None for data collected before addresses were
    sorted this way.
    """
    by_month = getattr(data, "affiliation_by_month", None)
    organizations = getattr(data, "organizations", None)
    authors = getattr(data, "organization_authors", None)
    if not isinstance(by_month, dict) or not isinstance(organizations, dict) or not by_month:
        return None
    authors = authors if isinstance(authors, dict) else {}
    # domains of one address: only known when the addresses were counted
    single = {name for name in organizations if authors.get(name) == 1}
    by_month = {month: dict(kinds) for month, kinds in by_month.items()}
    for name in single:
        for month, commits in organizations[name]["by_month"].items():
            kinds = by_month.setdefault(month, {})
            kinds[ORGANIZATION] = kinds.get(ORGANIZATION, 0) - commits
            kinds[ONE_ADDRESS] = kinds.get(ONE_ADDRESS, 0) + commits
    last = max(by_month)
    year_start = _months_back(last, 11)

    by_kind = dict.fromkeys(KINDS, 0)
    by_quarter: dict[str, dict[str, int]] = {}
    for month, kinds in by_month.items():
        quarter = by_quarter.setdefault(quarter_of(month), dict.fromkeys(KINDS, 0))
        for kind, commits in kinds.items():
            by_kind[kind] = by_kind.get(kind, 0) + commits
            quarter[kind] = quarter.get(kind, 0) + commits

    ranked = sorted(
        ((name, info) for name, info in organizations.items() if name not in single),
        key=lambda item: (-item[1]["commits"], item[0]),
    )
    rows = [
        {
            "organization": name,
            "commits": info["commits"],
            "commits_last_12mo": sum(
                count for month, count in info["by_month"].items() if month >= year_start
            ),
            "authors": int(authors.get(name, 0)),
            "first_commit_stamp": info["first_commit_stamp"],
            "last_commit_stamp": info["last_commit_stamp"],
        }
        for name, info in ranked[:limit]
    ]
    return {
        "commits": sum(by_kind.values()),
        "by_kind": by_kind,
        "organization_count": len(organizations) - len(single),
        "year_start": year_start,
        "last_month": last,
        "organizations": rows,
        "quarters": [
            {"quarter": quarter, "commits": sum(kinds.values()), "by_kind": kinds}
            for quarter, kinds in sorted(by_quarter.items())[-quarters:]
        ],
    }
