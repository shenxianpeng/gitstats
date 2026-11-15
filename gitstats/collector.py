# Copyright (c) 2007-2014 Heikki Hokkanen <hoxu@users.sf.net> & others contributors
# GPLv2 / GPLv3
# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
"""What a report is made from: the collector that reads a repository's history.

GitDataCollector runs git and keeps what it reads as attributes; refine()
works out what follows from them. The pages of a report (gitstats.pages), the
portfolio's summaries (gitstats.aggregate) and the Repo Wrapped card read
those attributes, and ``-f json`` writes them as they are: an attribute's
name is a key of that file.
"""

import datetime
import json
import logging
import os
import re
import shlex
import subprocess
import threading
import time
import unicodedata
from collections.abc import Callable, Iterable
from concurrent.futures import Future, ThreadPoolExecutor
from multiprocessing import Pool
from typing import Any, TypeVar

from gitstats import load_config
from gitstats.assistants import AssistedCommit, assisted_commits
from gitstats.employers import BOT, ORGANIZATION, Affiliation, classify
from gitstats.sources import is_source
from gitstats.utils import (
    SOURCE_LINES_LOG,
    WEEK_KEY,
    History,
    commit_local_time,
    commits_reached,
    count_files_in_trees,
    count_lines_in_blobs,
    get_commit_range,
    get_keys_sorted_by_value_key,
    get_log_range,
    get_num_of_files_from_rev,
    get_pipe_output,
    get_stat_summary_counts,
    history_graph,
    shortstat_logs,
    should_exclude_file,
    source_lines_added,
    unquote_path,
)

os.environ["LC_ALL"] = "C"


def _set_git_config(settings: dict[str, str]) -> None:
    """Have every git process gitstats starts read these settings, whatever
    the user's git configuration says, through the environment
    (GIT_CONFIG_COUNT, git 2.31 and later), after any already there."""
    try:
        count = int(os.environ.get("GIT_CONFIG_COUNT", "0"))
    except ValueError:
        count = 0
    for key, value in settings.items():
        os.environ[f"GIT_CONFIG_KEY_{count}"] = key
        os.environ[f"GIT_CONFIG_VALUE_{count}"] = value
        count += 1
    os.environ["GIT_CONFIG_COUNT"] = str(count)


_set_git_config(
    {
        # a signature check printed into each commit's lines would be read as
        # data: as a file name, or as a line that cannot be parsed
        "log.showSignature": "false",
        # `git log --author` matches the names after .mailmap, which are the
        # names the report shows (it is the default, and a setting can turn it off)
        "log.mailmap": "true",
    }
)

# the line `git log --shortstat` writes under a commit: " 2 files changed, ..."
# (an author may be named "2 files changed", so the header is no such line)
_SHORTSTAT = re.compile(r"\s+\d+ files? changed")

logger = logging.getLogger("gitstats")

conf = load_config()


_T = TypeVar("_T")
_R = TypeVar("_R")


def parallel_map_with_fallback(func: Callable[[_T], _R], items: Iterable[_T]) -> list[_R]:
    """Apply a function to items using multiprocessing, with sequential fallback.

    Args:
        func: Function to apply to each item
        items: Iterable of items to process

    Returns:
        List of results from applying func to each item
    """
    try:
        pool = Pool(processes=conf["processes"])
        results = pool.map(func, items)
        pool.terminate()
        pool.join()
        return results
    except OSError as e:
        # Fallback to sequential processing if multiprocessing fails
        # (common in restricted environments like Netlify)
        logger.warning(
            f"Multiprocessing not available ({e}), falling back to sequential processing"
        )
        return [func(item) for item in items]


def _sample_evenly(items: list[str], k: int) -> list[str]:
    """Pick up to ``k`` items spread evenly across the list, order preserved."""
    if len(items) <= k:
        return list(items)
    step = len(items) / k
    return [items[int(i * step)] for i in range(k)]


def _merge_period_aliases(
    period_authors: dict[str, int], name_to_canonical: dict[str, str]
) -> None:
    """Fold aliased authors into their canonical name within one period.

    ``period_authors`` maps author -> commit count for a single month or year
    and is updated in place.
    """
    for alias, canonical in name_to_canonical.items():
        if alias in period_authors:
            period_authors[canonical] = period_authors.get(canonical, 0) + period_authors.pop(alias)


def _author_name(name: str) -> str:
    """An author's name the way the report keys it, wherever git printed it.

    In Unicode's composed form (NFC), so that an "ä" written as an "a" and a
    combining diaeresis is one name with the "ä" written as one character,
    and without the whitespace around it, a no-break space (U+00A0) or a
    line separator (U+2028) as much as a space.
    """
    return unicodedata.normalize("NFC", name).strip()


# The latest stamp datetime.fromtimestamp() takes in every time zone:
# 9999-12-01 00:00:00 UTC, or 3000-01-01 on Windows, whose clock ends there
_LATEST_STAMP = 32503680000 if os.name == "nt" else 253399622400


def _stamp(text: str) -> int:
    """A commit's stamp as git prints it (%at), no later than _LATEST_STAMP.

    git takes dates after the year 9999, which Python's datetime cannot hold:
    such a commit is counted at the latest moment it can.
    """
    return min(int(text), _LATEST_STAMP)


def _stamp_or_zero(text: str) -> int:
    """_stamp(), or 0 for a date git cannot read, which it prints as nothing."""
    try:
        return _stamp(text)
    except ValueError:
        return 0


