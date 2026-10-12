"""Tests for gitstats.utils – pure logic and git helper functions."""

import datetime
import hashlib
import io
import logging
import os
import subprocess
from importlib.metadata import PackageNotFoundError
from unittest.mock import patch

import pytest

from gitstats.utils import (
    _run_pipe_chain,
    commit_local_time,
    commits_reached,
    count_files_in_trees,
    count_lines_in_blobs,
    count_lines_in_text,
    filter_lines_by_pattern,
    format_bytes,
    format_duration,
    format_int,
    get_commit_range,
    get_excluded_extensions,
    get_log_range,
    get_num_of_files_from_rev,
    get_pipe_output,
    get_stat_summary_counts,
    get_version,
    history_graph,
    shortstat_logs,
    should_exclude_file,
)

# ── get_stat_summary_counts ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "line,expected",
    [
        # standard: files, insertions, deletions
        (" 3 files changed, 100 insertions(+), 50 deletions(-)", ["3", "100", "50"]),
        # singular "file"
        (" 1 file changed, 10 insertions(+), 5 deletions(-)", ["1", "10", "5"]),
        # insertions only – appends int 0 for deletions
        (" 1 file changed, 30 insertions(+)", ["1", "30", 0]),
        # deletions only – inserts int 0 for insertions
        (" 2 files changed, 20 deletions(-)", ["2", 0, "20"]),
        # zero files changed – appends two int 0s
        (" 0 files changed", ["0", 0, 0]),
        # large numbers
        (
            " 10 files changed, 9999 insertions(+), 888 deletions(-)",
            ["10", "9999", "888"],
        ),
        # no changes at all
        (" 1 file changed", ["1", 0, 0]),
        # real git output format
        (
            " 5 files changed, 243 insertions(+), 128 deletions(-)",
            ["5", "243", "128"],
        ),
        # merge commit with no changes
        (" 0 files changed, 0 insertions(+), 0 deletions(-)", ["0", "0", "0"]),
    ],
)
def test_get_stat_summary_counts(line, expected):
    assert get_stat_summary_counts(line) == expected


def test_get_stat_summary_counts_unexpected_format():
    """Line with only non-numeric content should return empty list."""
    result = get_stat_summary_counts("no numbers here")
    assert result == []


# ── count_lines_in_text ──────────────────────────────────────────────────


def test_count_lines_in_text_basic():
    assert count_lines_in_text("a\nb\nc\n") == 3
    assert count_lines_in_text("single line") == 1


def test_count_lines_in_text_empty():
    assert count_lines_in_text("") == 0
    assert count_lines_in_text(None) == 0
    assert count_lines_in_text("   \n  \n   ") == 0


def test_count_lines_in_text_trailing_newline():
    assert count_lines_in_text("a\nb\nc") == 3


# ── filter_lines_by_pattern ──────────────────────────────────────────────


def test_filter_lines_by_pattern_basic():
    text = "line1\ncomment: foo\nline2\ncomment: bar\n"
    result = filter_lines_by_pattern(text, r"comment.*")
    assert "comment" not in result
    assert "line1" in result
    assert "line2" in result


def test_filter_lines_by_pattern_no_match():
    text = "a\nb\nc\n"
    assert filter_lines_by_pattern(text, r"xyz") == text


def test_filter_lines_by_pattern_empty():
    assert filter_lines_by_pattern("", r".*") == ""
    assert filter_lines_by_pattern("   \n", r".*") == ""


# ── should_exclude_file / get_excluded_extensions ────────────────────────


def _set_config(**kwargs):
    """Helper: set the gitstats config across all modules."""
    import gitstats
    import gitstats.utils

    cfg = dict(gitstats.DEFAULT_CONFIG, **kwargs)
    gitstats._config = cfg
    # Also update module-level conf variables
    gitstats.utils.conf = cfg
    gitstats.main.conf = cfg
    gitstats.report_creator.conf = cfg


def test_should_exclude_when_config_empty():
    """When exclude_exts is empty, no file should be excluded."""
    _set_config(exclude_exts="")
    assert not should_exclude_file("png")
    assert not should_exclude_file("py")
    assert not should_exclude_file("bin")


def test_should_exclude_matching():
    """Files with excluded extensions should be marked."""
    _set_config(exclude_exts="png,jpg,bin")
    assert should_exclude_file("png")
    assert should_exclude_file("PNG")  # case-insensitive
    assert should_exclude_file("jpg")
    assert should_exclude_file("bin")
    assert not should_exclude_file("py")
    assert not should_exclude_file("")


def test_should_exclude_spaces_in_config():
    """Config values with spaces should be trimmed."""
    _set_config(exclude_exts=" png , jpg ")
    assert should_exclude_file("png")
    assert should_exclude_file("jpg")


def test_get_excluded_extensions_empty():
    _set_config(exclude_exts="")
    assert get_excluded_extensions() == set()


