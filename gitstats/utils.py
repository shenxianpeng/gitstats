# Copyright (c) 2007-2014 Heikki Hokkanen <hoxu@users.sf.net> & others contributors
# GPLv2 / GPLv3
# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
import datetime
import heapq
import logging
import os
import re
import shlex
import subprocess
import tempfile
import threading
import time
from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from gitstats import ON_LINUX, exectime_external, load_config

logger = logging.getLogger("gitstats")

_WC_L_CMD = "wc -l"


def count_lines_in_text(text: str | None) -> int:
    """Cross-platform function to count lines in text"""
    if not text or not text.strip():
        return 0
    return len(text.strip().split("\n"))


def filter_lines_by_pattern(text: str | None, pattern: str) -> str:
    """Filter out lines matching a pattern (cross-platform grep -v replacement)"""
    if not text or not text.strip():
        return ""
    lines = text.split("\n")
    filtered_lines = [line for line in lines if not re.match(pattern, line)]
    return "\n".join(filtered_lines)


def get_version() -> str:
    """Installed package version, or "dev" when running from a source checkout."""
    try:
        return version("gitstats")
    except PackageNotFoundError:
        return "dev"


def format_int(value: Any) -> str:
    """Render an integer with thousands separators (44025623 -> "44,025,623").

    Non-numeric values are returned unchanged so callers can pass through
    already-formatted or missing data.
    """
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def format_duration(delta: datetime.timedelta) -> str:
    """Render a span compactly: "< 1 d", "9 d", "12 mo", "7.3 yr"."""
    days = delta.total_seconds() / 86400
    if days < 1:
        return "< 1 d"
    if days < 30:
        return f"{int(days)} d"
    if days < 365:
        return f"{round(days / 30.44)} mo"
    return f"{days / 365.25:.1f} yr"


def format_bytes(size: float) -> str:
    """Render a byte count in binary units (161307.78 -> "157.5 KB")."""
    for unit in ("bytes", "KB", "MB", "GB"):
        if abs(size) < 1024 or unit == "GB":
            break
        size /= 1024
    return f"{size:.0f} bytes" if unit == "bytes" else f"{size:.1f} {unit}"


def get_git_version() -> str:
    return get_pipe_output(["git --version"]).split("\n")[0]


def _run_command(cmd: str) -> bytes:
    """Run a single command safely without shell=True."""
    args = shlex.split(cmd)
    result = subprocess.run(args, capture_output=True, text=False, check=False)
    return result.stdout


def _run_pipe_chain(cmds: list[str]) -> bytes:
    """Run a chain of piped commands safely without shell=True."""
    if not cmds:
        return b""

    args = shlex.split(cmds[0])
    p = subprocess.Popen(args, stdout=subprocess.PIPE)
    processes = [p]

    for cmd in cmds[1:]:
        args = shlex.split(cmd)
        p = subprocess.Popen(args, stdin=p.stdout, stdout=subprocess.PIPE)
        processes.append(p)

    output, _ = p.communicate()
    for proc in processes:
        proc.wait()
    return output


def get_pipe_output(cmds: list[str], quiet: bool = False) -> str:
    global exectime_external
    start = time.time()
    if not quiet and ON_LINUX and os.isatty(1):
        logger.debug(">> " + " | ".join(cmds))

    # Handle cross-platform cases with Python equivalents (no shell pipes)
    if len(cmds) == 2 and cmds[1] == _WC_L_CMD:
        output = _run_command(cmds[0])
        try:
            text = output.decode("utf-8", errors="replace").rstrip("\n")
        except UnicodeDecodeError:  # pragma: no cover - errors="replace" never raises
            text = output.decode("latin-1", errors="replace").rstrip("\n")
        line_count = count_lines_in_text(text)
        result = str(line_count)
    elif len(cmds) == 2 and cmds[1].startswith("grep -v"):
        pattern = cmds[1].split("grep -v ")[1]
        output = _run_command(cmds[0])
        try:
            text = output.decode("utf-8", errors="replace").rstrip("\n")
        except UnicodeDecodeError:  # pragma: no cover - errors="replace" never raises
            text = output.decode("latin-1", errors="replace").rstrip("\n")
        result = filter_lines_by_pattern(text, pattern)
    else:
        output = _run_pipe_chain(cmds)
        try:
            result = output.decode("utf-8", errors="replace").rstrip("\n")
        except UnicodeDecodeError:  # pragma: no cover - errors="replace" never raises
            result = output.decode("latin-1", errors="replace").rstrip("\n")

    end = time.time()
    if not quiet:
        logger.debug("[{:.5f}] >> {}".format(end - start, " | ".join(cmds)))
    exectime_external += end - start
    return result


