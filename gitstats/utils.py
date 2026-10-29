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
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import PackageNotFoundError, version
from typing import Any, NamedTuple

from gitstats import ON_LINUX, check_git_settings, exectime_external, load_config

logger = logging.getLogger("gitstats")

_WC_L_CMD = "wc -l"


def count_lines_in_text(text: str | None) -> int:
    """Cross-platform function to count lines in text"""
    if not text or not text.strip():
        return 0
    return len(text.strip().split("\n"))


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
    for unit in ("bytes", "KB", "MB", "GB"):  # pragma: no branch - breaks at GB at the latest
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
    """The revisions the configured range is made of, as `git log` takes them.

    ``commit_begin..commit_end``, or ``commit_end`` alone with ``end_only``
    or without a ``commit_begin``. A ``commit_begin`` that is a number N
    means the last N commits that lead to ``commit_end``: all of them when
    the history has fewer (see last_commits_range()).

    Raises ValueError when a setting that goes on git's command line could be
    taken for something else (see check_git_settings()). Put the range after
    ``--end-of-options``, so that git never reads it as an option.
    """
    check_git_settings(load_config())
    commit_end = str(load_config()["commit_end"])
    if not commit_end:
        return defaultrange
    commit_begin = str(load_config()["commit_begin"])
    if end_only or not commit_begin:
        return commit_end
    if commit_begin.isascii() and commit_begin.isdigit():
        return last_commits_range(commit_end, int(commit_begin))
    return f"{commit_begin}..{commit_end}"


# (directory, end, count) -> what last_commits_range() found there
_last_commits: dict[tuple[str, str, int], str] = {}


def last_commits_range(end: str, count: int) -> str:
    """The last ``count`` commits that lead to ``end``, as revisions for `git log`.

    They are the first ``count`` of ``git rev-list --topo-order <end>``,
    where a commit comes after all of its descendants: the range is
    ``<end>`` less the commits the oldest of them come from, ``<end> ^<parent>
    ...``. Every walk of it, first-parent or not, sees those commits and no
    others, where ``<end>~N..<end>`` would take in whole branches merged in
    the last N commits, and fail on a history shorter than N. With no more
    than ``count`` commits in the history, it is ``<end>``: all of them.
    The answer is kept for the run, by repository.
    """
    if count == 0:
        return f"{end}..{end}"
    key = (os.getcwd(), end, count)
    if key not in _last_commits:
        rows = get_pipe_output(
            [
                f"git rev-list --topo-order --parents --max-count={count} --end-of-options "
                + shlex.quote(end)
            ]
        ).split("\n")
        commits = {row.split(" ", 1)[0] for row in rows}
        parents = [parent for row in rows for parent in row.split()[1:]]
        boundary = dict.fromkeys(parent for parent in parents if parent not in commits)
        _last_commits[key] = " ".join([end, *(f"^{parent}" for parent in boundary)])
    return _last_commits[key]


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


class History(NamedTuple):
    """The commits leading to a revision, as history_graph() reads them.

    A commit is known by its place in the lists. It comes before its parents,
    so a smaller place is never an ancestor of a larger one.
    """

    place: dict[str, int]  # commit hash -> its place
    commits: list[str]  # the hash of each commit
    trees: list[str]  # the hash of its tree
    parents: list[list[int]]  # the places of its parents, those git has
    first_parents: list[int]  # the place of its first parent, -1 without one
    headers: list[str]  # "<author timestamp> <author name>"


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