def test_get_excluded_extensions_values():
    _set_config(exclude_exts="png,jpg,class")
    assert get_excluded_extensions() == {"png", "jpg", "class"}


# ── get_version ──────────────────────────────────────────────────────────


def test_get_version():
    v = get_version()
    assert v  # not empty
    assert isinstance(v, str)


def test_get_version_from_a_source_checkout():
    """Without installed package metadata the version reads "dev"."""
    with patch("gitstats.utils.version", side_effect=PackageNotFoundError("gitstats")):
        assert get_version() == "dev"


# ── get_commit_range ─────────────────────────────────────────────────────


def test_get_commit_range_default():
    _set_config(commit_begin="", commit_end="HEAD")
    assert get_commit_range("HEAD") == "HEAD"


def test_get_commit_range_custom():
    _set_config(commit_begin="v1.0.0", commit_end="v2.0.0")
    assert get_commit_range() == "v1.0.0..v2.0.0"


def test_get_commit_range_end_only():
    _set_config(commit_begin="", commit_end="HEAD")
    assert get_commit_range("HEAD", end_only=True) == "HEAD"


def test_get_commit_range_numeric_begin():
    """commit_begin as a number means 'N commits ago from commit_end'."""
    _set_config(commit_begin="10", commit_end="HEAD")
    assert get_commit_range() == "HEAD~10..HEAD"


def test_get_commit_range_without_commit_end_uses_the_default():
    _set_config(commit_begin="v1.0.0", commit_end="")
    assert get_commit_range("HEAD") == "HEAD"
    assert get_commit_range("main", end_only=True) == "main"


# ── get_log_range ────────────────────────────────────────────────────────


def test_get_log_range_default():
    _set_config(start_date="", end_date="", authors="", commit_begin="", commit_end="HEAD")
    assert get_log_range() == "HEAD"


def test_get_log_range_with_dates():
    _set_config(
        start_date="2023-01-01",
        end_date="2023-12-31",
        authors="",
        commit_begin="",
        commit_end="HEAD",
    )
    result = get_log_range()
    assert '--since="2023-01-01"' in result
    assert '--until="2023-12-31"' in result


def test_get_log_range_with_authors():
    _set_config(start_date="", end_date="", authors="Alice,Hui", commit_begin="", commit_end="HEAD")
    result = get_log_range()
    assert '--author="Alice"' in result
    assert '--author="Hui"' in result


# ── format_int ───────────────────────────────────────────────────────────


def test_format_int_thousands():
    assert format_int(44025623) == "44,025,623"
    assert format_int(1020339) == "1,020,339"


def test_format_int_small_numbers_unchanged():
    assert format_int(0) == "0"
    assert format_int(999) == "999"


def test_format_int_numeric_strings():
    assert format_int("1234") == "1,234"


def test_format_int_non_numeric_passthrough():
    assert format_int("n/a") == "n/a"
    assert format_int(None) == "None"


# ── format_bytes / format_duration ───────────────────────────────────────


@pytest.mark.parametrize(
    "size,expected",
    [
        (0, "0 bytes"),
        (512.4, "512 bytes"),
        (2000, "2.0 KB"),
        (161307.78, "157.5 KB"),
        (5 * 1024 * 1024, "5.0 MB"),
        (3 * 1024**4, "3072.0 GB"),
    ],
)
def test_format_bytes(size, expected):
    assert format_bytes(size) == expected


@pytest.mark.parametrize(
    "delta,expected",
    [
        (datetime.timedelta(hours=5), "< 1 d"),
        (datetime.timedelta(days=9, hours=6), "9 d"),
        (datetime.timedelta(days=62), "2 mo"),
        (datetime.timedelta(days=359), "12 mo"),
        (datetime.timedelta(days=2657, hours=2), "7.3 yr"),
    ],
)
def test_format_duration(delta, expected):
    assert format_duration(delta) == expected


# ── get_pipe_output / _run_pipe_chain ────────────────────────────────────


def test_run_pipe_chain_without_commands():
    assert _run_pipe_chain([]) == b""


def test_run_pipe_chain_feeds_each_command_the_previous_output():
    version = subprocess.run(["git", "--version"], capture_output=True, check=True).stdout
    blob_id = hashlib.sha1(b"blob %d\0" % len(version) + version).hexdigest()
    assert _run_pipe_chain(["git --version", "git hash-object --stdin"]).strip() == blob_id.encode()


def test_get_pipe_output_echoes_commands_on_a_linux_terminal(caplog):
    with (
        patch("gitstats.utils.ON_LINUX", True),
        patch("gitstats.utils.os.isatty", return_value=True),
        caplog.at_level(logging.DEBUG, logger="gitstats"),
    ):
        output = get_pipe_output(["git --version"])
    assert output.startswith("git version")
    assert [r.message for r in caplog.records if r.message.startswith(">> ")] == [
        ">> git --version"
    ]


def test_get_pipe_output_quiet_logs_nothing(caplog):
    with caplog.at_level(logging.DEBUG, logger="gitstats"):
        output = get_pipe_output(["git --version"], quiet=True)
    assert output.startswith("git version")
    assert caplog.records == []