def get_commit_range(defaultrange: str = "HEAD", end_only: bool = False) -> str:
    if len(load_config()["commit_end"]) > 0:
        commit_begin = load_config()["commit_begin"]

        # Convert commit_begin to string for consistent handling
        commit_begin_str = str(commit_begin)

        # If end_only or no commit_begin specified, return just the end
        if end_only or len(commit_begin_str) == 0:
            return load_config()["commit_end"]

        # Handle numeric commit_begin as "N commits ago"
        if commit_begin_str.isdigit():
            commit_begin_str = f"{load_config()['commit_end']}~{commit_begin_str}"

        return "{}..{}".format(commit_begin_str, load_config()["commit_end"])
    return defaultrange


def get_excluded_extensions() -> set[str]:
    """
    Get the set of excluded file extensions from config.
    Returns a set of lowercase extensions.
    """
    exclude_ext_str = load_config().get("exclude_exts", "")
    if not exclude_ext_str:
        return set()
    return {ext.strip().lower() for ext in exclude_ext_str.split(",") if ext.strip()}


def should_exclude_file(ext: str) -> bool:
    """
    Check if a file should be excluded from line counting based on extension.
    Returns True if the file extension is in the exclude_exts configuration.
    If exclude_exts is empty, no files are excluded (returns False for all).
    """
    # Get excluded extensions from config
    excluded_extensions = get_excluded_extensions()

    # If exclude_exts is empty, don't exclude any files
    if not excluded_extensions:
        return False

    # Check if extension is in the excluded list
    return ext.lower() in excluded_extensions


def get_num_of_files_from_rev(time_rev: tuple[str, str]) -> tuple[int, str, int]:
    """
    Get number of files changed in commit
    """
    time, rev = time_rev
    return (
        int(time),
        rev,
        int(get_pipe_output([f'git ls-tree -r --name-only "{rev}"', _WC_L_CMD]).split("\n")[0]),
    )


def _git_lines(args: list[str], stdin: Any = None) -> Iterator[bytes]:
    """Run a git command and yield its output line by line, without the newline.

    For the commands whose output is as long as the history: nothing is held
    in memory but the line being read. ``stdin`` is a file the command reads.
    Raises subprocess.CalledProcessError once the output is read if git failed.
    """
    global exectime_external
    start = time.time()
    with subprocess.Popen(
        ["git", *args], stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    ) as process:
        assert process.stdout is not None
        for line in process.stdout:
            yield line.rstrip(b"\n")
    exectime_external += time.time() - start
    if process.returncode:
        raise subprocess.CalledProcessError(process.returncode, ["git", *args])


def count_files_in_trees(rev: str, wanted: set[str], known: dict[str, int]) -> dict[str, int]:
    """Count the files in the trees of the commits leading to ``rev``.

    ``wanted`` are the trees (hashes, as ``%T`` prints them) whose counts are
    needed; ``known`` maps the trees already counted to their counts. Returns
    the counts worked out, which are those of ``wanted`` and of any ancestor
    that had to be counted on the way.

    ``git ls-tree -r`` on every commit lists every file of every commit: a
    process per commit, and work that grows with commits x files. Here a
    commit's count is its first parent's, plus the files it added, minus the
    ones it deleted, and a single ``git diff-tree --stdin`` reports those for
    the whole history. A commit whose first parent's tree is in ``known``
    starts from there, so with a cache only the new commits are compared.

    A tree that is not found among the commits leading to ``rev`` is left
    out of the result, as is everything if git fails: the caller counts
    those with get_num_of_files_from_rev().
    """
    try:
        return _count_files_in_trees(rev, wanted, known)
    except (OSError, subprocess.CalledProcessError) as error:
        # half a listing would give wrong counts, not missing ones
        logger.debug(f"Could not count files from the commits' differences: {error}")
        return {}


