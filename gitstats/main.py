# Copyright (c) 2007-2014 Heikki Hokkanen <hoxu@users.sf.net> & others contributors
# GPLv2 / GPLv3
# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
import argparse
import datetime
import json
import logging
import os
import re
import sys
import time
from multiprocessing import Pool
from typing import Any

from gitstats import exectime_external, load_config, time_start
from gitstats.ai_summarizer import AISummarizer
from gitstats.report_creator import HTMLReportCreator, get_keys_sorted_by_value_key
from gitstats.utils import (
    get_commit_range,
    get_log_range,
    get_num_of_files_from_rev,
    get_num_of_lines_in_blob,
    get_pipe_output,
    get_stat_summary_counts,
    get_version,
    should_exclude_file,
)

os.environ["LC_ALL"] = "C"

logger = logging.getLogger("gitstats")

conf = load_config()


def configure_logging(verbose: bool = False, quiet: bool = False) -> None:
    level = logging.INFO
    if verbose:
        level = logging.DEBUG
    elif quiet:
        level = logging.WARNING

    logging.basicConfig(
        level=level,
        format="%(message)s",
        stream=sys.stderr,
        force=True,
    )


def parallel_map_with_fallback(func, items):
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
        self.activity_by_hour_of_day_busiest: int = 0
        self.activity_by_hour_of_week_busiest: int = 0
        self.activity_by_year_week: dict[str, int] = {}  # yy_wNN -> commits
        self.activity_by_year_week_peak: int = 0

        self.authors: dict[str, dict[str, Any]] = {}  # name -> author stats

        self.total_commits: int = 0
        self.total_files: int = 0
        self.authors_by_commits: list[str] = []

        # domains
        self.domains: dict[str, dict[str, int]] = {}  # domain -> commits

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

        # new contributors per month
        self.new_contributors_by_month: dict[str, int] = {}  # YYYY-MM -> count

        # AI summaries
        self.ai_summaries: dict[str, dict[str, Any]] = {}  # page_type -> {summary, error}

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
        except (json.JSONDecodeError, ValueError):
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
    def collect(self, repo_dir):
        DataCollector.collect(self, repo_dir)

        self.total_authors += int(
            get_pipe_output(["git shortlog -s {}".format(get_log_range("HEAD", False)), "wc -l"])
        )
        # self.total_lines = int(getoutput('git-ls-files -z |xargs -0 cat |wc -l'))

        # tags
        # Only include tags that are reachable within the commit range
        log_range = get_log_range("HEAD", False)
        tag_commits = get_pipe_output([f"git rev-list {log_range}"]).strip().split("\n")
        tag_commits_set = set(tag_commits) if tag_commits[0] else set()

        lines = get_pipe_output(["git show-ref --tags"]).split("\n")
        for line in lines:
            if len(line) == 0:
                continue
            (hash, tag) = line.split(" ")

            # Only include tags whose commit is in our range
            if hash not in tag_commits_set:
                continue

            tag = tag.replace("refs/tags/", "")
            output = get_pipe_output([f'git log "{hash}" --pretty=format:"%at %aN" -n 1'])
            if len(output) > 0:
                parts = output.split(" ")
                stamp = 0
                try:
                    stamp = int(parts[0])
                except ValueError:
                    stamp = 0
                self.tags[tag] = {
                    "stamp": stamp,
                    "hash": hash,
                    "date": datetime.datetime.fromtimestamp(stamp).strftime("%Y-%m-%d"),
                    "commits": 0,
                    "authors": {},
                }

        # collect info on tags, starting from latest
        # Only collect statistics for commits within our range
        log_range = get_log_range("HEAD", False)
        tags_sorted_by_date_desc = [
            el[1]
            for el in reversed(sorted([(el[1]["date"], el[0]) for el in list(self.tags.items())]))
        ]
        prev = None
        for tag in reversed(tags_sorted_by_date_desc):
            # Modify command to only include commits within our range
            cmd = f'git shortlog -s "{tag}"'
            if prev is not None:
                cmd += f' "^{prev}"'
            # Intersect with our commit range and apply filters
            cmd += f" {log_range}"
            output = get_pipe_output([cmd])
            if len(output) == 0:
                continue
            prev = tag
            for line in output.split("\n"):
                if len(line.strip()) == 0:
                    continue
                parts = re.split(r"\s+", line, 2)
                if len(parts) < 3:
                    continue
                commits = int(parts[1])
                author = parts[2]
                self.tags[tag]["commits"] += commits
                self.tags[tag]["authors"][author] = commits

        # Collect revision statistics
        # Outputs "<stamp> <date> <time> <timezone> <author> '<' <mail> '>'"
        lines = get_pipe_output(
            [
                'git rev-list --pretty=format:"%at %ai %aN <%aE>" {}'.format(
                    get_log_range("HEAD", False)
                ),
                "grep -v ^commit",
            ]
        ).split("\n")
        # Track email<->author mappings to automatically merge identities that share an email
        email_to_latest: dict[str, tuple[int, str]] = {}  # email -> (stamp, author_name)
        author_to_email: dict[str, str] = {}  # author_name -> primary email
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
                stamp = int(parts[0])
            except ValueError:
                stamp = 0
            timezone = parts[3]
            author, mail = parts[4].split("<", 1)
            author = author.rstrip()
            mail = mail.rstrip(">")
            domain = "?"
            if mail.find("@") != -1:
                domain = mail.rsplit("@", 1)[1]
            date = datetime.datetime.fromtimestamp(float(stamp))

            # Track email<->author mapping to later resolve identity aliases
            if mail and (mail not in email_to_latest or int(stamp) > email_to_latest[mail][0]):
                email_to_latest[mail] = (stamp, author)
            if mail and author not in author_to_email:
                author_to_email[author] = mail

            # First and last commit stamp (may be in any order because of cherry-picking and patches)
            if stamp > self.last_commit_stamp:
                self.last_commit_stamp = stamp
            if self.first_commit_stamp == 0 or stamp < self.first_commit_stamp:
                self.first_commit_stamp = stamp

            # activity
            # hour
            hour = date.hour
            self.activity_by_hour_of_day[hour] = self.activity_by_hour_of_day.get(hour, 0) + 1
            # most active hour?
            if self.activity_by_hour_of_day[hour] > self.activity_by_hour_of_day_busiest:
                self.activity_by_hour_of_day_busiest = self.activity_by_hour_of_day[hour]

            # day of week
            day = date.weekday()
            self.activity_by_day_of_week[day] = self.activity_by_day_of_week.get(day, 0) + 1

            # domain stats
            if domain not in self.domains:
                self.domains[domain] = {}
            # commits
            self.domains[domain]["commits"] = self.domains[domain].get("commits", 0) + 1

            # hour of week
            if day not in self.activity_by_hour_of_week:
                self.activity_by_hour_of_week[day] = {}
            self.activity_by_hour_of_week[day][hour] = (
                self.activity_by_hour_of_week[day].get(hour, 0) + 1
            )
            # most active hour?
            if self.activity_by_hour_of_week[day][hour] > self.activity_by_hour_of_week_busiest:
                self.activity_by_hour_of_week_busiest = self.activity_by_hour_of_week[day][hour]

            # month of year
            month = date.month
            self.activity_by_month_of_year[month] = self.activity_by_month_of_year.get(month, 0) + 1

            # yearly/weekly activity
            yyw = date.strftime("%Y-%W")
            self.activity_by_year_week[yyw] = self.activity_by_year_week.get(yyw, 0) + 1
            if self.activity_by_year_week_peak < self.activity_by_year_week[yyw]:
                self.activity_by_year_week_peak = self.activity_by_year_week[yyw]

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

            # timezone
            self.commits_by_timezone[timezone] = self.commits_by_timezone.get(timezone, 0) + 1

        # Build canonical name mapping: merge authors that share the same email
        # (same person who committed with different name/email configurations)
        email_to_canonical = {email: name for email, (_, name) in email_to_latest.items()}
        name_to_canonical: dict[str, str] = {}
        for name in self.authors.keys():
            email = author_to_email.get(name)
            if email:
                canonical = email_to_canonical.get(email, name)
                if canonical != name:
                    name_to_canonical[name] = canonical

        # Merge aliased author entries into their canonical entries
        for alias, canonical in name_to_canonical.items():
            if alias not in self.authors:
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

        # Merge aliases in time-based author dicts
        for period_dict in (self.author_of_month, self.author_of_year):
            for period in period_dict:
                for alias, canonical in name_to_canonical.items():
                    if alias in period_dict[period]:
                        period_dict[period][canonical] = period_dict[period].get(
                            canonical, 0
                        ) + period_dict[period].pop(alias)

        # Merge aliases in tag author dicts
        for tag in self.tags:
            merged_authors: dict[str, int] = {}
            for author, commits in self.tags[tag]["authors"].items():
                resolved = name_to_canonical.get(author, author)
                merged_authors[resolved] = merged_authors.get(resolved, 0) + commits
            self.tags[tag]["authors"] = merged_authors

        # Update total_authors to reflect merged identities
        self.total_authors = len(self.authors)

        # outputs "<stamp> <files>" for each revision
        revlines = (
            get_pipe_output(
                [
                    'git rev-list --pretty=format:"%at %T" {}'.format(get_log_range("HEAD", False)),
                    "grep -v ^commit",
                ]
            )
            .strip()
            .split("\n")
        )
        lines = []
        revs_to_read = []
        time_rev_count = []
        # Look up rev in cache and take info from cache if found
        # If not append rev to list of rev to read from repo
        for revline in revlines:
            time, rev = revline.split(" ")
            # if cache empty then add time and rev to list of new rev's
            # otherwise try to read needed info from cache
            if "files_in_tree" not in list(self.cache.keys()):
                revs_to_read.append((time, rev))
                continue
            if rev in list(self.cache["files_in_tree"].keys()):
                lines.append("%d %d" % (int(time), self.cache["files_in_tree"][rev]))
            else:
                revs_to_read.append((time, rev))

        # Read revisions from repo
        time_rev_count = parallel_map_with_fallback(get_num_of_files_from_rev, revs_to_read)

        # Update cache with new revisions and append then to general list
        for time, rev, count in time_rev_count:
            if "files_in_tree" not in self.cache:
                self.cache["files_in_tree"] = {}
            self.cache["files_in_tree"][rev] = count
            lines.append("%d %d" % (int(time), count))

        self.total_commits += len(lines)
        for line in lines:
            parts = line.split(" ")
            if len(parts) != 2:
                continue
            (stamp, files) = parts[0:2]
            try:
                self.files_by_stamp[int(stamp)] = int(files)
            except ValueError:
                logger.warning(f'Failed to parse line "{line}"')

        # extensions and size of files
        lines = get_pipe_output(
            ["git ls-tree -r -l -z {}".format(get_commit_range("HEAD", end_only=True))]
        ).split("\000")
        blobs_to_read = []
        for line in lines:
            if len(line) == 0:
                continue
            parts = re.split(r"\s+", line, 4)
            if parts[0] == "160000" and parts[3] == "-":
                # skip submodules
                continue
            blob_id = parts[2]
            size = int(parts[3])
            fullpath = parts[4]

            self.total_size += size
            self.total_files += 1

            filename = fullpath.split("/")[-1]  # strip directories
            if filename.find(".") == -1 or filename.rfind(".") == 0:
                continue  # skip files without extension
            else:
                ext = filename[(filename.rfind(".") + 1) :]
            if len(ext) > conf["max_ext_length"]:
                ext = ""

            # Skip excluded files completely
            if should_exclude_file(ext):
                continue

            if ext not in self.extensions:
                self.extensions[ext] = {"files": 0, "lines": 0}
            self.extensions[ext]["files"] += 1
            # if cache empty then add ext and blob id to list of new blob's
            # otherwise try to read needed info from cache
            if "lines_in_blob" not in list(self.cache.keys()):
                blobs_to_read.append((ext, blob_id))
                continue
            if blob_id in list(self.cache["lines_in_blob"].keys()):
                self.extensions[ext]["lines"] += self.cache["lines_in_blob"][blob_id]
            else:
                blobs_to_read.append((ext, blob_id))

        # Get info about line count for new blob's that wasn't found in cache
        ext_blob_linecount = parallel_map_with_fallback(get_num_of_lines_in_blob, blobs_to_read)

        # Update cache and write down info about number of number of lines
        for ext, blob_id, linecount in ext_blob_linecount:
            if "lines_in_blob" not in self.cache:
                self.cache["lines_in_blob"] = {}
            self.cache["lines_in_blob"][blob_id] = linecount
            self.extensions[ext]["lines"] += self.cache["lines_in_blob"][blob_id]

        # line statistics
        # outputs:
        #  N files changed, N insertions (+), N deletions(-)
        # <stamp> <author>
        self.changes_by_date = {}  # stamp -> { files, ins, del }
        # computation of lines of code by date is better done
        # on a linear history.
        extra = ""
        if conf["linear_linestats"]:
            extra = "--first-parent -m"
        lines = get_pipe_output(
            [
                'git log --shortstat {} --pretty=format:"%at %aN" {}'.format(
                    extra, get_log_range("HEAD", False)
                )
            ]
        ).split("\n")
        lines.reverse()
        files = 0
        inserted = 0
        deleted = 0
        total_lines = 0
        author = None
        for line in lines:
            if len(line) == 0:
                continue

            # <stamp> <author>
            if re.search("files? changed", line) is None:
                pos = line.find(" ")
                if pos != -1:
                    try:
                        (stamp, author) = (int(line[:pos]), line[pos + 1 :])
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
                # self.changes_by_date[stamp] = { 'files': files, 'ins': inserted, 'del': deleted }
        self.total_lines += total_lines

        # Per-author statistics

        # defined for stamp, author only if author committed at this timestamp.
        self.changes_by_date_by_author = {}  # stamp -> author -> lines_added

        # Similar to the above, but never use --first-parent
        # (we need to walk through every commit to know who
        # committed what, not just through mainline)
        lines = get_pipe_output(
            [
                'git log --shortstat --date-order --pretty=format:"%at %aN" {}'.format(
                    get_log_range("HEAD", False)
                )
            ]
        ).split("\n")
        lines.reverse()
        files = 0
        inserted = 0
        deleted = 0
        author = None
        stamp = 0
        for line in lines:
            if len(line) == 0:
                continue

            # <stamp> <author>
            if re.search("files? changed", line) is None:
                pos = line.find(" ")
                if pos != -1:
                    try:
                        oldstamp = stamp
                        (stamp, author) = (int(line[:pos]), line[pos + 1 :])
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
                        files, inserted, deleted = 0, 0, 0
                    except ValueError:
                        logger.warning(f'Unexpected line "{line}"')
                else:
                    logger.warning(f'Unexpected line "{line}"')
            else:
                numbers = get_stat_summary_counts(line)

                if len(numbers) == 3:
                    (files, inserted, deleted) = [int(el) for el in numbers]
                else:
                    logger.warning(f'Failed to handle line "{line}"')
                    (files, inserted, deleted) = (0, 0, 0)

        # File churn: count how many commits touched each file
        churn_output = get_pipe_output(
            ['git log --format="" --name-only {}'.format(get_log_range("HEAD", False))]
        )
        for line in churn_output.split("\n"):
            line = line.strip()
            if line:
                self.file_churn[line] = self.file_churn.get(line, 0) + 1

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
            if "first_commit_stamp" in a:
                first_month = datetime.datetime.fromtimestamp(a["first_commit_stamp"]).strftime(
                    "%Y-%m"
                )
                self.new_contributors_by_month[first_month] = (
                    self.new_contributors_by_month.get(first_month, 0) + 1
                )

    def get_active_days(self) -> set[str]:
        return self.active_days

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