# ── get_num_of_files_from_rev ────────────────────────────────────────────
# Data collection runs this in worker processes; here it runs in-process.


def _rev_parse(repo, rev):
    return subprocess.run(
        ["git", "rev-parse", rev], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_get_num_of_files_from_rev(git_repo, monkeypatch):
    monkeypatch.chdir(git_repo)
    head = _rev_parse(git_repo, "HEAD")
    first = _rev_parse(git_repo, "HEAD~4")
    assert get_num_of_files_from_rev(("1683000000", head)) == (1683000000, head, 5)
    assert get_num_of_files_from_rev(("1673776800", first)) == (1673776800, first, 2)


# ── count_files_in_trees / count_lines_in_blobs ──────────────────────────
# The same numbers, from one git process instead of one per commit or blob.


def _git(repo, *args, **env):
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        # git writes UTF-8 whatever the locale: on Windows the default would
        # read an author's "ë" as two other characters
        encoding="utf-8",
        check=True,
        env={**os.environ, **env},
    ).stdout


def _trees_by_ls_tree(repo, rev="HEAD"):
    """tree -> its number of files, counted the old way for every commit."""
    trees = _git(repo, "log", "--format=%T", rev).split()
    return {tree: get_num_of_files_from_rev(("0", tree))[2] for tree in trees}


def _tree(repo, rev):
    return _git(repo, "log", "-1", "--format=%T", rev).strip()


@pytest.fixture
def tangled_repo(temp_dir):
    """A history with what a file count can trip over: deletions, a merge, a
    directory that becomes a file, a submodule, a second root and a commit
    that changes nothing."""
    repo = os.path.join(temp_dir, "tangled")
    os.makedirs(repo)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.name", "Ann")
    _git(repo, "config", "user.email", "ann@example.com")

    def write(**files):
        for name, text in files.items():
            path = os.path.join(repo, *name.split("__"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(text)

    def commit(message, *extra):
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", message, *extra)

    write(**{"a.txt": "a\n", "b.txt": "b\n", "lib__x.py": "x\n", "lib__y.py": "y\n"})
    commit("four files")
    _git(repo, "checkout", "-q", "-b", "side")
    os.remove(os.path.join(repo, "a.txt"))
    write(**{"lib__deep__z.py": "z\n", "side.txt": "s\n"})
    commit("side: delete one, add two")
    _git(repo, "checkout", "-q", "main")
    write(**{"c.txt": "c\n"})
    commit("main: add one")
    _git(repo, "merge", "-q", "--no-ff", "-m", "merge side", "side")
    # the directory lib (three files) becomes a file called lib
    _git(repo, "rm", "-q", "-r", "lib")
    write(lib="not a directory any more\n")
    commit("lib is a file now")
    head = _git(repo, "rev-parse", "HEAD").strip()
    _git(repo, "update-index", "--add", "--cacheinfo", f"160000,{head},vendor/sub")
    _git(repo, "commit", "-q", "-m", "a submodule")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "nothing changes")
    # a second root, merged in
    _git(repo, "checkout", "-q", "--orphan", "other")
    _git(repo, "rm", "-q", "-r", "-f", ".")
    write(**{"other__one.md": "1\n", "other__two.md": "2\n"})
    commit("another beginning")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "-q", "--allow-unrelated-histories", "-m", "merge other", "other")
    return repo


def test_count_files_in_trees_counts_as_ls_tree_does(git_repo, monkeypatch):
    monkeypatch.chdir(git_repo)
    expected = _trees_by_ls_tree(git_repo)
    assert sorted(expected.values()) == [2, 3, 3, 4, 5]
    assert count_files_in_trees("HEAD", set(expected), {}) == expected


def test_count_files_in_trees_follows_a_tangled_history(tangled_repo, monkeypatch):
    monkeypatch.chdir(tangled_repo)
    expected = _trees_by_ls_tree(tangled_repo)
    # nine commits; the one that changes nothing has its parent's tree
    assert len(expected) == 8
    assert count_files_in_trees("HEAD", set(expected), {}) == expected
    # the merge of the second root ends with everything: b, c, side.txt, lib,
    # the submodule and the two files of the other history
    assert expected[_tree(tangled_repo, "HEAD")] == 7
    # and a merge is counted from its first parent, not from both
    assert expected[_tree(tangled_repo, "HEAD~4")] == 6


def test_count_files_in_trees_counts_what_is_asked_and_what_leads_to_it(git_repo, monkeypatch):
    monkeypatch.chdir(git_repo)
    expected = _trees_by_ls_tree(git_repo)
    middle = _tree(git_repo, "HEAD~2")
    counts = count_files_in_trees("HEAD", {middle}, {})
    # the third commit, and the two before it that its count is built on
    assert counts == {
        tree: expected[tree] for tree in _git(git_repo, "log", "--format=%T", "HEAD~2").split()
    }
    assert len(counts) == 3