def _count_files_in_trees(rev: str, wanted: set[str], known: dict[str, int]) -> dict[str, int]:
    """count_files_in_trees(), with git's failures left to the caller."""
    # ancestors before descendants: [commit, tree, first parent or None]
    commits: list[tuple[str, str, str | None]] = []
    tree_of: dict[str, str] = {}
    for line in _git_lines(["log", "--topo-order", "--reverse", "--format=%H %T %P", rev]):
        parts = line.decode("ascii", errors="replace").split(" ")
        if len(parts) < 2:
            continue
        commit, tree = parts[0], parts[1]
        commits.append((commit, tree, parts[2] if len(parts) > 2 and parts[2] else None))
        tree_of[commit] = tree

    # The commits to compare with their first parent: the wanted ones, and the
    # ancestors a count has to be carried up from
    needed: set[str] = set()
    for commit, tree, parent in reversed(commits):
        if commit not in needed:
            if tree not in wanted or tree in known:
                continue
            needed.add(commit)
        if parent is not None and tree_of.get(parent) not in known:
            needed.add(parent)
    if not needed:
        return {}

    delta: dict[str, int] = {}
    with tempfile.TemporaryFile("w+") as pairs:
        for commit, _, parent in commits:
            if commit in needed:
                # a commit without a parent we know of is compared with nothing (--root)
                pairs.write(f"{commit} {parent}\n" if parent in tree_of else f"{commit}\n")
        pairs.seek(0)
        current = ""
        for line in _git_lines(
            [
                "diff-tree",
                "--stdin",
                "-r",
                "--root",
                "--no-renames",
                "--diff-filter=AD",
                "--name-status",
            ],
            stdin=pairs,
        ):
            if line[:2] == b"A\t":
                delta[current] = delta.get(current, 0) + 1
            elif line[:2] == b"D\t":
                delta[current] = delta.get(current, 0) - 1
            else:
                # the commit the following lines are about
                current = line.split(b" ", 1)[0].decode("ascii", errors="replace")

    counts: dict[str, int] = {}
    of_commit: dict[str, int] = {}
    for commit, tree, parent in commits:
        if commit not in needed:
            continue
        if parent not in tree_of:
            base = 0
        elif parent in of_commit:
            base = of_commit[parent]
        else:
            base = known[tree_of[parent]]
        of_commit[commit] = counts[tree] = base + delta.get(commit, 0)
    return counts


def count_lines_in_blobs(blob_ids: Iterable[str]) -> dict[str, int]:
    """Count the lines of each blob, with one ``git cat-file --batch``.

    0 for a binary blob (a null byte in its first 8192 bytes), for one git
    cannot read, and for an id that is not a blob's. Leading and trailing
    blank lines are not counted (see count_lines_in_text()).
    """
    ids = list(dict.fromkeys(blob_ids))
    counts: dict[str, int] = dict.fromkeys(ids, 0)
    if not ids:
        return counts
    global exectime_external
    start = time.time()
    with tempfile.TemporaryFile("w+") as names:
        names.write("\n".join(ids) + "\n")
        names.seek(0)
        with subprocess.Popen(
            ["git", "cat-file", "--batch"],
            stdin=names,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        ) as process:
            out = process.stdout
            assert out is not None
            for blob_id in ids:
                # "<id> <type> <size>", or "<id> missing"
                header = out.readline().split()
                if not header:
                    break  # git stopped: the blobs left count nothing
                if len(header) != 3:
                    continue
                size = int(header[2])
                head = out.read(min(size, 8192))
                if header[1] != b"blob" or b"\x00" in head:
                    _skip(out, size - len(head) + 1)
                    continue
                content = head + out.read(size - len(head))
                out.read(1)  # the newline that ends the entry
                counts[blob_id] = count_lines_in_text(
                    content.decode("utf-8", errors="replace").rstrip("\n")
                )
    exectime_external += time.time() - start
    return counts


def _skip(stream: Any, size: int) -> None:
    """Read ``size`` bytes of a stream and drop them, a megabyte at a time."""
    while size > 0:
        chunk = stream.read(min(size, 1 << 20))
        if not chunk:
            return
        size -= len(chunk)