def run(gitpath, outputpath, extra_fmt=None) -> int:
    """Run the gitstats program.
    Args:
        gitpath: path to the git repository
        outputpath: path to the output directory
        extra_fmt: extra format
    Returns:
        0 on success, 1 on failure
    """
    rundir = os.getcwd()

    try:
        os.makedirs(outputpath)
    except OSError:
        pass

    if not os.path.isdir(outputpath):
        logger.error("FATAL: Output path is not a directory or does not exist")
        return 1

    logger.info(f"Output path: {outputpath}")
    cachefile = os.path.join(outputpath, "gitstats.cache")

    # Guard: multi-repository analysis is not yet supported.
    # When multiple paths are given, stats from all repos are merged into
    # one report with the wrong project name (last repo wins).
    # Track: https://github.com/shenxianpeng/gitstats/issues/234
    if len(gitpath) > 1:
        logger.error(
            "Multi-repository analysis is not supported. "
            "Only the first repository will be analyzed: %s",
            gitpath[0],
        )
        logger.info(
            "Track multi-repo dashboard feature: "
            "https://github.com/shenxianpeng/gitstats/issues/234"
        )
        gitpath = gitpath[:1]

    data = GitDataCollector()
    data.load_cache(cachefile)

    for gitpath in gitpath:
        logger.info(f"Git path: {gitpath}")

        prevdir = os.getcwd()
        os.chdir(gitpath)

        logger.info("Collecting data...")
        data.collect(gitpath)

        os.chdir(prevdir)

    logger.info("Refining data...")
    data.save_cache(cachefile)
    data.refine()

    # Generate AI summaries if enabled
    if conf.get("ai_enabled", False):
        try:
            logger.info("Generating AI summaries...")
            summarizer = AISummarizer(conf)
            summarizer.set_cache_dir(os.path.join(outputpath, ".ai_cache"))
            force_refresh = conf.get("refresh_ai", False)
            data.ai_summaries = summarizer.generate_all_summaries(data.__dict__, force_refresh)
            logger.info("AI summaries generated successfully")
        except Exception as e:
            logger.warning(f"Failed to generate AI summaries: {str(e)}")
            logger.info("Report will be generated without AI insights")
            data.ai_summaries = {}
    else:
        data.ai_summaries = {}

    os.chdir(rundir)

    logger.info("Generating report...")
    html_report = HTMLReportCreator()
    html_report.create(data, outputpath)

    if extra_fmt:
        output_file = os.path.join(gitpath, f"{outputpath}.{extra_fmt}")
        if extra_fmt == "json":
            import json

            logger.info(f'Generating JSON file: "{output_file}"')
            with open(output_file, "w", encoding="utf-8") as file:
                json.dump(data.__dict__, file, default=str)
        else:
            logger.error(f"Unsupported format '{extra_fmt}'")
            return 1

    time_end = time.time()
    exectime_internal = time_end - time_start
    logger.info(
        f"Execution time {exectime_internal:.5f} secs, {exectime_external:.5f} secs ({(100.0 * exectime_external) / exectime_internal:.2f} %) in external commands)"
    )
    if sys.stdin.isatty():
        python_cmd = "python" if os.name == "nt" else "python3"
        logger.info(
            f"To view the report, run: {python_cmd} -m http.server 8000 --bind 127.0.0.1 -d {outputpath}"
        )

    return 0