class DataCollector:
    """Manages data collection from a revision control repository."""

    def __init__(self) -> None:
        self.stamp_created: float = time.time()
        self.cache: dict[str, Any] = {}
        self.total_authors: int = 0
        self.activity_by_hour_of_day: dict[int, int] = {}  # hour -> commits
        self.activity_by_day_of_week: dict[int, int] = {}  # day -> commits
        self.activity_by_month_of_year: dict[int, int] = {}  # month [1-12] -> commits
        self.activity_by_hour_of_week: dict[int, dict[int, int]] = {}  # weekday -> hour -> commits
        # the same grid for each year (the Wrapped card is about one year):
        # year -> weekday -> hour -> commits
        self.activity_by_hour_of_week_by_year: dict[int, dict[int, dict[int, int]]] = {}
        self.activity_by_hour_of_day_busiest: int = 0
        self.activity_by_hour_of_week_busiest: int = 0
        self.activity_by_year_week: dict[str, int] = {}  # ISO "YYYY-WW" -> commits
        self.activity_by_year_week_peak: int = 0

        self.authors: dict[str, dict[str, Any]] = {}  # name -> author stats

        self.total_commits: int = 0
        self.total_files: int = 0
        self.authors_by_commits: list[str] = []

        # domains
        self.domains: dict[str, dict[str, int]] = {}  # domain -> commits

        # organizations, by the domain of the author's address (see gitstats.employers)
        # domain -> { commits, first_commit_stamp, last_commit_stamp, by_month: {YYYY-MM: commits} }
        self.organizations: dict[str, dict[str, Any]] = {}
        self.organization_authors: dict[str, int] = {}  # domain -> how many addresses
        self.organization_people: dict[str, int] = {}  # domain -> how many author names
        # YYYY-MM -> kind of address (organization, personal, ...) -> commits
        self.affiliation_by_month: dict[str, dict[str, int]] = {}

        # the commits of people, bots left out: year -> commits, and the days
        # with one (bots that merge or sync every day fill a calendar)
        self.human_commits_by_year: dict[int, int] = {}
        self.human_active_days: set[str] = set()

        # lines of the project's own source (see gitstats.sources): ever added,
        # and in the last commit's files; None when they were not counted
        self.source_lines_added: int | None = None

        # author of the month
        self.author_of_month: dict[str, dict[str, int]] = {}  # month -> author -> commits
        self.author_of_year: dict[int, dict[str, int]] = {}  # year -> author -> commits
        self.commits_by_month: dict[str, int] = {}  # month -> commits
        self.commits_by_year: dict[int, int] = {}  # year -> commits
        self.lines_added_by_month: dict[str, int] = {}  # month -> lines added
        self.lines_added_by_year: dict[int, int] = {}  # year -> lines added
        self.lines_removed_by_month: dict[str, int] = {}  # month -> lines removed
        self.lines_removed_by_year: dict[int, int] = {}  # year -> lines removed
        self.first_commit_stamp: int = 0
        self.last_commit_stamp: int = 0
        self.last_active_day: str | None = None
        self.active_days: set[str] = set()
        self.longest_streak: int = 0  # longest consecutive active days streak
        # the commits of each day and the lines they changed ("YYYY-MM-DD" ->
        # count): what part of a year is compared with the same days of the
        # year before by, on a Wrapped card made before its year is over
        self.commits_by_day: dict[str, int] = {}
        self.lines_changed_by_day: dict[str, int] = {}

        # lines
        self.total_lines: int = 0
        self.total_lines_added: int = 0
        self.total_lines_removed: int = 0

        # size
        self.total_size: int = 0

        # timezone
        self.commits_by_timezone: dict[str, int] = {}  # timezone -> commits

        # tags
        self.tags: dict[str, dict[str, Any]] = {}

        self.files_by_stamp: dict[int, int] = {}  # stamp -> files

        # extensions
        self.extensions: dict[str, dict[str, int]] = {}  # extension -> files, lines

        # line statistics
        self.changes_by_date: dict[int, dict[str, int]] = {}  # stamp -> { files, ins, del }
        self.changes_by_date_by_author: dict[int, dict[str, dict[str, int]]] = {}

        # file churn: number of commits that touched each file path
        self.file_churn: dict[str, int] = {}  # filepath -> commit count

        # code ownership: author -> file path -> number of commits touching it
        self.author_files: dict[str, dict[str, int]] = {}

        # paths of the files at HEAD (ownership and churn skip deleted files)
        self.head_files: list[str] = []

        # hotspots: change frequency against size for each file at HEAD whose
        # lines are counted; filepath -> { lines, churn, score }
        self.hotspot_files: dict[str, dict[str, float]] = {}

        # evenly sampled commit subjects per year (collected only when AI
        # features are enabled; they ground the AI chronicle narration)
        self.commit_subjects_by_year: dict[int, list[str]] = {}

        # new contributors per month
        self.new_contributors_by_month: dict[str, int] = {}  # YYYY-MM -> count

        # Commits that name an AI coding assistant, as their author, as a
        # co-author or in the line it signs with (see gitstats.assistants).
        # A lower bound: an assistant that leaves no mark is not counted.
        self.ai_assisted_commits: int = 0
        # those of them an assistant made under its own account
        self.ai_assisted_authored: int = 0
        self.ai_assisted_by_month: dict[str, int] = {}  # YYYY-MM -> commits
        # assistant -> { commits, authored, first_commit_stamp, last_commit_stamp }
        self.ai_assistants: dict[str, dict[str, int]] = {}

        # AI summaries
        self.ai_summaries: dict[str, dict[str, Any]] = {}  # page_type -> {summary, error}

        # analyzed from a shallow clone: the report only covers the fetched history
        self.shallow: bool = False

    ##
    # This should be the main function to extract data from the repository.
    def collect(self, repo_dir: str) -> None:
        self.dir = repo_dir
        if len(conf["project_name"]) == 0:
            self.project_name = os.path.basename(os.path.abspath(repo_dir))
        else:
            self.project_name = conf["project_name"]

    ##
    # Load cacheable data
    def load_cache(self, cachefile: str) -> None:
        if not os.path.exists(cachefile):
            return
        logger.info("Loading cache...")
        try:
            with open(cachefile, encoding="utf-8") as f:
                self.cache = json.load(f)
        except ValueError:
            # Corrupted or legacy pickle cache - start fresh
            logger.warning("Warning: cache is corrupted, starting fresh")
            self.cache = {}

    def get_stamp_created(self) -> float:
        return self.stamp_created

    # Save cacheable data
    def save_cache(self, cachefile: str) -> None:
        logger.info("Saving cache...")
        tempfile = cachefile + ".tmp"
        with open(tempfile, "w", encoding="utf-8") as f:
            json.dump(self.cache, f)
        try:
            os.remove(cachefile)
        except OSError:
            pass
        os.rename(tempfile, cachefile)