# How many commits one git process is asked the line counts of. Small enough for
# the processes to share the work evenly, whatever the commits cost and however
# fast the cores are; large enough for starting them not to count.
SHORTSTAT_COMMITS_PER_PROCESS = 1000
# The processes that count lines are two at first and one more every few
# seconds, up to as many as were asked for. A history of small diffs is done
# before they are many, and they take no processor from the phases of the run
# that go on meanwhile; a history that needs them all has them soon enough.
SHORTSTAT_PROCESSES_AT_FIRST = 2
SHORTSTAT_SECONDS_PER_PROCESS = 3.0

# "<commit>\t<parents>\t<stamp> <author>", a commit of a walk
_LOG_ROW = re.compile(r"^([0-9a-f]+)\t([0-9a-f ]*)\t(.*)$", re.MULTILINE)
# a line that is a commit's hash and nothing else
_COMMIT_LINE = re.compile(r"^([0-9a-f]{40}|[0-9a-f]{64})$", re.MULTILINE)


def _git_text(args: list[str], data: str | None = None, env: dict[str, str] | None = None) -> str:
    """Run a git command, giving it ``data`` to read, and return what it prints.

    Raises subprocess.CalledProcessError if git fails.
    """
    global exectime_external
    start = time.time()
    # What git reads comes from a file, not a pipe. With a pipe each way,
    # subprocess reads the output in the pieces git writes it in, and git
    # writes a commit at a time: a few seconds of Python on a long history,
    # during which the other threads of the run wait. With one pipe it is
    # one read.
    with tempfile.TemporaryFile("w+") as given:
        if data is not None:
            given.write(data)
            given.seek(0)
        result = subprocess.run(
            ["git", *args],
            stdin=given if data is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
            env=env,
        )
    exectime_external += time.time() - start
    return result.stdout.decode("utf-8", errors="replace")


