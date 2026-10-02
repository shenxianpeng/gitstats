"""Tests for gitstats.utils – pure logic and git helper functions."""

import datetime
import hashlib
import logging
import subprocess
from importlib.metadata import PackageNotFoundError
from unittest.mock import patch

import pytest

from gitstats.utils import (
    _run_pipe_chain,
    count_lines_in_text,
    filter_lines_by_pattern,
    format_bytes,
    format_duration,
    format_int,
    get_commit_range,
    get_excluded_extensions,
    get_log_range,
    get_num_of_files_from_rev,
    get_num_of_lines_in_blob,
    get_pipe_output,
    get_stat_summary_counts,
    get_version,
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


# ── get_num_of_lines_in_blob / get_num_of_files_from_rev ─────────────────
# Data collection runs these in worker processes; here they run in-process.


def _rev_parse(repo, rev):
    return subprocess.run(
        ["git", "rev-parse", rev], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_get_num_of_lines_in_blob_counts_text_lines(git_repo, monkeypatch):
    monkeypatch.chdir(git_repo)
    blob = _rev_parse(git_repo, "HEAD:utils.py")
    assert get_num_of_lines_in_blob(("py", blob)) == ("py", blob, 5)


def test_get_num_of_lines_in_blob_binary_counts_zero(git_repo, monkeypatch):
    monkeypatch.chdir(git_repo)
    blob = _rev_parse(git_repo, "HEAD:logo.png")
    assert get_num_of_lines_in_blob(("png", blob)) == ("png", blob, 0)


def test_get_num_of_lines_in_blob_excluded_extension_is_not_read():
    _set_config(exclude_exts="png")
    with patch("gitstats.utils.subprocess.check_output") as check_output:
        assert get_num_of_lines_in_blob(("png", "abc123")) == ("png", "abc123", 0)
    check_output.assert_not_called()


def test_get_num_of_lines_in_blob_unreadable_blob_counts_zero(git_repo, monkeypatch):
    monkeypatch.chdir(git_repo)
    missing = "0" * 40
    assert get_num_of_lines_in_blob(("py", missing)) == ("py", missing, 0)


def test_get_num_of_files_from_rev(git_repo, monkeypatch):
    monkeypatch.chdir(git_repo)
    head = _rev_parse(git_repo, "HEAD")
    first = _rev_parse(git_repo, "HEAD~4")
    assert get_num_of_files_from_rev(("1683000000", head)) == (1683000000, head, 5)
    assert get_num_of_files_from_rev(("1673776800", first)) == (1673776800, first, 2)