def test_count_files_in_trees_starts_from_the_trees_it_knows(git_repo, monkeypatch):
    import gitstats.utils as utils

    monkeypatch.chdir(git_repo)
    expected = _trees_by_ls_tree(git_repo)
    newest = _tree(git_repo, "HEAD")
    known = {tree: count for tree, count in expected.items() if tree != newest}

    compared = []
    real = utils._git_lines

    def spy(args, stdin=None):
        if stdin is not None:
            compared.extend(line for line in stdin.read().split("\n") if line)
            stdin.seek(0)
        return real(args, stdin)

    monkeypatch.setattr(utils, "_git_lines", spy)
    assert count_files_in_trees("HEAD", {newest}, known) == {newest: expected[newest]}
    # one commit was compared with its parent, not the whole history
    head, parent = _git(git_repo, "rev-parse", "HEAD", "HEAD~1").split()
    assert compared == [f"{head} {parent}"]

    # nothing to count: git is not asked to compare anything
    compared.clear()
    assert count_files_in_trees("HEAD", set(), expected) == {}
    assert count_files_in_trees("HEAD", {newest}, expected) == {}
    assert compared == []


def test_count_files_in_trees_of_a_shallow_clone(git_repo, temp_dir, monkeypatch):
    shallow = os.path.join(temp_dir, "shallow")
    _git(temp_dir, "clone", "-q", "--depth", "2", "file://" + git_repo, shallow)
    monkeypatch.chdir(shallow)
    expected = _trees_by_ls_tree(shallow)
    # the older of the two commits has a parent that was not fetched
    assert sorted(expected.values()) == [4, 5]
    assert count_files_in_trees("HEAD", set(expected), {}) == expected


def test_count_files_in_trees_leaves_out_what_it_cannot_find(git_repo, monkeypatch):
    monkeypatch.chdir(git_repo)
    unknown = "f" * 40
    assert count_files_in_trees("HEAD", {unknown}, {}) == {}
    # a revision git does not know: nothing is counted, nothing is raised
    assert count_files_in_trees("no-such-branch", {_tree(git_repo, "HEAD")}, {}) == {}


def test_count_files_in_trees_reads_two_listings(monkeypatch):
    """What it asks git for, and what it makes of the answers."""
    import gitstats.utils as utils

    asked = []

    def fake(args, stdin=None):
        asked.append((args[0], stdin.read() if stdin is not None else None))
        if args[0] == "log":
            # commit, tree, parents, oldest first; a line that is none of that is passed over
            return iter([b"", b"oops", b"c1 t1 ", b"c2 t2 c1", b"c3 t3 c2 c9"])
        # the files each commit added to and deleted from its first parent
        return iter([b"c1", b"A\ta", b"A\tb", b"A\tc", b"c3", b"D\ta", b"D\tb", b"A\td"])

    monkeypatch.setattr(utils, "_git_lines", fake)
    # c2 changed no file list: it is not in the answer, and has its parent's count
    assert count_files_in_trees("main", {"t3"}, {}) == {"t1": 3, "t2": 3, "t3": 2}
    assert asked == [("log", None), ("diff-tree", "c1\nc2 c1\nc3 c2\n")]

    # with t2 known, only c3 is compared, and counted from there
    asked.clear()
    assert count_files_in_trees("main", {"t3"}, {"t2": 10}) == {"t3": 9}
    assert asked[1] == ("diff-tree", "c3 c2\n")


def test_count_files_in_trees_counts_nothing_when_git_fails_half_way(monkeypatch):
    import gitstats.utils as utils

    def failing(args, stdin=None):
        if args[0] == "log":
            yield from (b"c1 t1 ", b"c2 t2 c1")
            return
        # the comparison dies after its first commit
        yield from (b"c1", b"A\ta")
        raise subprocess.CalledProcessError(128, ["git", *args])

    monkeypatch.setattr(utils, "_git_lines", failing)
    # c2 would be counted as c1 with nothing added: no answer is better
    assert count_files_in_trees("main", {"t1", "t2"}, {}) == {}


def _lines_one_by_one(repo, blob):
    """The lines of a blob as they were counted before, a process per blob:
    none for a binary one, otherwise those of its text, blank ends aside."""
    content = subprocess.run(
        ["git", "cat-file", "blob", blob], cwd=repo, capture_output=True, check=True
    ).stdout
    if b"\x00" in content[:8192]:
        return 0
    return count_lines_in_text(content.decode("utf-8", errors="replace").rstrip("\n"))


def _blobs(repo):
    """Every blob of HEAD: path -> id."""
    entries = [
        line.split(None, 3) for line in _git(repo, "ls-tree", "-r", "HEAD").split("\n") if line
    ]
    return {entry[3]: entry[2] for entry in entries if entry[1] == "blob"}