def count_files_in_trees(
    history: History,
    wanted: set[str],
    known: dict[str, int],
    added: dict[str, int] | None = None,
) -> dict[str, int]:
    """Count the files in the trees of the commits of ``history``.

    ``wanted`` are the trees (hashes, as ``%T`` prints them) whose counts are
    needed; ``known`` maps the trees already counted to their counts. Returns
    the counts worked out, which are those of ``wanted`` and of any ancestor
    that had to be counted on the way.

    ``git ls-tree -r`` on every commit lists every file of every commit: a
    process per commit, and work that grows with commits x files. Here a
    commit's count is its first parent's, plus the files it added, minus the
    ones it deleted. A commit whose first parent's tree is in ``known``
    starts from there, so with a cache only the new commits are looked at.

    ``added`` gives that difference for the commits it has: commit hash ->
    files added less files deleted, against its first parent
    (shortstat_logs() reads it off the diffs it has git make for the line
    counts). The other commits are compared with their first parent by a
    single ``git diff-tree --stdin``; without ``added`` that is all of them.

    A tree that is not found in the history is left out of the result, as is
    everything if git fails: the caller counts those with
    get_num_of_files_from_rev().
    """
    try:
        return _count_files_in_trees(history, wanted, known, added or {})
    except (OSError, subprocess.CalledProcessError) as error:
        # half a listing would give wrong counts, not missing ones
        logger.debug(f"Could not count files from the commits' differences: {error}")
        return {}


def _count_files_in_trees(
    history: History, wanted: set[str], known: dict[str, int], added: dict[str, int]
) -> dict[str, int]:
    """count_files_in_trees(), with git's failures left to the caller."""
    commits, trees, first_parents = history.commits, history.trees, history.first_parents

    # The commits whose difference with their first parent is needed: the
    # wanted ones, and the ancestors a count has to be carried up from.
    # Descendants come first, so a commit is marked before it is reached.
    needed = bytearray(len(commits))
    for commit, tree in enumerate(trees):
        if not needed[commit]:
            if tree not in wanted or tree in known:
                continue
            needed[commit] = 1
        parent = first_parents[commit]
        if parent >= 0 and trees[parent] not in known:
            needed[parent] = 1

    # That difference, from the counts already made, or else from git
    delta: dict[int, int] = {}
    place = history.place
    with tempfile.TemporaryFile("w+") as pairs:
        asked = False
        for commit in range(len(commits)):
            if not needed[commit]:
                continue
            difference = added.get(commits[commit])
            if difference is not None:
                delta[commit] = difference
                continue
            parent = first_parents[commit]
            # a commit without a parent we know of is compared with nothing (--root)
            pairs.write(
                f"{commits[commit]} {commits[parent]}\n" if parent >= 0 else f"{commits[commit]}\n"
            )
            asked = True
        if asked:
            pairs.seek(0)
            current = -1
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
                    current = place[line.split(b" ", 1)[0].decode("ascii", errors="replace")]

    counts: dict[str, int] = {}
    of_commit: dict[int, int] = {}
    # ancestors first, so that a parent is counted before its children
    for commit in range(len(commits) - 1, -1, -1):
        if not needed[commit]:
            continue
        parent = first_parents[commit]
        if parent < 0:
            base = 0
        elif needed[parent]:
            base = of_commit[parent]
        else:
            base = known[trees[parent]]
        of_commit[commit] = counts[trees[commit]] = base + delta.get(commit, 0)
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
# that go on meanwhile. A history of large diffs is what a run waits for: once
# the processes take SHORTSTAT_SLOW_SECONDS over their commits on average, all
# those asked for are allowed. (At that rate two processes would still be
# counting when the other phases, which cost about half as much per commit,
# are done.) They are all allowed, too, when the run says it is waiting.
SHORTSTAT_PROCESSES_AT_FIRST = 2
SHORTSTAT_SECONDS_PER_PROCESS = 3.0
SHORTSTAT_SLOW_SECONDS = 0.35

# "<commit>\t<parents>\t<the line that starts it>", a commit of a walk
_LOG_ROW = re.compile(r"^([0-9a-f]+)\t([0-9a-f ]*)\t(.*)$", re.MULTILINE)
# What starts a commit in the output of a process that counts lines. git puts
# no such character in what follows: it quotes the paths that have one.
_COMMIT_MARK = "\x01"


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