class GitDataCollector(DataCollector):
    def collect(self, repo_dir: str) -> None:
        """Collect all statistics from the repository.

        Each phase below owns one slice of the data model; the only value
        passed between them is the author-alias mapping, which later phases
        need to attribute work to canonical identities.
        """
        DataCollector.collect(self, repo_dir)

        # CI checkouts are shallow by default (GitLab fetches 20 commits,
        # Bitbucket 50, actions/checkout 1), and every number in the report
        # would silently cover only those.
        shallow = get_pipe_output(["git rev-parse --is-shallow-repository"]).strip()
        self.shallow = shallow == "true"
        if self.shallow:
            logger.warning(
                "Warning: this is a shallow clone, so the report only covers the history "
                "that was fetched. Fetch all of it first with 'git fetch --unshallow', or in "
                "CI set GitHub Actions 'fetch-depth: 0', GitLab CI 'GIT_DEPTH: 0' or "
                "Bitbucket Pipelines 'clone: depth: full'."
            )

        # the names after .mailmap, as `git shortlog -s` gives them; git log, not
        # shortlog or rev-list, so that the authors filter matches those names
        # in every command (see get_log_range())
        names = get_pipe_output(['git log --format="%aN" {}'.format(get_log_range("HEAD", False))])
        self.total_authors += len({name for name in names.split("\n") if name})

        # Three phases read a `git log` of the whole history, two of them with
        # the line counts of every diff and the third with the names of the
        # files it changes: what is left of a run is mostly git working those
        # out. None of the three depends on the phases before it, so git
        # starts on them now and each phase parses its text when its turn
        # comes. A commit is compared with its parent once, for the three of
        # them, and from several git processes at a time (shortstat_logs()):
        # one fewer than `processes`, and than the machine has processors, so
        # that the phases below, which the run cannot go faster than, keep one
        # to themselves. A thread is enough here: it only waits for git. With
        # `processes = 1` the phases run their commands themselves, one after
        # the other.
        processes = min(int(conf["processes"]), os.cpu_count() or 1)
        line_stats: Future[tuple[list[str], dict[str, int], str | None]] | None = None
        assisted: Future[list[AssistedCommit]] | None = None
        # the lines ever added to the project's own source, which the same
        # diffs count file by file
        source_lines: list[int] = []
        # set when the phases have nothing left to do but wait for the line counts
        waiting = threading.Event()
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="git-log") as pool:
            if processes > 1:
                # the messages of every commit, read beside the rest: one quick `git log`
                assisted = pool.submit(self._assisted_commits)
                line_stats = pool.submit(
                    shortstat_logs,
                    self._line_stat_passes(),
                    get_log_range("HEAD", False),
                    processes - 1,
                    waiting,
                    self.CHURN_FORMAT,
                    is_source,
                    source_lines,
                )

            # The history that leads to the end of the range, read once and
            # when a phase first asks for it: the tags and the files of each
            # commit are both worked out from it.
            read: list[History] = []

            def history() -> History:
                if not read:
                    read.append(history_graph(get_commit_range("HEAD", end_only=True)))
                return read[0]

            # What the line counts give when they are in: the text of each of
            # the two walks, the files each commit adds, and the text with
            # the names of the files each commit changes. None leaves a phase
            # to ask git itself.
            counted: list[tuple[list[str | None], dict[str, int] | None, str | None]] = []

            def line_counts() -> tuple[list[str | None], dict[str, int] | None, str | None]:
                if not counted:
                    counted.append(([None, None], None, None))
                    if line_stats is not None:
                        # no processor needs sparing for the phases any more
                        waiting.set()
                        try:
                            texts, added, names = line_stats.result()
                            counted[0] = (list(texts), added, names)
                        except (OSError, subprocess.CalledProcessError) as error:
                            logger.debug(
                                f"Could not spread the line counts over git processes: {error}"
                            )
                return counted[0]

            self._collect_tags(history)
            identities = self._collect_commit_stats()
            name_to_canonical = self._merge_author_aliases(identities)
            self._collect_extensions()
            # after the others: it waits for the line counts, which say what
            # files each commit adds
            self._collect_files_by_stamp(history, lambda: line_counts()[1])

            outputs, _, changed = line_counts()
            self._collect_line_stats(outputs[0])
            outputs[0] = None  # let go of the text once its phase has read it
            self._collect_per_author_line_stats(name_to_canonical, outputs[1])
            outputs[1] = None
            self._collect_file_churn_and_ownership(name_to_canonical, changed)
            self._collect_ai_assisted(assisted.result() if assisted is not None else None)
            # counted with the others, or, without them, by a walk of its own
            self.source_lines_added = source_lines[0] if source_lines else self._source_lines()
        if conf["ai_enabled"]:
            self._collect_commit_subjects()

    # ── collection phases ────────────────────────────────────────────────

    def _collect_tags(self, history: Callable[[], History] | None = None) -> None:
        """Populate ``tags`` with each tag's date, commit count and authors.

        Only tags whose commit is reachable within the configured commit range
        are included. ``history`` gives the history that leads to the end of
        the range when collect() shares one reading of it between phases.
        """
        # --topo-order: never list a commit before its descendants, so the order
        # below follows the history even when commit dates are skewed. Which
        # tags are in the report does not depend on the authors filter: a tag
        # on another author's commit is still a release, credited with the
        # filtered authors' commits since the one before.
        tag_commits = (
            get_pipe_output(
                [
                    f'git log --topo-order --format="%H" {get_log_range("HEAD", False, authors=False)}'
                ]
            )
            .strip()
            .split("\n")
        )
        tag_commits_set = set(tag_commits) if tag_commits[0] else set()
        if load_config()["authors"]:
            counted = get_pipe_output(
                [f'git log --format="%H" {get_log_range("HEAD", False)}']
            ).split("\n")
            counted_set = {commit for commit in counted if commit}
        else:
            counted_set = tag_commits_set

        # An annotated tag is listed with the hash of the tag object; --dereference
        # adds a "<tag>^{}" line with the commit it points to, which is the one
        # that can be found in the commit range.
        tag_hashes: dict[str, str] = {}
        lines = get_pipe_output(["git show-ref --tags --dereference"]).split("\n")
        for line in lines:
            if len(line) == 0:
                continue
            (hash, ref) = line.split(" ", 1)
            tag = ref.replace("refs/tags/", "")
            if tag.endswith("^{}"):
                tag_hashes[tag[: -len("^{}")]] = hash
            else:
                tag_hashes.setdefault(tag, hash)

        # Only the tags whose commit is in our range are included
        tag_hashes = {tag: hash for tag, hash in tag_hashes.items() if hash in tag_commits_set}
        if not tag_hashes:
            return

        # The date of each tag and the commits it adds to the tag before it
        # come from the history read once, with what joins its commits. Asking
        # git for each tag took two processes per tag: most of a run on a
        # small repository, and half a minute on one with a thousand tags.
        # The whole history that leads to the end of the range is read, not
        # the range: a tag's commits are found by walking back from it, which
        # the date and author filters would leave holes in.
        graph = history() if history else history_graph(get_commit_range("HEAD", end_only=True))
        place, parents, headers = graph.place, graph.parents, graph.headers
        # the commits counted: those of the range, by the filtered authors
        in_range = [False] * len(parents)
        for commit in counted_set:
            if commit in place:
                in_range[place[commit]] = True

        for tag, hash in tag_hashes.items():
            if hash not in place:
                continue
            stamp = 0
            try:
                stamp = _stamp(headers[place[hash]].partition(" ")[0])
            except ValueError:
                stamp = 0
            self.tags[tag] = {
                "stamp": stamp,
                "hash": hash,
                "date": datetime.datetime.fromtimestamp(stamp).strftime("%Y-%m-%d"),
                "commits": 0,
                "authors": {},
            }

        # Walk the tags oldest first, so each one is credited with the commits
        # added since the previous tag. The order comes from the history itself:
        # rev-list --topo-order lists descendants before their ancestors, so a
        # larger index is an older commit (by default rev-list sorts on commit
        # dates, which a skewed clock can put out of history order). Sorting
        # on the "%Y-%m-%d" date instead broke the tie between two tags of the
        # same day by tag name, and a newer tag sorted first took the older
        # tag's commits, leaving the older one with none.
        commit_order = {commit: index for index, commit in enumerate(tag_commits)}
        # Keep the position so the report can present tags in the same order,
        # rather than re-deriving one from the date string.
        for info in self.tags.values():
            info["order"] = commit_order.get(info["hash"], 0)
        tags_oldest_first = [
            tag
            for _, tag in sorted(
                (-commit_order.get(info["hash"], 0), tag) for tag, info in self.tags.items()
            )
        ]
        prev: int | None = None
        for tag in tags_oldest_first:
            tip = place[self.tags[tag]["hash"]]
            # The commits that lead to this tag and not to the one before
            # (`git log <tag> ^<prev>`). Of those, keep the commits of our
            # range, which also applies the date and author filters.
            counts: dict[str, int] = {}
            for reached in commits_reached(parents, tip, prev):
                if in_range[reached]:
                    author = _author_name(headers[reached].partition(" ")[2])
                    counts[author] = counts.get(author, 0) + 1
            if not counts:
                continue
            prev = tip
            for author, commits in counts.items():
                self.tags[tag]["commits"] += commits
                self.tags[tag]["authors"][author] = commits

    def _collect_commit_stats(self) -> dict[tuple[str, str], int]:
        """Walk every commit, accumulating activity, domain and author stats.

        Returns what resolves author identities (see _merge_author_aliases()):
        ``(author name, email) -> the stamp of its latest commit``.
        """
        # Outputs "<stamp> <date> <time> <timezone> <author> '<' <mail> '>'"
        lines = get_pipe_output(
            ['git log --format="%at %ai %aN <%aE>" {}'.format(get_log_range("HEAD", False))]
        ).split("\n")
        # the names and addresses used together, to merge the identities of one person
        identities: dict[tuple[str, str], int] = {}  # (name, email) -> latest stamp
        # the earliest stamp; None until there is one, as 0 is a commit at the epoch
        first_stamp: int | None = None
        # the addresses and names of each organization, to count them: only the counts are kept
        addresses: dict[str, set[str]] = {}
        names: dict[str, set[str]] = {}
        for line in lines:
            # Skip empty lines (happens when there are no commits in the date range)
            if not line.strip():
                continue
            parts = line.split(" ", 4)
            # Skip lines that don't have enough parts
            if len(parts) < 5:
                continue
            author = ""
            try:
                stamp = _stamp(parts[0])
            except ValueError:
                stamp = 0
            timezone = parts[3]
            author, mail = parts[4].split("<", 1)
            author = _author_name(author)
            mail = mail.rstrip(">")
            domain = "?"
            if mail.find("@") != -1:
                # MIT.EDU and mit.edu are one domain
                domain = mail.rsplit("@", 1)[1].strip().lower()
            date = datetime.datetime.fromtimestamp(float(stamp))

            # Track name<->email pairs to later resolve identity aliases
            identities[author, mail] = max(identities.get((author, mail), stamp), stamp)

            # First and last commit stamp (may be in any order because of cherry-picking and patches)
            if stamp > self.last_commit_stamp:
                self.last_commit_stamp = stamp
            if first_stamp is None or stamp < first_stamp:
                first_stamp = stamp

            self._record_activity(date, commit_local_time(stamp, timezone))

            # domain stats
            if domain not in self.domains:
                self.domains[domain] = {}
            # commits
            self.domains[domain]["commits"] = self.domains[domain].get("commits", 0) + 1

            self._record_author_commit(author, stamp, date)
            affiliation = self._record_affiliation(author, mail, stamp, date)
            if affiliation.kind != BOT:
                self.human_commits_by_year[date.year] = (
                    self.human_commits_by_year.get(date.year, 0) + 1
                )
                self.human_active_days.add(date.strftime("%Y-%m-%d"))
            organization = affiliation.organization
            if organization:
                addresses.setdefault(organization, set()).add(mail.strip().lower())
                names.setdefault(organization, set()).add(" ".join(author.lower().split()))

            # timezone
            self.commits_by_timezone[timezone] = self.commits_by_timezone.get(timezone, 0) + 1

        if first_stamp is not None:
            self.first_commit_stamp = first_stamp
        self.organization_authors = {name: len(found) for name, found in addresses.items()}
        self.organization_people = {name: len(found) for name, found in names.items()}
        return identities

    def _record_affiliation(
        self, author: str, mail: str, stamp: int, date: datetime.datetime
    ) -> Affiliation:
        """Count a commit under the kind of its author's address, and under
        the organization when the address belongs to one. Returns where the
        address belongs."""
        month = date.strftime("%Y-%m")
        affiliation = classify(author, mail)
        kinds = self.affiliation_by_month.setdefault(month, {})
        kinds[affiliation.kind] = kinds.get(affiliation.kind, 0) + 1
        if affiliation.kind != ORGANIZATION:
            return affiliation
        info = self.organizations.setdefault(
            affiliation.organization,
            {"commits": 0, "first_commit_stamp": stamp, "last_commit_stamp": stamp, "by_month": {}},
        )
        info["commits"] += 1
        info["first_commit_stamp"] = min(info["first_commit_stamp"], stamp)
        info["last_commit_stamp"] = max(info["last_commit_stamp"], stamp)
        info["by_month"][month] = info["by_month"].get(month, 0) + 1
        return affiliation

    def _record_activity(
        self, date: datetime.datetime, local: datetime.datetime | None = None
    ) -> None:
        """Accumulate the time-of-commit histograms for a single commit.

        ``date`` is the commit on this machine's clock, and decides which
        month, week and year it is counted in, like the rest of the report.
        ``local`` is the same moment on the committer's clock (the commit's
        own UTC offset) and decides the hour and the day of the week: a
        commit made at 23:00 in Tokyo is a late-evening commit wherever the
        report is generated. Without it, ``date`` stands in for both.
        """
        local = local or date
        # hour
        hour = local.hour
        self.activity_by_hour_of_day[hour] = self.activity_by_hour_of_day.get(hour, 0) + 1
        # most active hour?
        if self.activity_by_hour_of_day[hour] > self.activity_by_hour_of_day_busiest:
            self.activity_by_hour_of_day_busiest = self.activity_by_hour_of_day[hour]

        # day of week
        day = local.weekday()
        self.activity_by_day_of_week[day] = self.activity_by_day_of_week.get(day, 0) + 1

        # hour of week
        if day not in self.activity_by_hour_of_week:
            self.activity_by_hour_of_week[day] = {}
        self.activity_by_hour_of_week[day][hour] = (
            self.activity_by_hour_of_week[day].get(hour, 0) + 1
        )
        # most active hour?
        if self.activity_by_hour_of_week[day][hour] > self.activity_by_hour_of_week_busiest:
            self.activity_by_hour_of_week_busiest = self.activity_by_hour_of_week[day][hour]

        # hour of week, for the year the commit is counted in
        year_hours = self.activity_by_hour_of_week_by_year.setdefault(date.year, {}).setdefault(
            day, {}
        )
        year_hours[hour] = year_hours.get(hour, 0) + 1

        # month of year
        month = date.month
        self.activity_by_month_of_year[month] = self.activity_by_month_of_year.get(month, 0) + 1

        # yearly/weekly activity
        # the ISO week, which starts on a Monday and is one week across New
        # Year: "%Y-%W" kept Dec 30, 2024 and Jan 2, 2025 under 2024-53 and 2025-00
        yyw = date.strftime(WEEK_KEY)
        self.activity_by_year_week[yyw] = self.activity_by_year_week.get(yyw, 0) + 1
        if self.activity_by_year_week_peak < self.activity_by_year_week[yyw]:
            self.activity_by_year_week_peak = self.activity_by_year_week[yyw]

    def _record_author_commit(self, author: str, stamp: int, date: datetime.datetime) -> None:
        """Accumulate per-author and per-period stats for a single commit."""
        # author stats
        if author not in self.authors:
            self.authors[author] = {}
        # commits, note again that commits may be in any date order because of cherry-picking and patches
        if "last_commit_stamp" not in self.authors[author]:
            self.authors[author]["last_commit_stamp"] = stamp
        if stamp > self.authors[author]["last_commit_stamp"]:
            self.authors[author]["last_commit_stamp"] = stamp
        if "first_commit_stamp" not in self.authors[author]:
            self.authors[author]["first_commit_stamp"] = stamp
        if stamp < self.authors[author]["first_commit_stamp"]:
            self.authors[author]["first_commit_stamp"] = stamp

        # author of the month/year
        yymm = date.strftime("%Y-%m")
        if yymm in self.author_of_month:
            self.author_of_month[yymm][author] = self.author_of_month[yymm].get(author, 0) + 1
        else:
            self.author_of_month[yymm] = {}
            self.author_of_month[yymm][author] = 1
        self.commits_by_month[yymm] = self.commits_by_month.get(yymm, 0) + 1

        yy = date.year
        if yy in self.author_of_year:
            self.author_of_year[yy][author] = self.author_of_year[yy].get(author, 0) + 1
        else:
            self.author_of_year[yy] = {}
            self.author_of_year[yy][author] = 1
        self.commits_by_year[yy] = self.commits_by_year.get(yy, 0) + 1

        # authors: active days
        yymmdd = date.strftime("%Y-%m-%d")
        self.commits_by_day[yymmdd] = self.commits_by_day.get(yymmdd, 0) + 1
        if "last_active_day" not in self.authors[author]:
            self.authors[author]["last_active_day"] = yymmdd
            self.authors[author]["active_days"] = set([yymmdd])
        elif yymmdd != self.authors[author]["last_active_day"]:
            self.authors[author]["last_active_day"] = yymmdd
            self.authors[author]["active_days"].add(yymmdd)

        # project: active days
        if yymmdd != self.last_active_day:
            self.last_active_day = yymmdd
            self.active_days.add(yymmdd)

    def _merge_author_aliases(self, identities: dict[tuple[str, str], int]) -> dict[str, str]:
        """Fold the names of one person into one canonical identity.

        ``identities`` maps each ``(name, email)`` used together in a commit
        to the stamp of the latest such commit. Two names used with one
        email are one person, and so are two emails used with one name,
        however long the chain (jdoe and "John Doe" at work, "John Doe" and
        "John D." at home): the names and emails are grouped by union-find,
        whatever order the commits come in. A group goes by the name of its
        most recent commit.

        Merges the alias entries in ``authors``, the per-period author dicts and
        the tag author dicts, then returns the ``alias -> canonical`` mapping so
        later phases can attribute their data to the same identities.
        """
        # name or email -> the one it was joined to; a group's root is its own
        joined: dict[tuple[str, str], tuple[str, str]] = {}

        def root(node: tuple[str, str]) -> tuple[str, str]:
            joined.setdefault(node, node)
            while joined[node] != node:
                joined[node] = joined[joined[node]]  # halve the way for next time
                node = joined[node]
            return node

        newest: dict[str, tuple[int, str]] = {}  # name -> (latest stamp, name)
        for (name, mail), stamp in identities.items():
            newest[name] = max(newest.get(name, (stamp, name)), (stamp, name))
            group = root(("name", name))
            if mail:
                joined[group] = root(("email", mail))
        named: dict[tuple[str, str], tuple[int, str]] = {}  # group -> its most recent name
        for name, latest in newest.items():
            group = root(("name", name))
            named[group] = max(named.get(group, latest), latest)
        name_to_canonical: dict[str, str] = {}
        for name in newest:
            canonical = named[root(("name", name))][1]
            if canonical != name:
                name_to_canonical[name] = canonical

        # Merge aliased author entries into their canonical entries
        for alias, canonical in name_to_canonical.items():
            if alias not in self.authors:  # pragma: no cover - each alias is popped once
                continue
            if canonical not in self.authors:
                self.authors[canonical] = self.authors.pop(alias)
                continue
            ca = self.authors[canonical]
            aa = self.authors.pop(alias)
            ca["commits"] = ca.get("commits", 0) + aa.get("commits", 0)
            ca["lines_added"] = ca.get("lines_added", 0) + aa.get("lines_added", 0)
            ca["lines_removed"] = ca.get("lines_removed", 0) + aa.get("lines_removed", 0)
            if "first_commit_stamp" in aa and (
                "first_commit_stamp" not in ca
                or aa["first_commit_stamp"] < ca["first_commit_stamp"]
            ):
                ca["first_commit_stamp"] = aa["first_commit_stamp"]
            if "last_commit_stamp" in aa and aa.get("last_commit_stamp", 0) > ca.get(
                "last_commit_stamp", 0
            ):
                ca["last_commit_stamp"] = aa["last_commit_stamp"]
            if "active_days" in aa:
                ca.setdefault("active_days", set()).update(aa["active_days"])
            if "last_active_day" in aa:
                ca["last_active_day"] = max(ca.get("last_active_day", ""), aa["last_active_day"])

        # Merge aliases in time-based author dicts. The two dicts are keyed
        # differently (month string vs. year int) but their values share one
        # shape, so the merge works on the inner author->commits dicts.
        for period_authors in (*self.author_of_month.values(), *self.author_of_year.values()):
            _merge_period_aliases(period_authors, name_to_canonical)

        # Merge aliases in tag author dicts
        for tag in self.tags:
            merged_authors: dict[str, int] = {}
            for author, commits in self.tags[tag]["authors"].items():
                resolved = name_to_canonical.get(author, author)
                merged_authors[resolved] = merged_authors.get(resolved, 0) + commits
            self.tags[tag]["authors"] = merged_authors

        # Update total_authors to reflect merged identities
        self.total_authors = len(self.authors)

        return name_to_canonical

    def _collect_files_by_stamp(
        self,
        history: Callable[[], History] | None = None,
        added: Callable[[], dict[str, int] | None] | None = None,
    ) -> None:
        """Record the file count of every revision, using the blob cache.

        ``history`` gives the history that leads to the end of the range when
        collect() shares one reading of it between phases. ``added`` gives
        the files each commit adds, less those it deletes, as the line counts
        found them (see shortstat_logs()), or None when they did not; it may
        wait for those counts to be in.
        """
        # outputs "<stamp> <files>" for each revision
        revlines = (
            get_pipe_output(['git log --format="%at %T" {}'.format(get_log_range("HEAD", False))])
            .strip()
            .split("\n")
        )
        revlines = [line for line in revlines if line.strip()]
        if not revlines:
            raise RuntimeError(
                "No commits to analyze. The repository is empty, or no commit"
                " matches the configured start_date, end_date, authors or"
                " commit range."
            )
        lines = []
        revs_to_read = []
        # Take the count of a tree from the cache if it is there; the others
        # are counted below
        files_in_tree = self.cache.setdefault("files_in_tree", {})
        for revline in revlines:
            # a date git cannot read prints as nothing: such a commit is counted at 0
            time, _, rev = revline.rpartition(" ")
            time = str(_stamp_or_zero(time.strip()))
            if rev in files_in_tree:
                lines.append("%d %d" % (int(time), files_in_tree[rev]))
            else:
                revs_to_read.append((time, rev))

        if revs_to_read:
            # They are counted from what each commit added to and deleted from
            # its parent. Listing the tree of every commit instead takes a
            # process per commit, and time that grows with commits x files:
            # most of an hour on a large repository.
            wanted = {rev for _, rev in revs_to_read}
            graph = history() if history else history_graph(get_commit_range("HEAD", end_only=True))
            # The line counts have had git compare nearly every commit with
            # its parent already, and say what files each one added: git is
            # asked again only about the commits they leave out.
            files_added = added() if added else None
            counted = count_files_in_trees(graph, wanted, files_in_tree, files_added)
            if files_added and counted:
                # What the line counts say rests on how git shows a diff, which
                # a configuration can change. The newest tree is listed to make
                # sure of it: its count has all the others behind it.
                _, newest = revs_to_read[0]
                if counted.get(newest) != get_num_of_files_from_rev(("0", newest))[2]:
                    logger.debug("The files added by each commit do not add up: asking git again")
                    counted = count_files_in_trees(graph, wanted, files_in_tree)
            # the trees of the ancestors counted on the way are kept as well
            files_in_tree.update(counted)
            # whatever that could not find is listed, a tree at a time
            left = [(time, rev) for time, rev in revs_to_read if rev not in counted]
            if left:
                for _, rev, count in parallel_map_with_fallback(get_num_of_files_from_rev, left):
                    files_in_tree[rev] = count
            for time, rev in revs_to_read:
                lines.append("%d %d" % (int(time), files_in_tree[rev]))

        self.total_commits += len(lines)
        for line in lines:
            parts = line.split(" ")
            if len(parts) != 2:  # pragma: no cover - lines are built as "%d %d" above
                continue
            (stamp, files) = parts[0:2]
            try:
                self.files_by_stamp[_stamp(stamp)] = int(files)
            except ValueError:  # pragma: no cover - lines are built as "%d %d" above
                logger.warning(f'Failed to parse line "{line}"')

    def _collect_extensions(self) -> None:
        """Count files, total size and lines per file extension at HEAD."""
        # extensions and size of files
        lines = get_pipe_output(
            [
                "git ls-tree -r -l -z --end-of-options {}".format(
                    shlex.quote(get_commit_range("HEAD", end_only=True))
                )
            ]
        ).split("\000")
        blobs_to_read = []
        # (path, blob id, extension) of every file whose lines are counted
        counted_files: list[tuple[str, str, str]] = []
        lines_in_blob = self.cache.setdefault("lines_in_blob", {})
        for line in lines:
            if len(line) == 0:
                continue
            # "<mode> <type> <object> <size>\t<path>": the path is all that
            # follows the tab, spaces at its start included
            meta, fullpath = line.split("\t", 1)
            parts = meta.split()
            if parts[1] == "commit":
                # skip submodules
                continue
            blob_id = parts[2]
            size = int(parts[3])

            self.total_size += size
            self.total_files += 1
            self.head_files.append(fullpath)

            filename = fullpath.split("/")[-1]  # strip directories
            # "" for a file without an extension (Makefile, .gitignore), or
            # with one too long to be one: the report's "no extension" row
            ext = ""
            if filename.find(".") != -1 and filename.rfind(".") != 0:
                ext = filename[(filename.rfind(".") + 1) :]
                if len(ext) > conf["max_ext_length"]:
                    ext = ""

                # Skip excluded files completely
                if should_exclude_file(ext):
                    continue

            if ext not in self.extensions:
                self.extensions[ext] = {"files": 0, "lines": 0}
            self.extensions[ext]["files"] += 1
            counted_files.append((fullpath, blob_id, ext))
            # the line count of a blob comes from the cache if it is there
            if blob_id not in lines_in_blob:
                blobs_to_read.append(blob_id)

        # One git process reads the blobs the cache does not have, where two
        # processes per blob took minutes on a tree of tens of thousands of files
        lines_in_blob.update(count_lines_in_blobs(blobs_to_read))

        # The lines of code are those of these files: what the diffs add up
        # to would count the excluded files, and only the commits that the
        # date, author and range filters leave. Per-file line counts go to
        # the hotspot analysis; refine() adds each file's churn and score.
        for fullpath, blob_id, ext in counted_files:
            lines = lines_in_blob[blob_id]
            self.total_lines += lines
            self.extensions[ext]["lines"] += lines
            self.hotspot_files[fullpath] = {"lines": lines, "churn": 0, "score": 0.0}

    @staticmethod
    def _line_stat_passes() -> list[tuple[str, bool]]:
        """The two walks of the history that have the lines of every diff counted.

        As shortstat_logs() takes them: the options that pick and order the
        commits, and whether a merge is compared with its first parent. The
        first is that of _collect_line_stats(), the second that of
        _collect_per_author_line_stats().
        """
        # computation of lines of code by date is better done
        # on a linear history.
        linear = bool(conf["linear_linestats"])
        return [("--first-parent" if linear else "", linear), ("--date-order", False)]

    @classmethod
    def _line_stats_command(cls) -> str:
        """The `git log` that _collect_line_stats() reads."""
        walk, first_parent = cls._line_stat_passes()[0]
        return 'git log --root --shortstat {} --pretty=format:"%at %aN" {}'.format(
            walk + (" -m" if first_parent else ""), get_log_range("HEAD", False)
        )

    @classmethod
    def _author_line_stats_command(cls) -> str:
        """The `git log` that _collect_per_author_line_stats() reads."""
        walk, _ = cls._line_stat_passes()[1]
        return 'git log --root --shortstat {} --pretty=format:"%at %aN" {}'.format(
            walk, get_log_range("HEAD", False)
        )

    # the line that starts a commit in what _collect_file_churn_and_ownership() reads
    CHURN_FORMAT = "COMMIT:%aN"

    @classmethod
    def _churn_command(cls) -> str:
        """The `git log` that _collect_file_churn_and_ownership() reads: the
        paths as they are, but for those git always quotes (see unquote_path())."""
        return 'git -c core.quotePath=false log --root --format="{}" --name-only {}'.format(
            cls.CHURN_FORMAT, get_log_range("HEAD", False)
        )

    def _collect_line_stats(self, output: str | None = None) -> None:
        """Record lines added/removed over time (``changes_by_date``).

        Computed on a linear history when ``linear_linestats`` is enabled, since
        lines-of-code over time is better measured along the mainline.
        ``output`` is that of _line_stats_command() when collect() has already
        run it.
        """
        # line statistics
        # outputs:
        #  N files changed, N insertions (+), N deletions(-)
        # <stamp> <author>
        self.changes_by_date = {}  # stamp -> { files, ins, del }
        if output is None:
            output = get_pipe_output([self._line_stats_command()])
        lines = output.split("\n")
        lines.reverse()
        files = 0
        inserted = 0
        deleted = 0
        total_lines = 0
        for line in lines:
            if len(line) == 0:
                continue

            # <stamp> <author>; only the stamp matters here, the author is
            # attributed in _collect_per_author_line_stats
            if _SHORTSTAT.match(line) is None:
                pos = line.find(" ")
                if pos != -1:
                    try:
                        stamp = _stamp(line[:pos])
                        self.changes_by_date[stamp] = {
                            "files": files,
                            "ins": inserted,
                            "del": deleted,
                            "lines": total_lines,
                        }

                        date = datetime.datetime.fromtimestamp(stamp)
                        yymm = date.strftime("%Y-%m")
                        self.lines_added_by_month[yymm] = (
                            self.lines_added_by_month.get(yymm, 0) + inserted
                        )
                        self.lines_removed_by_month[yymm] = (
                            self.lines_removed_by_month.get(yymm, 0) + deleted
                        )

                        yy = date.year
                        self.lines_added_by_year[yy] = (
                            self.lines_added_by_year.get(yy, 0) + inserted
                        )
                        self.lines_removed_by_year[yy] = (
                            self.lines_removed_by_year.get(yy, 0) + deleted
                        )

                        day = date.strftime("%Y-%m-%d")
                        self.lines_changed_by_day[day] = (
                            self.lines_changed_by_day.get(day, 0) + inserted + deleted
                        )

                        files, inserted, deleted = 0, 0, 0
                    except ValueError:
                        logger.warning(f'Unexpected line "{line}"')
                else:
                    logger.warning(f'Unexpected line "{line}"')
            else:
                numbers = get_stat_summary_counts(line)

                if len(numbers) == 3:
                    (files, inserted, deleted) = [int(el) for el in numbers]
                    total_lines += inserted
                    total_lines -= deleted
                    self.total_lines_added += inserted
                    self.total_lines_removed += deleted

                else:
                    logger.warning(f'Failed to handle line "{line}"')
                    (files, inserted, deleted) = (0, 0, 0)

    def _collect_per_author_line_stats(
        self, name_to_canonical: dict[str, str], output: str | None = None
    ) -> None:
        """Record each author's commits and line counts over time.

        Unlike :meth:`_collect_line_stats` this never uses ``--first-parent``:
        every commit must be walked to know who committed what, not just the
        mainline. ``output`` is that of _author_line_stats_command() when
        collect() has already run it.
        """
        # defined for stamp, author only if author committed at this timestamp.
        self.changes_by_date_by_author = {}  # stamp -> author -> lines_added

        if output is None:
            output = get_pipe_output([self._author_line_stats_command()])
        lines = output.split("\n")
        lines.reverse()
        inserted = 0
        deleted = 0
        author = None
        stamp = 0
        for line in lines:
            if len(line) == 0:
                continue

            # <stamp> <author>
            if _SHORTSTAT.match(line) is None:
                pos = line.find(" ")
                if pos != -1:
                    try:
                        oldstamp = stamp
                        (stamp, author) = (_stamp(line[:pos]), _author_name(line[pos + 1 :]))
                        author = name_to_canonical.get(author, author)
                        if oldstamp > stamp:
                            # clock skew, keep old timestamp to avoid having ugly graph
                            stamp = oldstamp
                        if author not in self.authors:
                            self.authors[author] = {
                                "lines_added": 0,
                                "lines_removed": 0,
                                "commits": 0,
                            }
                        self.authors[author]["commits"] = self.authors[author].get("commits", 0) + 1
                        self.authors[author]["lines_added"] = (
                            self.authors[author].get("lines_added", 0) + inserted
                        )
                        self.authors[author]["lines_removed"] = (
                            self.authors[author].get("lines_removed", 0) + deleted
                        )
                        if stamp not in self.changes_by_date_by_author:
                            self.changes_by_date_by_author[stamp] = {}
                        if author not in self.changes_by_date_by_author[stamp]:
                            self.changes_by_date_by_author[stamp][author] = {}
                        self.changes_by_date_by_author[stamp][author]["lines_added"] = self.authors[
                            author
                        ]["lines_added"]
                        self.changes_by_date_by_author[stamp][author]["commits"] = self.authors[
                            author
                        ]["commits"]
                        inserted, deleted = 0, 0
                    except ValueError:
                        logger.warning(f'Unexpected line "{line}"')
                else:
                    logger.warning(f'Unexpected line "{line}"')
            else:
                numbers = get_stat_summary_counts(line)

                if len(numbers) == 3:
                    # the file count is unused here; only line deltas matter
                    (_, inserted, deleted) = [int(el) for el in numbers]
                else:
                    logger.warning(f'Failed to handle line "{line}"')
                    (inserted, deleted) = (0, 0)

    def _collect_file_churn_and_ownership(
        self, name_to_canonical: dict[str, str], output: str | None = None
    ) -> None:
        """Record how often each file changes and who changes it.

        A single name-only pass drives two metrics:
        ``file_churn`` (commits touching each file) and ``author_files``
        (which files each author touches, for code ownership). Each commit is
        prefixed with a ``COMMIT:<author>`` marker line; the lines that follow
        are the file paths changed by that commit. Authors are resolved to their
        canonical identity so aliases merge here directly. ``output`` is that of
        _churn_command() when collect() has it already, from the diffs that
        count the lines (see shortstat_logs()).
        """
        if output is None:
            output = get_pipe_output([self._churn_command()])
        current_author = None
        for line in output.split("\n"):
            if not line:
                continue
            if line.startswith("COMMIT:"):
                name = _author_name(line[7:])
                current_author = name_to_canonical.get(name, name)
                continue
            # A changed-file line: the path, as the files at HEAD have it
            path = unquote_path(line)
            self.file_churn[path] = self.file_churn.get(path, 0) + 1
            if current_author:
                author_map = self.author_files.setdefault(current_author, {})
                author_map[path] = author_map.get(path, 0) + 1

    @staticmethod
    def _source_lines_command() -> str:
        """What counts the lines ever added to the project's own source, when
        the diffs of the line counts did not (see shortstat_logs())."""
        return f"git {SOURCE_LINES_LOG} {get_log_range('HEAD', False)}"

    def _source_lines(self) -> int | None:
        """The lines ever added to the project's own source, leaving out
        vendored dependencies, generated files, test fixtures and lock files
        (see gitstats.sources), by the rules of the count the diffs of the
        line counts make (see source_lines_added()); None when git could not
        count them."""
        try:
            return source_lines_added(get_pipe_output([self._source_lines_command()]), is_source)
        except (OSError, subprocess.CalledProcessError):
            return None

    @staticmethod
    def _assisted_commits() -> list[AssistedCommit]:
        """The commits of the range that name an AI coding assistant."""
        return list(assisted_commits(get_log_range("HEAD", False)))

    def _collect_ai_assisted(self, commits: list[AssistedCommit] | None = None) -> None:
        """Count the commits that name an AI coding assistant.

        By month, and by assistant: a commit that names two is counted under
        both, and once in the total. ``commits`` are those of
        _assisted_commits() when collect() has already asked for them.
        """
        if commits is None:
            commits = self._assisted_commits()
        for commit in commits:
            self.ai_assisted_commits += 1
            self.ai_assisted_authored += commit.authored
            yymm = datetime.datetime.fromtimestamp(min(commit.stamp, _LATEST_STAMP)).strftime(
                "%Y-%m"
            )
            self.ai_assisted_by_month[yymm] = self.ai_assisted_by_month.get(yymm, 0) + 1
            for place, name in enumerate(commit.assistants):
                info = self.ai_assistants.setdefault(
                    name,
                    {
                        "commits": 0,
                        "authored": 0,
                        "first_commit_stamp": commit.stamp,
                        "last_commit_stamp": commit.stamp,
                    },
                )
                info["commits"] += 1
                # the author, when it is an assistant, is the first one named
                info["authored"] += commit.authored and place == 0
                info["first_commit_stamp"] = min(info["first_commit_stamp"], commit.stamp)
                info["last_commit_stamp"] = max(info["last_commit_stamp"], commit.stamp)

    def _collect_commit_subjects(self) -> None:
        """Sample commit subjects per year to ground the AI chronicle.

        One subjects-only pass in chronological order; each year keeps an
        evenly spaced sample so the whole span stays represented no matter
        how large the repository is. Only runs when AI features are enabled.
        """
        output = get_pipe_output(
            ['git log --reverse --format="%at %s" {}'.format(get_log_range("HEAD", False))]
        )
        by_year: dict[int, list[str]] = {}
        for line in output.split("\n"):
            line = line.strip()
            if not line:
                continue
            pos = line.find(" ")
            if pos == -1:
                continue
            try:
                year = datetime.datetime.fromtimestamp(int(line[:pos])).year
            except ValueError:
                continue
            subject = line[pos + 1 :].strip()
            if subject:  # pragma: no branch - a stripped line has text after its space
                by_year.setdefault(year, []).append(subject[:100])

        self.commit_subjects_by_year = {
            year: _sample_evenly(subjects, 10) for year, subjects in by_year.items()
        }

    def refine(self) -> None:
        # authors
        # name -> {place_by_commits, commits_frac, date_first, date_last, timedelta}
        self.authors_by_commits = get_keys_sorted_by_value_key(self.authors, "commits")
        self.authors_by_commits.reverse()  # most first
        for i, name in enumerate(self.authors_by_commits):
            self.authors[name]["place_by_commits"] = i + 1

        for name in list(self.authors.keys()):
            a = self.authors[name]
            a["commits_frac"] = (100 * float(a["commits"])) / self.get_total_commits()
            date_first = datetime.datetime.fromtimestamp(a["first_commit_stamp"])
            date_last = datetime.datetime.fromtimestamp(a["last_commit_stamp"])
            delta = date_last - date_first
            a["date_first"] = date_first.strftime("%Y-%m-%d")
            a["date_last"] = date_last.strftime("%Y-%m-%d")
            a["timedelta"] = delta
            if "lines_added" not in a:
                a["lines_added"] = 0
            if "lines_removed" not in a:
                a["lines_removed"] = 0

        # Compute new contributors per month from author first-commit stamps
        for name in self.authors:
            a = self.authors[name]
            if "first_commit_stamp" in a:  # pragma: no branch - every author has one by now
                first_month = datetime.datetime.fromtimestamp(a["first_commit_stamp"]).strftime(
                    "%Y-%m"
                )
                self.new_contributors_by_month[first_month] = (
                    self.new_contributors_by_month.get(first_month, 0) + 1
                )

        # Compute longest consecutive active days streak
        self._compute_longest_streak()

        # Merge file churn into the hotspot data and score each file
        self._compute_hotspots()

    def _compute_longest_streak(self) -> None:
        """Compute longest consecutive active days streak."""
        dates = sorted(datetime.datetime.strptime(d, "%Y-%m-%d") for d in self.active_days)
        longest, current = 0, 0
        for i, d in enumerate(dates):
            if i == 0:
                current = 1
            else:
                diff = (d - dates[i - 1]).days
                current = current + 1 if diff <= 1 else 1
            longest = max(longest, current)
        self.longest_streak = longest

    def _compute_hotspots(self) -> None:
        """Give each hotspot file its churn and its score.

        The score is ``churn * sqrt(lines)``: it grows with both, so the files
        that are large and change often rank first, without size alone
        deciding the order.
        """
        for filepath, info in self.hotspot_files.items():
            churn = self.file_churn.get(filepath, 0)
            info["churn"] = churn
            info["score"] = churn * info["lines"] ** 0.5

    def get_active_days(self) -> set[str]:
        return self.active_days

    def get_longest_streak(self) -> int:
        return self.longest_streak

    def get_activity_by_day_of_week(self) -> dict[int, int]:
        return self.activity_by_day_of_week

    def get_activity_by_hour_of_day(self) -> dict[int, int]:
        return self.activity_by_hour_of_day

    def get_author_info(self, author: str) -> dict[str, Any]:
        return self.authors[author]

    def get_authors(self, limit: int | None = None) -> list[str]:
        res = get_keys_sorted_by_value_key(self.authors, "commits")
        res.reverse()
        return res[:limit]

    def get_commit_delta_days(self) -> float:
        return (self.last_commit_stamp / 86400 - self.first_commit_stamp / 86400) + 1

    def get_domain_info(self, domain: str) -> dict[str, int]:
        return self.domains[domain]

    def get_domains(self) -> list[str]:
        return list(self.domains.keys())

    def get_first_commit_date(self) -> datetime.datetime:
        return datetime.datetime.fromtimestamp(self.first_commit_stamp)

    def get_last_commit_date(self) -> datetime.datetime:
        return datetime.datetime.fromtimestamp(self.last_commit_stamp)

    def get_tags(self) -> list[str]:
        lines = get_pipe_output(["git show-ref --tags", "cut -d/ -f3"])
        return lines.split("\n")

    def get_tag_date(self, tag: str) -> str:
        return self.rev_to_date("tags/" + tag)

    def get_total_authors(self) -> int:
        return self.total_authors

    def get_total_commits(self) -> int:
        return self.total_commits

    def get_total_files(self) -> int:
        return self.total_files

    def get_total_loc(self) -> int:
        return self.total_lines

    def get_total_size(self) -> int:
        return self.total_size

    def rev_to_date(self, rev: str) -> str:
        stamp = int(get_pipe_output([f'git log --pretty=format:%at "{rev}" -n 1']))
        return datetime.datetime.fromtimestamp(stamp).strftime("%Y-%m-%d")