def get_parser() -> argparse.ArgumentParser:
    """Get the parser for the command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate statistics for a Git repository.",
    )

    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {get_version()}",
    )

    # Optional arguments
    parser.add_argument(
        "-c",
        "--config",
        metavar="key=value",
        action="append",
        default=[],
        help=f"Override configuration value. Can be specified multiple times. Default configuration: {conf}",
    )

    # Positional arguments
    parser.add_argument(
        "gitpath",
        metavar="<gitpath>",
        nargs="+",
        help="Path to the Git repository. An optional output directory may follow.",
    )
    parser.add_argument(
        "outputpath",
        metavar="<outputpath>",
        nargs="?",
        default=None,
        help="Path to the output directory (default: gitstats-report)",
    )

    parser.add_argument(
        "-f",
        "--format",
        choices=["json"],
        required=False,
        help="Generate additional output format",
    )

    logging_group = parser.add_mutually_exclusive_group()
    logging_group.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    logging_group.add_argument(
        "--quiet",
        action="store_true",
        help="Only show warnings and errors",
    )

    # AI-powered features
    parser.add_argument(
        "--ai",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable/disable AI-powered summaries in reports (use --ai or --no-ai)",
    )

    parser.add_argument(
        "--ai-provider",
        choices=["openai", "claude", "gemini", "ollama"],
        help="AI provider to use (openai, claude, gemini, ollama)",
    )

    parser.add_argument(
        "--ai-model",
        help="AI model to use (e.g., gpt-4, claude-3-5-sonnet-20241022, gemini-pro, llama2)",
    )

    parser.add_argument(
        "--ai-language",
        help="Language for AI-generated summaries (en, zh, ja, ko, es, fr, de, etc.)",
    )

    parser.add_argument(
        "--refresh-ai",
        action="store_true",
        help="Force refresh AI-generated summaries (ignore cache)",
    )

    return parser


def main() -> int:
    parser = get_parser()
    args = parser.parse_args()
    configure_logging(verbose=args.verbose, quiet=args.quiet)

    # Resolve positional arguments: gitpath (nargs='+') consumes all positional args.
    # If outputpath is None and more than one arg was given, move the last arg from
    # gitpath to outputpath.
    if args.outputpath is None:
        if len(args.gitpath) > 1:
            *repo_paths, args.outputpath = args.gitpath
            args.gitpath = repo_paths
        else:
            args.outputpath = "gitstats-report"

    gitpath = args.gitpath
    outputpath = os.path.abspath(args.outputpath)
    extra_fmt = args.format

    for item in args.config:
        try:
            key, value = item.split("=", 1)
            if key not in conf:
                parser.error(f'No such key "{key}" in config')
            # Convert numeric strings to integers to match config file behavior
            if value.isdigit():
                conf[key] = int(value)
            elif value.lower() in ("true", "false"):
                conf[key] = value.lower() == "true"
            else:
                conf[key] = value
        except ValueError:
            parser.error("Config must be in the form key=value")

    # Handle AI CLI arguments (CLI takes precedence over config)
    if args.ai is not None:
        conf["ai_enabled"] = args.ai

    if args.ai_provider:
        conf["ai_provider"] = args.ai_provider

    if args.ai_model:
        conf["ai_model"] = args.ai_model

    if args.ai_language:
        conf["ai_language"] = args.ai_language

    # Store refresh_ai flag for later use
    conf["refresh_ai"] = args.refresh_ai if hasattr(args, "refresh_ai") else False

    run(gitpath, outputpath, extra_fmt=extra_fmt)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