def shortstat_logs(
    passes: list[tuple[str, bool]],
    log_range: str,
    workers: int,
    waiting: threading.Event | None = None,
    names: str | None = None,
    source: Callable[[str], bool] | None = None,
    source_lines: list[int] | None = None,
) -> tuple[list[str], dict[str, int], str | None]:
    """Write what `git log --shortstat` prints for several walks of one history.

    Each of ``passes`` is ``(walk, first_parent)``: ``walk`` holds the options
    that pick and order its commits (``--first-parent``, ``--date-order``),
    and ``first_parent`` says whether a merge is compared with its first
    parent (``--first-parent -m``) or shown without a count. The text
    written for a pass is, blank lines aside, the output of::

        git log --shortstat <walk> [-m] --pretty=format:"%at %aN" <log_range>

    Returns the texts, and with them what the same diffs say of the files of
    each commit: commit hash -> files it adds, less files it deletes, against
    its first parent (``--summary``). That is given for the commits with one
    parent, and for the merges compared with their first parent; a commit
    without parents is left out, as git may or may not show what it adds.
    count_files_in_trees() takes it, and has nothing left to ask git about
    for most commits.

    With ``names``, the same diffs also say what files each commit changes.
    ``names`` is the format of the line that starts a commit, and the third
    text returned is, blank lines aside, the output of::

        git log --format=<names> --name-only <log_range>

    which would compare every commit once more. Without it, None is returned
    in its place.

    Counting the lines of every diff is what those commands spend their time
    on, each in one process, and the walks mostly cover the same commits.
    Here the commits of each walk are listed first, which is quick. The
    counts are then asked for once per commit, whatever the number of walks
    it is in, and from up to ``workers`` git processes at a time
    (``git log --shortstat --no-walk``), each taking the next
    SHORTSTAT_COMMITS_PER_PROCESS commits when it is done with the last.
    They are SHORTSTAT_PROCESSES_AT_FIRST to begin with and one more every
    SHORTSTAT_SECONDS_PER_PROCESS seconds, or all of them once they take
    SHORTSTAT_SLOW_SECONDS over their commits on average. They are held back
    to leave processors to what the caller does meanwhile: when it sets
    ``waiting``, it has nothing left to do but wait, and they are all allowed.

    The outputs are cut and joined whole, with as little work per commit in
    Python as can be: the caller is parsing other output meanwhile, and the
    two would take turns.

    With ``source`` and ``source_lines``, the plain diffs also count, file by
    file (``--numstat``), the lines added to the files ``source`` takes for
    the project's own, and their sum is appended to ``source_lines``: the
    lines ever added to its source, every commit but the merges once.

    Raises OSError or subprocess.CalledProcessError when git fails.
    """
    workers = max(workers, 1)
    with_numstat = source is not None and source_lines is not None
    # git fills its buffer before it writes, where it would write after every commit
    env = {**os.environ, "GIT_FLUSH": "0"}

    def listing(walk: str, header: str) -> list[tuple[str, str, str]]:
        """(commit, parents, the line that starts it) in the order of the walk."""
        return _LOG_ROW.findall(
            _git_text(
                [
                    "log",
                    *shlex.split(walk),
                    f"--format=%H%x09%P%x09{header}",
                    *shlex.split(log_range),
                ],
                env=env,
            )
        )

    # how many git processes may count lines at this moment, and how many
    # more may be allowed later
    allowed = threading.Semaphore(min(workers, SHORTSTAT_PROCESSES_AT_FIRST))
    held_back = [max(workers - SHORTSTAT_PROCESSES_AT_FIRST, 0)]
    # the seconds the processes have taken so far, and how many have finished
    spent = [0.0, 0]
    holding = threading.Lock()
    counted = threading.Event()

    def allow(processes: int) -> None:
        with holding:
            processes = min(processes, held_back[0])
            held_back[0] -= processes
        for _ in range(processes):
            allowed.release()

    def allow_more() -> None:
        """One more process when it is due; all of them once the caller waits."""
        due = time.monotonic() + SHORTSTAT_SECONDS_PER_PROCESS
        while held_back[0]:
            if waiting is not None and waiting.is_set():
                allow(workers)
                return
            # with a caller to listen for, a short nap; without, until the next is due
            nap = 0.05 if waiting is not None else due - time.monotonic()
            if counted.wait(max(nap, 0)):
                return
            if time.monotonic() >= due:
                allow(1)
                due += SHORTSTAT_SECONDS_PER_PROCESS

    def counts(
        job: tuple[list[str], bool],
    ) -> tuple[dict[str, str], dict[str, int], dict[str, str], int, dict[str, list[str]]]:
        """For one process's share of the commits: commit -> the count git
        prints under it, commit -> the files it adds less those it deletes,
        where that is not nothing, and, when the names are asked for,
        commit -> the files it changes, a line each. Then, when the lines of
        the source are asked for, those its diffs add, and commit -> the
        files it moves into the source (see _source_lines_of())."""
        commits, first_parent = job
        # the names are those of the plain diff, as `git log --name-only` shows it
        with_names = names is not None and not first_parent
        numstat = with_numstat and not first_parent
        with allowed:
            began = time.monotonic()
            text = _git_text(
                [
                    # the paths as they are: git still quotes those with a
                    # double quote, a backslash or a control character
                    "-c",
                    "core.quotePath=false",
                    "log",
                    # the diff of a commit without parents, whatever log.showRoot says
                    "--root",
                    "--shortstat",
                    # the files created and deleted, from the same diff
                    "--summary",
                    # and every file changed. --name-only would print the names
                    # and nothing else; a raw line ends with the name, quoted
                    # the same way, and full hashes cost git nothing to print
                    *(["--raw", "--no-abbrev"] if with_names else []),
                    # and, file by file, the lines added and removed
                    *(["--numstat"] if numstat else []),
                    *(["--first-parent", "-m"] if first_parent else []),
                    "--no-walk",
                    # from its input: a thousand hashes are more than a
                    # command line holds on Windows
                    "--stdin",
                    "--format=%x01%H",
                ],
                "\n".join(commits) + "\n",
                env,
            )
            took = time.monotonic() - began
            with holding:
                spent[0] += took
                spent[1] += 1
                # the average, of four processes at least: one slow share of
                # the commits does not make a slow history, unless it is very slow
                slow = spent[0] > SHORTSTAT_SLOW_SECONDS * max(spent[1], 4)
            if slow:
                # large diffs: the run will be waiting for these counts
                allow(workers)
        found: dict[str, str] = {}
        files: dict[str, int] = {}
        changed: dict[str, str] = {}
        source_added = 0
        moved: dict[str, list[str]] = {}
        # [what comes before the first commit, "<commit>\n<what is under it>", ...]
        for block in text.split(_COMMIT_MARK)[1:]:
            commit, _, under = block.partition("\n")
            # Under a commit, in this order: a line for each file changed
            # (":100644 100644 <blob> <blob> M\t<path>"), the line that
            # counts the changes (" 3 files changed, ..."), and a line for
            # each file created, deleted or renamed (" create mode 100644
            # <path>"). The first kind starts with a colon, the two others
            # with a space, whatever the paths are.
            count_at = under.find("\n ")
            if count_at < 0:
                # nothing changed, or a merge shown without a diff
                found[commit] = ""
                raw = under
            else:
                summary_at = under.find("\n", count_at + 1)
                # the text is that of the commands, which print the count alone
                found[commit] = under[count_at : summary_at + 1]
                if summary_at + 1 < len(under):
                    # a renamed file is neither created nor deleted; a copied one is new
                    change = (
                        under.count("\n create mode ", summary_at)
                        + under.count("\n copy ", summary_at)
                        - under.count("\n delete mode ", summary_at)
                    )
                    if change:
                        files[commit] = change
                raw = under[:count_at]
            if numstat:
                lines, moved_in = _source_lines_of(raw.split("\n"), source)  # type: ignore[arg-type]
                source_added += lines
                if moved_in:
                    moved[commit] = moved_in
            if with_names:
                # the name is what follows the last tab: for a renamed file,
                # the new name, which comes after the old one. It is left
                # quoted as `git log --name-only` would print it.
                changed[commit] = "".join(
                    [
                        "\n" + line.rpartition("\t")[2]
                        for line in raw.split("\n")
                        if line.startswith(":")
                    ]
                )
        return found, files, changed, source_added, moved

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="git-shortstat") as pool:
        walks = list(
            pool.map(
                listing,
                # the walk of `git log` for the names comes last
                [walk for walk, _ in passes] + ([""] if names is not None else []),
                ["%at %aN"] * len(passes) + ([names] if names is not None else []),
            )
        )
        named_walk = walks.pop() if names is not None else None

        # Every commit once: a merge of a first-parent walk with its first
        # parent, any other commit the plain way, which is the same in every
        # walk. The commits stay in the order of the walks, so that those of
        # one process are neighbors in the history.
        plain_commits: dict[str, None] = {}
        merge_commits: dict[str, None] = {}
        # the commits with one parent: what they add is read off the plain count
        one_parent: set[str] = set()
        for (_, first_parent), rows in zip(passes, walks):
            one_parent.update(
                commit for commit, parents, _ in rows if parents and " " not in parents
            )
            if first_parent:
                merge_commits.update(
                    (commit, None) for commit, parents, _ in rows if " " in parents
                )
                plain_commits.update(
                    (commit, None) for commit, parents, _ in rows if " " not in parents
                )
            else:
                plain_commits.update((row[0], None) for row in rows)
        if named_walk is not None:
            # those no walk has the lines counted of are asked for their names
            plain_commits.update((row[0], None) for row in named_walk)
        size = SHORTSTAT_COMMITS_PER_PROCESS
        jobs = [
            (commits[start : start + size], first_parent)
            for commits, first_parent in ((list(plain_commits), False), (list(merge_commits), True))
            for start in range(0, len(commits), size)
        ]
        # Not in the order of the history: recent commits tend to cost more
        # than old ones, and the first shares to be counted say how long the
        # rest will take. Each share comes 0.618 of the list after the one
        # before it, going round, so that the shares counted so far are
        # always spread over the whole history. The order is the same from
        # one run to the next.
        jobs = [
            jobs[index]
            for index in sorted(range(len(jobs)), key=lambda index: index * 0.6180339887498949 % 1)
        ]
        plain: dict[str, str] = {}
        merges: dict[str, str] = {}
        changed: dict[str, str] = {}
        added: dict[str, int] = dict.fromkeys(one_parent, 0)
        added.update(dict.fromkeys(merge_commits, 0))
        timer = threading.Thread(target=allow_more, name="git-shortstat-more", daemon=True)
        timer.start()
        source_added = 0
        moved: dict[str, list[str]] = {}
        try:
            for (_, first_parent), (found, files, their_names, source_count, moved_in) in zip(
                jobs, pool.map(counts, jobs)
            ):
                source_added += source_count
                moved.update(moved_in)
                if first_parent:
                    merges.update(found)
                    added.update(files)
                else:
                    plain.update(found)
                    changed.update(their_names)
                    # not the merges, which the plain count shows nothing of, nor
                    # the commits without parents
                    added.update(
                        (commit, change) for commit, change in files.items() if commit in one_parent
                    )
        except BaseException:
            # git failed for some commits: the others need not be counted
            pool.shutdown(cancel_futures=True)
            raise
        finally:
            counted.set()
            timer.join()

    if with_numstat:
        source_added += _lines_moved_into_source(moved, env)
        source_lines.append(source_added)  # type: ignore[union-attr]
    texts = []
    names_text = None
    try:
        for (_, first_parent), rows in zip(passes, walks):
            # in a first-parent walk the merges have the counts made that way
            under = {**plain, **merges} if first_parent and merges else plain
            texts.append("\n".join([header + under[commit] for commit, _, header in rows]))
        if named_walk is not None:
            names_text = "\n".join([header + changed[commit] for commit, _, header in named_walk])
    except KeyError as missing:
        raise subprocess.CalledProcessError(
            1, ["git", "log", "--shortstat", "--no-walk"], f"nothing printed for {missing}"
        ) from None
    return texts, added, names_text