def shortstat_logs(passes: list[tuple[str, bool]], log_range: str, workers: int) -> list[str]:
    """Write what `git log --shortstat` prints for several walks of one history.

    Each of ``passes`` is ``(walk, first_parent)``: ``walk`` holds the options
    that pick and order its commits (``--first-parent``, ``--date-order``),
    and ``first_parent`` says whether a merge is compared with its first
    parent (``-m --first-parent``) or shown without a count. The text
    returned for a pass is, blank lines aside, the output of::

        git log --shortstat <walk> [-m] --pretty=format:"%at %aN" <log_range>

    Counting the lines of every diff is what those commands spend their time
    on, each in one process, and the walks mostly cover the same commits.
    Here the commits of each walk are listed first, which is quick. The
    counts are then asked for once per commit, whatever the number of walks
    it is in, and from up to ``workers`` git processes at a time
    (``git log --shortstat --no-walk``), each taking the next
    SHORTSTAT_COMMITS_PER_PROCESS commits when it is done with the last.
    They are SHORTSTAT_PROCESSES_AT_FIRST to begin with, and one more every
    SHORTSTAT_SECONDS_PER_PROCESS seconds.

    The outputs are cut and joined whole, with as little work per commit in
    Python as can be: the caller is parsing other output meanwhile, and the
    two would take turns.

    Raises OSError or subprocess.CalledProcessError when git fails.
    """
    workers = max(workers, 1)
    # git fills its buffer before it writes, where it would write after every commit
    env = {**os.environ, "GIT_FLUSH": "0"}

    def listing(walk: str) -> list[tuple[str, str, str]]:
        """(commit, parents, "<stamp> <author>") in the order of the walk."""
        return _LOG_ROW.findall(
            _git_text(
                [
                    "log",
                    *shlex.split(walk),
                    "--format=%H%x09%P%x09%at %aN",
                    *shlex.split(log_range),
                ],
                env=env,
            )
        )

    # how many git processes may count lines at this moment
    allowed = threading.Semaphore(min(workers, SHORTSTAT_PROCESSES_AT_FIRST))
    counted = threading.Event()

    def allow_more() -> None:
        for _ in range(workers - SHORTSTAT_PROCESSES_AT_FIRST):
            if counted.wait(SHORTSTAT_SECONDS_PER_PROCESS):
                return
            allowed.release()

    def counts(job: tuple[list[str], bool]) -> dict[str, str]:
        """commit -> what git prints under it, for one process's share of the commits."""
        commits, first_parent = job
        with allowed:
            text = _git_text(
                [
                    "log",
                    "--shortstat",
                    *(["-m", "--first-parent"] if first_parent else []),
                    "--no-walk",
                    # from its input: a thousand hashes are more than a
                    # command line holds on Windows
                    "--stdin",
                    "--format=%H",
                ],
                "\n".join(commits) + "\n",
                env,
            )
        # [what comes before the first commit, commit, what is under it, commit, ...]
        parts = _COMMIT_LINE.split(text)
        return dict(zip(parts[1::2], parts[2::2]))

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="git-shortstat") as pool:
        walks = list(pool.map(listing, [walk for walk, _ in passes]))

        # Every commit once: a merge of a first-parent walk with its first
        # parent, any other commit the plain way, which is the same in every
        # walk. The commits stay in the order of the walks, so that those of
        # one process are neighbors in the history.
        plain_commits: dict[str, None] = {}
        merge_commits: dict[str, None] = {}
        for (_, first_parent), rows in zip(passes, walks):
            if first_parent:
                merge_commits.update(
                    (commit, None) for commit, parents, _ in rows if " " in parents
                )
                plain_commits.update(
                    (commit, None) for commit, parents, _ in rows if " " not in parents
                )
            else:
                plain_commits.update((row[0], None) for row in rows)
        size = SHORTSTAT_COMMITS_PER_PROCESS
        jobs = [
            (commits[start : start + size], first_parent)
            for commits, first_parent in ((list(plain_commits), False), (list(merge_commits), True))
            for start in range(0, len(commits), size)
        ]
        plain: dict[str, str] = {}
        merges: dict[str, str] = {}
        timer = threading.Thread(target=allow_more, name="git-shortstat-more", daemon=True)
        timer.start()
        try:
            for (_, first_parent), found in zip(jobs, pool.map(counts, jobs)):
                (merges if first_parent else plain).update(found)
        except BaseException:
            # git failed for some commits: the others need not be counted
            pool.shutdown(cancel_futures=True)
            raise
        finally:
            counted.set()
            timer.join()

    texts = []
    for (_, first_parent), rows in zip(passes, walks):
        # in a first-parent walk the merges have the counts made that way
        under = {**plain, **merges} if first_parent and merges else plain
        try:
            texts.append("\n".join([header + under[commit] for commit, _, header in rows]))
        except KeyError as missing:
            raise subprocess.CalledProcessError(
                1, ["git", "log", "--shortstat", "--no-walk"], f"nothing printed for {missing}"
            ) from None
    return texts


def history_graph(rev: str) -> tuple[dict[str, int], list[list[int]], list[str]]:
    """Read the commits leading to ``rev``, with what joins them, in one `git log`.

    Returns ``(place, parents, headers)``:
        place:   commit hash -> its place in the two lists. A commit comes
                 before its parents (``--topo-order``), so a smaller place is
                 never an ancestor of a larger one;
        parents: for each commit, the places of its parents (a parent git
                 does not have, as at the edge of a shallow clone, is left out);
        headers: for each commit, "<author timestamp> <author name>", as
                 ``git log --format="%at %aN"`` prints it.
    """
    rows = _LOG_ROW.findall(
        get_pipe_output([f'git log --topo-order --format="%H%x09%P%x09%at %aN" "{rev}"'])
    )
    place = {row[0]: index for index, row in enumerate(rows)}
    parents = [[place[parent] for parent in row[1].split() if parent in place] for row in rows]
    return place, parents, [row[2] for row in rows]