def test_count_lines_in_blobs_counts_as_one_by_one(git_repo, monkeypatch):
    monkeypatch.chdir(git_repo)
    blobs = _blobs(git_repo)
    expected = {blob: _lines_one_by_one(git_repo, blob) for blob in blobs.values()}
    counts = count_lines_in_blobs(blobs.values())
    assert counts == expected
    assert counts[blobs["utils.py"]] == 5
    assert counts[blobs["logo.png"]] == 0


def test_count_lines_in_blobs_of_awkward_files(git_repo, monkeypatch):
    files = {
        "empty.txt": b"",
        "no-newline.txt": b"one\ntwo",
        "blank-ends.txt": b"\n\none\n\ntwo\n\n\n",
        "only-blank.txt": b"\n \n\t\n",
        "latin1.txt": b"\xe9t\xe9\n\xfcber\n",
        "crlf.txt": b"one\r\ntwo\r\n",
        # longer than the 8192 bytes read to tell text from binary
        "long.txt": b"line\n" * 5000,
        # a null byte past those 8192 bytes does not make a file binary
        "late-null.txt": b"x\n" * 5000 + b"\x00\n",
        # a binary file longer than the megabyte skipped at a time
        "big.bin": b"\x00" + os.urandom(1_500_000),
        "after-big.txt": b"still\nread\nright\n",
    }
    for name, content in files.items():
        with open(os.path.join(git_repo, name), "wb") as f:
            f.write(content)
    _git(git_repo, "add", "-A")
    _git(git_repo, "commit", "-q", "-m", "awkward files")
    monkeypatch.chdir(git_repo)

    blobs = _blobs(git_repo)
    counts = count_lines_in_blobs(blobs.values())
    assert {name: counts[blobs[name]] for name in files} == {
        "empty.txt": 0,
        "no-newline.txt": 2,
        "blank-ends.txt": 3,
        "only-blank.txt": 0,
        "latin1.txt": 2,
        "crlf.txt": 2,
        "long.txt": 5000,
        "late-null.txt": 5001,
        "big.bin": 0,
        "after-big.txt": 3,
    }
    # and each is what reading the blobs one by one gives
    for name in files:
        assert _lines_one_by_one(git_repo, blobs[name]) == counts[blobs[name]], name


def test_count_lines_in_blobs_that_are_not_there(git_repo, monkeypatch):
    monkeypatch.chdir(git_repo)
    assert count_lines_in_blobs([]) == {}
    blob = _blobs(git_repo)["utils.py"]
    missing = "0" * 40
    tree = _tree(git_repo, "HEAD")
    # a missing object and one that is not a blob count nothing, and do not
    # put the blobs after them out of step; an id given twice is read once
    assert count_lines_in_blobs([missing, blob, tree, blob]) == {missing: 0, blob: 5, tree: 0}


@pytest.mark.parametrize(
    "said",
    [
        # nothing at all
        b"",
        # a binary blob, cut off before its end
        b"aaa blob 5000000\n\x00\x01\x02",
        # a text blob counted, then silence
        b"aaa blob 4\none\n\n",
    ],
)
def test_count_lines_in_blobs_when_git_stops_early(said):
    class Stopped:
        stdout = io.BytesIO(said)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    with patch("gitstats.utils.subprocess.Popen", return_value=Stopped()):
        counts = count_lines_in_blobs(["aaa", "bbb", "ccc"])
    # what was read in full is counted; the rest counts nothing, and nothing hangs
    assert counts == {"aaa": 1 if said.startswith(b"aaa blob 4") else 0, "bbb": 0, "ccc": 0}


# ── commit_local_time ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "offset,expected",
    [
        # 1700000000 is 2023-11-14 22:13:20 UTC
        ("+0000", datetime.datetime(2023, 11, 14, 22, 13, 20)),
        ("+0900", datetime.datetime(2023, 11, 15, 7, 13, 20)),
        ("-0800", datetime.datetime(2023, 11, 14, 14, 13, 20)),
        # offsets are not always whole hours
        ("+0530", datetime.datetime(2023, 11, 15, 3, 43, 20)),
        ("-0330", datetime.datetime(2023, 11, 14, 18, 43, 20)),
    ],
)
def test_commit_local_time_is_the_committers_clock(offset, expected):
    """Whatever the timezone of the machine running the tests."""
    assert commit_local_time(1700000000, offset) == expected


@pytest.mark.parametrize("offset", ["", "UTC", "+9", "0300", "+2400", "-9960"])
def test_commit_local_time_falls_back_to_this_machines_clock(offset):
    """An offset git would not print, or one no timezone has."""
    assert commit_local_time(1700000000, offset) == datetime.datetime.fromtimestamp(1700000000)


# ── shortstat_logs ───────────────────────────────────────────────────────
# The text of `git log --shortstat`, put together from many git processes.

LINEAR = [("--first-parent", True), ("--date-order", False)]
EVERY_COMMIT = [("", False), ("--date-order", False)]