# a path git quoted (core.quotePath, and always one with a double quote, a
# backslash or a control character): in double quotes, with C escapes
_QUOTED = r'"(?:[^"\\]|\\.)*"'
_QUOTED_PATH = re.compile(_QUOTED, re.DOTALL)
# a C escape: an octal byte, or a character
_C_ESCAPE = re.compile(rb"\\([0-7]{3}|.)", re.DOTALL)
_C_ESCAPES = {
    b"a": b"\a",
    b"b": b"\b",
    b"t": b"\t",
    b"n": b"\n",
    b"v": b"\v",
    b"f": b"\f",
    b"r": b"\r",
}
# a renamed file as --numstat names it when a name is quoted: "old" => "new",
# either of them quoted
_QUOTED_RENAME = re.compile(f'({_QUOTED}|[^"]*) => ({_QUOTED}|[^"]*)', re.DOTALL)
# the part of a renamed file's path that changed: "a/{old => new}/b"
_RENAMED_PART = re.compile(r"\{([^{}]*) => ([^{}]*)\}")


def unquote_path(path: str) -> str:
    """A path as git prints it, without the quotes and escapes git may have
    put in (``"r\\303\\251sum\\303\\251.py"`` is ``résumé.py``), so that it is the
    path ``git ls-tree -z`` gives."""
    if not _QUOTED_PATH.fullmatch(path):
        return path
    data = _C_ESCAPE.sub(
        lambda escape: (
            bytes([int(escape[1], 8)])
            if len(escape[1]) == 3
            else _C_ESCAPES.get(escape[1], escape[1])
        ),
        path[1:-1].encode("utf-8"),
    )
    return data.decode("utf-8", errors="replace")