def commits_reached(parents: list[list[int]], tip: int, base: int | None = None) -> list[int]:
    """List the commits that lead to ``tip`` and not to ``base``.

    The commits of ``git rev-list <tip> ^<base>`` (those of ``git rev-list
    <tip>`` without a base), in a graph as history_graph() gives it:
    ``parents[i]`` holds the places of the parents of commit ``i``, and a
    commit comes before its parents. Descendants come first in the result.

    Both sides are walked at once, the nearest descendants first, the way git
    does it: a commit is known to lead to ``base`` or not by the time it is
    reached, and the walk stops when everything left to visit leads to it.
    What it costs is the commits listed and those of the other side as far
    back as they go, not the whole history.
    """
    wanted, unwanted = 1, 2
    state = {tip: wanted}
    queue = [tip]
    # how many of the commits waiting in the queue are still wanted
    waiting = 1
    if base is not None:
        if base == tip:
            return []
        state[base] = unwanted
        heapq.heappush(queue, base)
    reached = []
    while waiting:
        commit = heapq.heappop(queue)
        mine = state[commit]
        if mine == wanted:
            waiting -= 1
            reached.append(commit)
        for parent in parents[commit]:
            theirs = state.get(parent)
            if theirs is None:
                state[parent] = mine
                heapq.heappush(queue, parent)
                if mine == wanted:
                    waiting += 1
            elif theirs == wanted and mine == unwanted:
                # reached from the tip first, and now from the base as well
                state[parent] = unwanted
                waiting -= 1
    return reached


def get_stat_summary_counts(line: str) -> list[str | int]:
    numbers = re.findall(r"\d+", line)
    if len(numbers) == 1:
        # neither insertions nor deletions: may probably only happen for "0 files changed"
        numbers.append(0)
        numbers.append(0)
    elif len(numbers) == 2 and line.find("(+)") != -1:
        numbers.append(0)
        # only insertions were printed on line
    elif len(numbers) == 2 and line.find("(-)") != -1:
        numbers.insert(1, 0)
        # only deletions were printed on line
    return numbers


def get_log_range(defaultrange: str = "HEAD", end_only: bool = True) -> str:
    commit_range = get_commit_range(defaultrange, end_only)
    # Build git log options
    options = []

    # Date range filtering
    if len(load_config()["start_date"]) > 0:
        options.append('--since="{}"'.format(load_config()["start_date"]))
    if len(load_config()["end_date"]) > 0:
        options.append('--until="{}"'.format(load_config()["end_date"]))

    # Author filtering
    if len(load_config()["authors"]) > 0:
        authors_list = [
            author.strip() for author in load_config()["authors"].split(",") if author.strip()
        ]
        for author in authors_list:
            # Escape possible double quotes or special characters in author
            safe_author = author.replace('"', r"\"")
            options.append(f'--author="{safe_author}"')

    # Combine options with commit range
    if options:
        return '{} "{}"'.format(" ".join(options), commit_range)
    return commit_range


def commit_local_time(stamp: float, utc_offset: str) -> datetime.datetime:
    """The moment ``stamp`` on the clock of whoever made the commit.

    ``utc_offset`` is the commit's own offset as git prints it (``+0300``,
    ``-0530``), so the result does not depend on the timezone of the machine
    the report is generated on. It is naive, like the report's other
    datetimes. An offset that cannot be read falls back to this machine's
    local time.
    """
    match = re.fullmatch(r"([+-])(\d{2})(\d{2})", utc_offset.strip())
    if match:
        sign, hours, minutes = match.groups()
        offset = datetime.timedelta(hours=int(hours), minutes=int(minutes))
        try:
            zone = datetime.timezone(-offset if sign == "-" else offset)
        except ValueError:  # a day or more, which no timezone is
            zone = None
        if zone is not None:
            return datetime.datetime.fromtimestamp(stamp, zone).replace(tzinfo=None)
    return datetime.datetime.fromtimestamp(stamp)


def tags_newest_first(tags: dict[str, Any]) -> list[str]:
    """Order tags the way the history does, newest first.

    Data collection records each tag's position in the commit walk, where a
    smaller index is a newer commit. Tags without a position (data from an
    older version, such as a JSON dump) fall back to the date, newest first.
    Shared by the report pages and the release badge, so they agree on which
    tag is the latest.
    """
    return sorted(
        tags,
        key=lambda tag: (
            "order" not in tags[tag],
            tags[tag].get("order", 0),
            _reversed_date(tags[tag].get("date", "")),
            tag,
        ),
    )


def _reversed_date(date: str) -> tuple[int, ...]:
    """Sort key putting the later date first, for the no-position fallback.

    A date that does not parse sorts after every real one, rather than ahead
    of them as an empty key would.
    """
    try:
        return (0, *(-int(part) for part in date.split("-")))
    except ValueError:
        return (1,)