def _shortstat_commands(passes, log_range):
    """What the commands themselves print, a pass at a time, blank lines aside."""
    outputs = []
    for walk, first_parent in passes:
        extra = walk + (" -m" if first_parent else "")
        output = get_pipe_output(
            [f'git log --shortstat {extra} --pretty=format:"%at %aN" {log_range}']
        )
        outputs.append([line for line in output.split("\n") if line])
    return outputs


def _shortstat_logs(passes, log_range, workers=4):
    return [
        [line for line in text.split("\n") if line]
        for text in shortstat_logs(passes, log_range, workers)
    ]


@pytest.fixture
def merged_repo(tangled_repo):
    """tangled_repo, and on top of it a merge of three branches at once, an
    author whose name is not ASCII and a commit that only renames a file."""
    repo = tangled_repo
    for branch, name in (("one", "one.txt"), ("two", "two.txt")):
        _git(repo, "checkout", "-q", "-b", branch, "main")
        with open(os.path.join(repo, name), "w") as f:
            f.write(f"{branch}\n" * 3)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", f"add {name}")
    _git(repo, "checkout", "-q", "main")
    with open(os.path.join(repo, "b.txt"), "a") as f:
        f.write("more\n")
    _git(repo, "commit", "-q", "-a", "-m", "main moves on")
    _git(repo, "merge", "-q", "--no-ff", "-m", "merge two branches at once", "one", "two")
    _git(repo, "mv", "c.txt", "renamed.txt")
    _git(
        repo,
        "commit",
        "-q",
        "-m",
        "a rename",
        GIT_AUTHOR_NAME="Zoë Müller",
        GIT_AUTHOR_EMAIL="zoe@example.com",
    )
    return repo


@pytest.mark.parametrize("passes", [LINEAR, EVERY_COMMIT])
def test_shortstat_logs_write_what_the_commands_print(git_repo, monkeypatch, passes):
    monkeypatch.chdir(git_repo)
    expected = _shortstat_commands(passes, "HEAD")
    assert _shortstat_logs(passes, "HEAD") == expected
    # five commits, each with the line that counts its changes
    assert len(expected[1]) == 10
    assert expected[1][1].startswith(" 1 file changed, 2 insertions(+)")


@pytest.mark.parametrize("passes", [LINEAR, EVERY_COMMIT])
@pytest.mark.parametrize("per_process", [1, 3, 1000])
def test_shortstat_logs_of_a_history_with_merges(merged_repo, monkeypatch, passes, per_process):
    import gitstats.utils as utils

    monkeypatch.chdir(merged_repo)
    monkeypatch.setattr(utils, "SHORTSTAT_COMMITS_PER_PROCESS", per_process)
    expected = _shortstat_commands(passes, "HEAD")
    assert _shortstat_logs(passes, "HEAD", workers=3) == expected

    counted = [line for line in expected[0] if "changed" in line]
    headers = [line for line in expected[0] if "changed" not in line]
    if passes is LINEAR:
        # along the first parents every commit but the empty one has a count,
        # the three merges among them
        assert len(counted) == len(headers) - 1
    else:
        # among all the commits, the three merges and the empty one have none
        assert len(counted) == len(headers) - 4
    assert any(line.endswith(" Zoë Müller") for line in headers)


@pytest.mark.parametrize(
    "log_range",
    [
        '--since="2023-03-01" "HEAD"',
        '--until="2023-03-01" "HEAD"',
        '--author="Bob Jones" "HEAD"',
        '--author="Alice Smith" --author="Bob Jones" "HEAD"',
        "HEAD~3..HEAD",
        '--since="2023-02-01" --until="2023-04-30" "v1.0.0..HEAD"',
        '--author="Nobody" "HEAD"',
    ],
)
def test_shortstat_logs_keep_to_the_range(git_repo, monkeypatch, log_range):
    monkeypatch.chdir(git_repo)
    assert _shortstat_logs(LINEAR, log_range) == _shortstat_commands(LINEAR, log_range)


def test_shortstat_logs_count_a_commit_once(merged_repo, monkeypatch):
    import gitstats.utils as utils

    monkeypatch.chdir(merged_repo)
    monkeypatch.setattr(utils, "SHORTSTAT_COMMITS_PER_PROCESS", 4)
    asked = {False: [], True: []}
    real = utils._git_text

    def spy(args, data=None, env=None):
        if data is not None:
            asked["--first-parent" in args].extend(data.split())
        return real(args, data, env)

    monkeypatch.setattr(utils, "_git_text", spy)
    shortstat_logs(LINEAR, "HEAD", 3)

    every = _git(merged_repo, "log", "--format=%H", "HEAD").split()
    chain_merges = _git(merged_repo, "log", "--first-parent", "--merges", "--format=%H").split()
    assert len(chain_merges) == 3
    # every commit is asked for the plain way once, though most are in both walks
    assert sorted(asked[False]) == sorted(every)
    # and the merges along the first parents once more, against their first parent
    assert sorted(asked[True]) == sorted(chain_merges)

    # when no walk compares merges with a parent, nothing is asked that way
    asked[False].clear()
    asked[True].clear()
    shortstat_logs(EVERY_COMMIT, "HEAD", 3)
    assert sorted(asked[False]) == sorted(every)
    assert asked[True] == []