def numstat_paths(printed: str) -> tuple[str, str]:
    """The path a file has before and after a commit, from what --numstat
    prints: ``"a/{old => new}/b"``, ``old => new``, ``"old" => "new"`` for a
    renamed file, and the same path twice for any other."""
    if '"' in printed:
        renamed = _QUOTED_RENAME.fullmatch(printed)
        if renamed:
            return unquote_path(renamed[1]), unquote_path(renamed[2])
        return unquote_path(printed), unquote_path(printed)
    if " => " not in printed:
        return printed, printed
    if "{" in printed:
        # "{ => sub}/x" or "a/{b => }/x": a folder that is on one side only
        return (
            _RENAMED_PART.sub(r"\1", printed).replace("//", "/").strip("/"),
            _RENAMED_PART.sub(r"\2", printed).replace("//", "/").strip("/"),
        )
    old, _, new = printed.rpartition(" => ")
    return old, new


def numstat_path(path: str) -> str:
    """The path a file has after a commit, from what --numstat prints."""
    return numstat_paths(path)[1]


def _source_lines_of(
    numstat: Iterable[str], source: Callable[[str], bool]
) -> tuple[int, list[str]]:
    """The lines a commit adds to the project's own source, from the lines of
    its ``--numstat``, and the files it moves into the source.

    A file counts when ``source`` takes its path after the commit for the
    project's own. A file renamed within the source counts what was added to
    it; one moved out of the source counts nothing. One moved into it, from
    a vendored folder say, brings all of its lines with it, which the
    numstat of a rename does not say: those files are returned, for
    _lines_moved_into_source() to count.
    """
    added = 0
    moved_in = []
    for line in numstat:
        # "<added>\t<removed>\t<path>", "-" for a binary file
        if line[:1].isdigit():
            lines, _, rest = line.partition("\t")
            old, new = numstat_paths(rest.partition("\t")[2])
            if not source(new):
                continue
            if old == new or source(old):
                added += int(lines)
            else:
                moved_in.append(new)
    return added, moved_in


