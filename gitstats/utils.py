# Copyright (c) 2007-2014 Heikki Hokkanen <hoxu@users.sf.net> & others contributors
# GPLv2 / GPLv3
# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
import datetime
import logging
import os
import re
import shlex
import subprocess
import tempfile
import time
from collections.abc import Iterable, Iterator
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
