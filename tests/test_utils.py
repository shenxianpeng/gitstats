"""Tests for gitstats.utils – pure logic and git helper functions."""

import os

import pytest

from gitstats.utils import (
    get_stat_summary_counts,
    count_lines_in_text,
    filter_lines_by_pattern,
    should_exclude_file,
    get_excluded_extensions,
    get_version,
    get_commit_range,
    get_log_range,
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


# ── get_log_range ────────────────────────────────────────────────────────

def test_get_log_range_default():
    _set_config(start_date="", end_date="", authors="", commit_begin="", commit_end="HEAD")
    assert get_log_range() == "HEAD"


def test_get_log_range_with_dates():
    _set_config(start_date="2023-01-01", end_date="2023-12-31", authors="", commit_begin="", commit_end="HEAD")
    result = get_log_range()
    assert '--since="2023-01-01"' in result
    assert '--until="2023-12-31"' in result


def test_get_log_range_with_authors():
    _set_config(start_date="", end_date="", authors="Alice,Hui", commit_begin="", commit_end="HEAD")
    result = get_log_range()
    assert '--author="Alice"' in result
    assert '--author="Hui"' in result