def _lines_moved_into_source(moved: dict[str, list[str]], env: dict[str, str] | None = None) -> int:
    """The lines of the files commits moved into the project's own source:
    commit -> the files it moved there. They are what the diff of each
    commit adds to them when it is not looking for renames, in one git
    process. Raises subprocess.CalledProcessError when git fails."""
    if not moved:
        return 0
    text = _git_text(
        [
            "-c",
            "core.quotePath=false",
            "log",
            "--no-walk",
            "--stdin",
            "--no-renames",
            "--numstat",
            "--format=%x01%H",
        ],
        "\n".join(moved) + "\n",
        env,
    )
    total = 0
    for block in text.split(_COMMIT_MARK)[1:]:
        commit, _, under = block.partition("\n")
        wanted = set(moved.get(commit, ()))
        for line in under.split("\n"):
            if line[:1].isdigit():
                lines, _, rest = line.partition("\t")
                if unquote_path(rest.partition("\t")[2]) in wanted:
                    total += int(lines)
    return total


# the options of a `git log` whose output source_lines_added() reads
SOURCE_LINES_LOG = "-c core.quotePath=false log --root --numstat --format=%x01%H"


def source_lines_added(printed: str, source: Callable[[str], bool]) -> int:
    """The lines ever added to the files ``source`` takes for the project's
    own, from what ``git SOURCE_LINES_LOG <range>`` prints: every commit but
    the merges, whose diffs that command does not show, once.

    The count shortstat_logs() makes beside the others when it is asked to,
    by the same rules (see _source_lines_of()), for a run that does not
    have it make them. Raises subprocess.CalledProcessError when git fails
    to count the files moved into the source.
    """
    added = 0
    moved: dict[str, list[str]] = {}
    for block in printed.split(_COMMIT_MARK)[1:]:
        commit, _, under = block.partition("\n")
        lines, moved_in = _source_lines_of(under.split("\n"), source)
        added += lines
        if moved_in:
            moved[commit] = moved_in
    return added + _lines_moved_into_source(moved)