def test_shortstat_logs_with_one_worker_or_none(git_repo, monkeypatch):
    monkeypatch.chdir(git_repo)
    expected = _shortstat_commands(LINEAR, "HEAD")
    assert _shortstat_logs(LINEAR, "HEAD", workers=1) == expected
    assert _shortstat_logs(LINEAR, "HEAD", workers=0) == expected
    assert shortstat_logs([], "HEAD", 4) == []


def test_shortstat_logs_raise_when_git_fails(git_repo, monkeypatch):
    monkeypatch.chdir(git_repo)
    with pytest.raises(subprocess.CalledProcessError):
        shortstat_logs(LINEAR, "no-such-branch", 4)


def test_shortstat_logs_raise_when_git_leaves_a_commit_out(git_repo, monkeypatch):
    import gitstats.utils as utils

    monkeypatch.chdir(git_repo)
    real = utils._git_text

    def forgetful(args, data=None, env=None):
        text = real(args, data, env)
        # the process that counts lines says nothing of its last commit
        return text if data is None else text[: text.rindex(data.split()[-1])]

    monkeypatch.setattr(utils, "_git_text", forgetful)
    monkeypatch.setattr(utils, "SHORTSTAT_COMMITS_PER_PROCESS", 2)
    with pytest.raises(subprocess.CalledProcessError):
        shortstat_logs(LINEAR, "HEAD", 2)


def _busiest(monkeypatch, workers, seconds_per_process, jobs=12):
    """Run shortstat_logs() with a git that takes a moment to count; return
    how many countings were going on at once, at most."""
    import threading
    import time

    import gitstats.utils as utils

    commits = [f"{i:040x}" for i in range(jobs)]
    lock = threading.Lock()
    running = most = 0

    def slow(args, data=None, env=None):
        nonlocal running, most
        if data is None:
            return "".join(f"{commit}\t\t{i} Ann\n" for i, commit in enumerate(commits))
        with lock:
            running += 1
            most = max(most, running)
        time.sleep(0.05)
        with lock:
            running -= 1
        return "".join(f"{commit}\n\n 1 file changed, 1 insertion(+)\n" for commit in data.split())

    monkeypatch.setattr(utils, "_git_text", slow)
    monkeypatch.setattr(utils, "SHORTSTAT_COMMITS_PER_PROCESS", 1)
    monkeypatch.setattr(utils, "SHORTSTAT_SECONDS_PER_PROCESS", seconds_per_process)
    (text,) = shortstat_logs([("", False)], "HEAD", workers)
    # every commit is there, in the order of the walk, with its count under it
    assert [line for line in text.split("\n") if line] == [
        line for i in range(jobs) for line in (f"{i} Ann", " 1 file changed, 1 insertion(+)")
    ]
    return most


def test_shortstat_logs_start_with_two_processes(monkeypatch):
    # with a long wait before a third, two is all there ever is
    assert _busiest(monkeypatch, workers=6, seconds_per_process=60) == 2
    # one worker is one process
    assert _busiest(monkeypatch, workers=1, seconds_per_process=60) == 1


def test_shortstat_logs_add_processes_as_time_passes(monkeypatch):
    # twelve countings of 50 ms, and another process allowed every 10 ms
    most = _busiest(monkeypatch, workers=6, seconds_per_process=0.01)
    assert 2 < most <= 6


def test_shortstat_logs_use_every_process_once_the_counting_is_slow(monkeypatch):
    import gitstats.utils as utils

    # the countings take 50 ms: slow, by this measure, so no waiting for the others
    monkeypatch.setattr(utils, "SHORTSTAT_SLOW_SECONDS", 0.01)
    most = _busiest(monkeypatch, workers=6, seconds_per_process=60, jobs=24)
    assert 2 < most <= 6
    # one counting of 50 ms is not slow when four of them may take 30 ms each:
    # the average has to be reached, by four countings at least
    monkeypatch.setattr(utils, "SHORTSTAT_SLOW_SECONDS", 0.03)
    assert 2 < _busiest(monkeypatch, workers=6, seconds_per_process=60, jobs=24) <= 6
    # and fast by the usual measure: two processes, as long as the wait for a third lasts
    monkeypatch.setattr(utils, "SHORTSTAT_SLOW_SECONDS", 0.35)
    assert _busiest(monkeypatch, workers=6, seconds_per_process=60, jobs=24) == 2