# "<commit>\t<tree>\t<parents>\t<stamp> <author>", a commit of the history
_HISTORY_ROW = re.compile(r"^([0-9a-f]+)\t([0-9a-f]+)\t([0-9a-f ]*)\t(.*)$", re.MULTILINE)


def history_graph(rev: str) -> History:
    """Read the commits leading to ``rev``, with what joins them, in one `git log`.

    The tags and the number of files of each commit are both worked out from
    it, where each used to walk the history again, or to ask git about every
    commit. A parent git does not have, as at the edge of a shallow clone, is
    left out; the header of a commit is what ``git log --format="%at %aN"``
    prints for it.
    """
    rows = _HISTORY_ROW.findall(
        get_pipe_output(
            [
                'git log --topo-order --format="%H%x09%T%x09%P%x09%at %aN" --end-of-options '
                + shlex.quote(rev)
            ]
        )
    )
    place = {row[0]: index for index, row in enumerate(rows)}
    named = [row[2].split() for row in rows]
    return History(
        place=place,
        commits=[row[0] for row in rows],
        trees=[row[1] for row in rows],
        parents=[[place[parent] for parent in hashes if parent in place] for hashes in named],
        first_parents=[place.get(hashes[0], -1) if hashes else -1 for hashes in named],
        headers=[row[3] for row in rows],
    )


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


# the key the commits of a week are kept under: the ISO year and week, which
# start on a Monday and do not split the week of New Year ("2025-01")
WEEK_KEY = "%G-%V"


def get_log_range(defaultrange: str = "HEAD", end_only: bool = True, authors: bool = True) -> str:
    """The options and revisions of the commits to read, for a `git log`
    command line: the date and author filters, then ``--end-of-options``
    (git 2.24 and later) and the range, each quoted for shlex.split().
    Nothing may follow it but ``-- <paths>``. Without ``authors``, the
    authors filter is left out.

    For `git log` only: ``--author`` matches the names after .mailmap there,
    and the names as committed in `git rev-list` and `git shortlog`.
    """
    commit_range = get_commit_range(defaultrange, end_only)
    # Build git log options
    options = []

    # Date range filtering
    if len(load_config()["start_date"]) > 0:
        options.append("--since=" + shlex.quote(load_config()["start_date"]))
    if len(load_config()["end_date"]) > 0:
        options.append("--until=" + shlex.quote(load_config()["end_date"]))

    # Author filtering
    if authors and len(load_config()["authors"]) > 0:
        authors_list = [
            author.strip() for author in load_config()["authors"].split(",") if author.strip()
        ]
        for author in authors_list:
            options.append("--author=" + shlex.quote(author))

    # whatever the configuration says, git reads the range as revisions, each
    # quoted on its own (the last commits are a tip and the commits they leave out)
    return " ".join(
        [*options, "--end-of-options", *(shlex.quote(part) for part in commit_range.split(" "))]
    )


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