def test_shortstat_logs_count_the_shares_spread_over_the_history(monkeypatch):
    import gitstats.utils as utils

    commits = [f"{i:040x}" for i in range(10)]
    order = []

    def recording(args, data=None, env=None):
        if data is None:
            return "".join(f"{commit}\t\t1 Ann\n" for commit in commits)
        order.append(int(data.split()[0], 16))
        return data

    monkeypatch.setattr(utils, "_git_text", recording)
    monkeypatch.setattr(utils, "SHORTSTAT_COMMITS_PER_PROCESS", 1)
    shortstat_logs([("", False)], "HEAD", 1)
    # ten shares of one commit, one process: each share is a good half of the
    # list after the one before, and any few in a row cover the whole of it
    assert order == [0, 5, 2, 7, 4, 9, 1, 6, 3, 8]


def test_shortstat_logs_stop_counting_when_git_fails(monkeypatch):
    import time

    import gitstats.utils as utils

    commits = [f"{i:040x}" for i in range(40)]
    asked = []

    def failing(args, data=None, env=None):
        if data is None:
            return "".join(f"{commit}\t\t1 Ann\n" for commit in commits)
        asked.append(data)
        time.sleep(0.02)
        raise subprocess.CalledProcessError(128, ["git", *args])

    monkeypatch.setattr(utils, "_git_text", failing)
    monkeypatch.setattr(utils, "SHORTSTAT_COMMITS_PER_PROCESS", 1)
    monkeypatch.setattr(utils, "SHORTSTAT_SECONDS_PER_PROCESS", 60)
    with pytest.raises(subprocess.CalledProcessError):
        shortstat_logs([("", False)], "HEAD", 2)
    # the countings that had not begun were called off
    assert len(asked) < len(commits)


# ── history_graph / commits_reached ──────────────────────────────────────
# The commits a tag adds to the tag before it, without a `git log` per tag.


def test_history_graph_lists_a_commit_before_its_parents(merged_repo, monkeypatch):
    monkeypatch.chdir(merged_repo)
    place, parents, headers = history_graph("HEAD")

    commits = _git(merged_repo, "rev-list", "HEAD").split()
    assert sorted(place) == sorted(commits)
    assert sorted(place.values()) == list(range(len(commits)))
    assert len(parents) == len(headers) == len(commits)
    by_place = {index: commit for commit, index in place.items()}
    for commit, index in place.items():
        # the parents git names, and each of them further down the list
        named = _git(merged_repo, "log", "-1", "--format=%P", commit).split()
        assert [by_place[parent] for parent in parents[index]] == named
        assert all(parent > index for parent in parents[index])
        assert headers[index] == _git(merged_repo, "log", "-1", "--format=%at %aN", commit).strip()
    # HEAD comes first; the two roots and the merge of three branches are there
    assert place[commits[0]] == 0
    assert sorted(len(p) for p in parents).count(0) == 2
    assert max(len(p) for p in parents) == 3
    assert any(header.endswith(" Zoë Müller") for header in headers)


def test_history_graph_of_another_revision_and_of_a_shallow_clone(git_repo, temp_dir, monkeypatch):
    monkeypatch.chdir(git_repo)
    place, parents, _ = history_graph("HEAD~2")
    assert len(place) == 3
    assert parents == [[1], [2], []]

    shallow = os.path.join(temp_dir, "shallow")
    _git(temp_dir, "clone", "-q", "--depth", "2", "file://" + git_repo, shallow)
    monkeypatch.chdir(shallow)
    place, parents, _ = history_graph("HEAD")
    # the parent of the older commit was not fetched: it is left out
    assert parents == [[1], []]


def test_commits_reached_are_those_of_rev_list(merged_repo, monkeypatch):
    """For every pair of commits of a tangled history: the commits that lead
    to the one and not to the other are those `git rev-list` gives."""
    monkeypatch.chdir(merged_repo)
    place, parents, _ = history_graph("HEAD")
    by_place = {index: commit for commit, index in place.items()}
    commits = list(place)
    assert len(commits) == 14

    for tip in commits:
        listed = _git(merged_repo, "rev-list", tip).split()
        reached = commits_reached(parents, place[tip])
        assert sorted(by_place[index] for index in reached) == sorted(listed), tip
        # descendants first
        assert reached == sorted(reached)
        for base in commits:
            listed = _git(merged_repo, "rev-list", tip, "^" + base).split()
            reached = commits_reached(parents, place[tip], place[base])
            assert sorted(by_place[index] for index in reached) == sorted(listed), (tip, base)


def test_commits_reached_stop_where_the_base_takes_over():
    # 0 - 1 - 2 - 3 - 4 - ... - 99, each the child of the next
    chain = [[index + 1] for index in range(99)] + [[]]
    assert commits_reached(chain, 0, 3) == [0, 1, 2]
    assert commits_reached(chain, 3, 0) == []
    assert commits_reached(chain, 5, 5) == []
    assert commits_reached(chain, 97) == [97, 98, 99]

    # the walk from 0 to 3 does not go on to the end of the history
    class Counting(list):
        asked = 0

        def __getitem__(self, index):
            Counting.asked += 1
            return super().__getitem__(index)

    assert commits_reached(Counting(chain), 0, 3) == [0, 1, 2]
    assert Counting.asked < 10
