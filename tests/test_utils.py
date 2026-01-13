"""Tests for gitstats.utils module."""

import os
import subprocess
from unittest.mock import patch, MagicMock
import gitstats.utils as utils
import gitstats


def test_count_lines_in_text_empty():
    """Test counting lines in empty text."""
    assert utils.count_lines_in_text("") == 0
    assert utils.count_lines_in_text("   ") == 0
    assert utils.count_lines_in_text(None) == 0


def test_count_lines_in_text_single_line():
    """Test counting lines in single line text."""
    assert utils.count_lines_in_text("hello") == 1


def test_count_lines_in_text_multiple_lines():
    """Test counting lines in multi-line text."""
    text = "line1\nline2\nline3"
    assert utils.count_lines_in_text(text) == 3


def test_filter_lines_by_pattern_empty():
    """Test filtering empty text."""
    assert utils.filter_lines_by_pattern("", "pattern") == ""
    assert utils.filter_lines_by_pattern("   ", "pattern") == ""


def test_filter_lines_by_pattern():
    """Test filtering lines by pattern."""
    text = "commit abc123\nline1\ncommit def456\nline2"
    result = utils.filter_lines_by_pattern(text, r"^commit")
    assert "line1" in result
    assert "line2" in result
    assert "commit" not in result


def test_get_version():
    """Test getting version."""
    version = utils.get_version()
    assert isinstance(version, str)
    assert len(version) > 0


@patch("gitstats.utils.get_pipe_output")
def test_get_git_version(mock_pipe):
    """Test getting git version."""
    mock_pipe.return_value = "git version 2.39.0\n"
    version = utils.get_git_version()
    assert version == "git version 2.39.0"
    mock_pipe.assert_called_once_with(["git --version"])


@patch("gitstats.utils.get_pipe_output")
def test_get_gnuplot_version(mock_pipe):
    """Test getting gnuplot version."""
    mock_pipe.return_value = "gnuplot 5.4 patchlevel 0\n"
    version = utils.get_gnuplot_version()
    assert version == "gnuplot 5.4 patchlevel 0"


@patch("gitstats.utils.get_pipe_output")
def test_get_gnuplot_version_none(mock_pipe):
    """Test getting gnuplot version when it returns empty."""
    mock_pipe.return_value = ""
    version = utils.get_gnuplot_version()
    assert version is None


@patch("subprocess.Popen")
def test_get_pipe_output_simple(mock_popen):
    """Test get_pipe_output with single command."""
    mock_process = MagicMock()
    mock_process.communicate.return_value = (b"output\n", None)
    mock_process.wait.return_value = 0
    mock_popen.return_value = mock_process

    result = utils.get_pipe_output(["echo hello"], quiet=True)
    assert result == "output"


@patch("subprocess.Popen")
def test_get_pipe_output_wc_line_count(mock_popen):
    """Test get_pipe_output with wc -l."""
    mock_process = MagicMock()
    mock_process.communicate.return_value = (b"line1\nline2\nline3", None)
    mock_process.wait.return_value = 0
    mock_popen.return_value = mock_process

    result = utils.get_pipe_output(["git log", "wc -l"], quiet=True)
    assert result == "3"


@patch("subprocess.Popen")
def test_get_pipe_output_grep_v(mock_popen):
    """Test get_pipe_output with grep -v."""
    mock_process = MagicMock()
    mock_process.communicate.return_value = (b"commit abc\nline1\ncommit def", None)
    mock_process.wait.return_value = 0
    mock_popen.return_value = mock_process

    result = utils.get_pipe_output(["git log", "grep -v ^commit"], quiet=True)
    assert "line1" in result
    assert "commit" not in result


@patch("subprocess.Popen")
def test_get_pipe_output_unicode_decode_error(mock_popen):
    """Test get_pipe_output with binary data."""
    mock_process = MagicMock()
    # Create bytes that will fail utf-8 decoding
    bad_bytes = b"\x80\x81\x82"
    mock_process.communicate.return_value = (bad_bytes, None)
    mock_process.wait.return_value = 0
    mock_popen.return_value = mock_process

    # Should use latin-1 fallback
    result = utils.get_pipe_output(["cat binary"], quiet=True)
    assert isinstance(result, str)


def test_get_commit_range_default(reset_config):
    """Test get_commit_range with default values."""
    conf = gitstats.load_config()
    result = utils.get_commit_range()
    assert result == "HEAD"


def test_get_commit_range_with_end(reset_config):
    """Test get_commit_range with commit_end set."""
    with patch.dict("gitstats.utils.conf", {"commit_end": "main", "commit_begin": ""}):
        result = utils.get_commit_range("HEAD", end_only=True)
        assert result == "main"


def test_get_commit_range_with_begin_and_end(reset_config):
    """Test get_commit_range with both begin and end."""
    with patch.dict(
        "gitstats.utils.conf", {"commit_end": "HEAD", "commit_begin": "abc123"}
    ):
        result = utils.get_commit_range()
        assert result == "abc123..HEAD"


def test_get_commit_range_numeric_begin(reset_config):
    """Test get_commit_range with numeric commit_begin."""
    with patch.dict(
        "gitstats.utils.conf", {"commit_end": "main", "commit_begin": "10"}
    ):
        result = utils.get_commit_range()
        assert result == "main~10..main"


def test_get_commit_range_numeric_string_begin(reset_config):
    """Test get_commit_range with numeric string commit_begin."""
    with patch.dict(
        "gitstats.utils.conf", {"commit_end": "develop", "commit_begin": 5}
    ):
        result = utils.get_commit_range()
        assert result == "develop~5..develop"


def test_get_excluded_extensions_empty(reset_config):
    """Test getting excluded extensions when none set."""
    conf = gitstats.load_config()
    conf["exclude_exts"] = ""
    result = utils.get_excluded_extensions()
    assert result == set()


def test_get_excluded_extensions_single(reset_config):
    """Test getting single excluded extension."""
    with patch.dict("gitstats.utils.conf", {"exclude_exts": "md"}):
        result = utils.get_excluded_extensions()
        assert result == {"md"}


def test_get_excluded_extensions_multiple(reset_config):
    """Test getting multiple excluded extensions."""
    with patch.dict("gitstats.utils.conf", {"exclude_exts": "md, txt, log"}):
        result = utils.get_excluded_extensions()
        assert result == {"md", "txt", "log"}


def test_get_excluded_extensions_with_dots(reset_config):
    """Test getting excluded extensions with dots."""
    with patch.dict("gitstats.utils.conf", {"exclude_exts": ".md,.txt"}):
        result = utils.get_excluded_extensions()
        assert result == {".md", ".txt"}


def test_should_exclude_file_no_exclusions(reset_config):
    """Test should_exclude_file when no exclusions set."""
    conf = gitstats.load_config()
    conf["exclude_exts"] = ""
    assert utils.should_exclude_file("py") is False
    assert utils.should_exclude_file("md") is False


def test_should_exclude_file_with_exclusions(reset_config):
    """Test should_exclude_file with exclusions."""
    with patch.dict("gitstats.utils.conf", {"exclude_exts": "md,txt,log"}):
        assert utils.should_exclude_file("md") is True
        assert utils.should_exclude_file("txt") is True
        assert utils.should_exclude_file("py") is False


def test_should_exclude_file_case_insensitive(reset_config):
    """Test should_exclude_file is case insensitive."""
    with patch.dict("gitstats.utils.conf", {"exclude_exts": "MD,TXT"}):
        assert utils.should_exclude_file("md") is True
        assert utils.should_exclude_file("MD") is True
        assert utils.should_exclude_file("Md") is True


@patch("subprocess.check_output")
@patch("gitstats.utils.get_pipe_output")
def test_get_num_of_lines_in_blob_excluded(mock_pipe, mock_check):
    """Test get_num_of_lines_in_blob for excluded file."""
    with patch.dict("gitstats.utils.conf", {"exclude_exts": "md"}):
        result = utils.get_num_of_lines_in_blob(("md", "abc123"))
        assert result == ("md", "abc123", 0)
        mock_check.assert_not_called()


@patch("subprocess.check_output")
@patch("gitstats.utils.get_pipe_output")
def test_get_num_of_lines_in_blob_binary(mock_pipe, mock_check):
    """Test get_num_of_lines_in_blob for binary file."""
    gitstats._config = gitstats.DEFAULT_CONFIG.copy()
    gitstats._config["exclude_exts"] = ""

    # Return binary content with null byte
    mock_check.return_value = b"binary\x00content"

    result = utils.get_num_of_lines_in_blob(("exe", "abc123"))
    assert result == ("exe", "abc123", 0)


@patch("subprocess.check_output")
@patch("gitstats.utils.get_pipe_output")
def test_get_num_of_lines_in_blob_error(mock_pipe, mock_check):
    """Test get_num_of_lines_in_blob when git command fails."""
    gitstats._config = gitstats.DEFAULT_CONFIG.copy()
    gitstats._config["exclude_exts"] = ""

    mock_check.side_effect = subprocess.CalledProcessError(1, "git")

    result = utils.get_num_of_lines_in_blob(("py", "abc123"))
    assert result == ("py", "abc123", 0)


@patch("subprocess.check_output")
@patch("gitstats.utils.get_pipe_output")
def test_get_num_of_lines_in_blob_text(mock_pipe, mock_check):
    """Test get_num_of_lines_in_blob for text file."""
    gitstats._config = gitstats.DEFAULT_CONFIG.copy()
    gitstats._config["exclude_exts"] = ""

    # Return text content without null bytes
    mock_check.return_value = b"line1\nline2\nline3"
    mock_pipe.return_value = "3"

    result = utils.get_num_of_lines_in_blob(("py", "abc123"))
    assert result == ("py", "abc123", 3)


@patch("gitstats.utils.get_pipe_output")
def test_get_num_of_files_from_rev(mock_pipe):
    """Test get_num_of_files_from_rev."""
    mock_pipe.return_value = "42\n"

    result = utils.get_num_of_files_from_rev((1234567890, "abc123"))
    assert result == (1234567890, "abc123", 42)


def test_get_stat_summary_counts_full():
    """Test get_stat_summary_counts with all values."""
    line = "5 files changed, 100 insertions(+), 50 deletions(-)"
    result = utils.get_stat_summary_counts(line)
    assert result == ["5", "100", "50"]


def test_get_stat_summary_counts_no_changes():
    """Test get_stat_summary_counts with no changes."""
    line = "0 files changed"
    result = utils.get_stat_summary_counts(line)
    assert len(result) == 3
    assert result[0] == "0"


def test_get_stat_summary_counts_only_insertions():
    """Test get_stat_summary_counts with only insertions."""
    line = "3 files changed, 25 insertions(+)"
    result = utils.get_stat_summary_counts(line)
    assert len(result) == 3
    assert result[1] == "25"
    assert result[2] == 0


def test_get_stat_summary_counts_only_deletions():
    """Test get_stat_summary_counts with only deletions."""
    line = "2 files changed, 15 deletions(-)"
    result = utils.get_stat_summary_counts(line)
    assert len(result) == 3
    assert result[1] == 0
    assert result[2] == "15"


def test_get_log_range_default(reset_config):
    """Test get_log_range with default values."""
    conf = gitstats.load_config()
    conf["start_date"] = ""
    result = utils.get_log_range()
    assert result == "HEAD"


def test_get_log_range_with_start_date(reset_config):
    """Test get_log_range with start_date."""
    with patch.dict(
        "gitstats.utils.conf", {"start_date": "2024-01-01", "commit_end": "main"}
    ):
        result = utils.get_log_range("HEAD", end_only=True)
        assert '--since="2024-01-01"' in result
        assert '"main"' in result


def test_get_log_range_end_only_false(reset_config):
    """Test get_log_range with end_only=False."""
    with patch.dict(
        "gitstats.utils.conf",
        {"start_date": "", "commit_end": "main", "commit_begin": "dev"},
    ):
        result = utils.get_log_range("HEAD", end_only=False)
        assert "dev..main" in result


def test_gnuplot_cmd_default():
    """Test gnuplot command defaults to gnuplot."""
    assert utils.gnuplot_cmd == os.environ.get("GNUPLOT", "gnuplot")


@patch.dict(os.environ, {"GNUPLOT": "/custom/gnuplot"})
def test_gnuplot_cmd_custom():
    """Test gnuplot command can be overridden."""
    import importlib

    importlib.reload(utils)
    assert utils.gnuplot_cmd == "/custom/gnuplot"


def test_count_lines_edge_cases():
    """Test count_lines_in_text with edge cases."""
    # Test with only newlines
    assert utils.count_lines_in_text("\n\n\n") == 0
    # Test with mixed content
    assert utils.count_lines_in_text("a\nb\nc") == 3


def test_filter_lines_none_input():
    """Test filter_lines_by_pattern with None."""
    result = utils.filter_lines_by_pattern(None, "pattern")
    assert result == ""


@patch("gitstats.ON_LINUX", True)
@patch("sys.stdout")
@patch("subprocess.Popen")
def test_get_pipe_output_quiet_tty_linux(mock_popen, mock_stdout):
    """Test get_pipe_output with quiet=False on Linux with tty."""
    mock_stdout.isatty.return_value = True
    mock_process = MagicMock()
    mock_process.communicate.return_value = (b"output\n", None)
    mock_process.wait.return_value = 0
    mock_process.stdout = MagicMock()
    mock_popen.return_value = mock_process

    with patch("os.isatty", return_value=True):
        result = utils.get_pipe_output(["git log"], quiet=False)
        assert result == "output"


@patch("subprocess.Popen")
def test_get_pipe_output_wc_unicode_decode_error(mock_popen):
    """Test get_pipe_output wc -l handles binary data."""
    mock_process = MagicMock()
    # Return binary data
    mock_process.communicate.return_value = (b"\xff\xfe\x00\x01line1\nline2\n", None)
    mock_process.wait.return_value = 0
    mock_process.stdout = MagicMock()
    mock_popen.return_value = mock_process

    result = utils.get_pipe_output(["git show", "wc -l"], quiet=True)
    # Should handle binary data and count lines
    assert isinstance(result, str)


@patch("subprocess.Popen")
def test_get_pipe_output_grep_v_unicode_decode_error(mock_popen):
    """Test get_pipe_output grep -v with UnicodeDecodeError fallback."""
    mock_process = MagicMock()
    # Return binary data that will trigger UnicodeDecodeError
    mock_process.communicate.return_value = (
        b"\xff\xfeline1\ncommit abc\nline2\n",
        None,
    )
    mock_process.wait.return_value = 0
    mock_process.stdout = MagicMock()
    mock_popen.return_value = mock_process

    result = utils.get_pipe_output(["git log", "grep -v ^commit"], quiet=True)
    # Should fallback to latin-1 and filter
    assert isinstance(result, str)


@patch("subprocess.Popen")
def test_get_pipe_output_multi_command_pipe(mock_popen):
    """Test get_pipe_output with multiple piped commands."""
    mock_process1 = MagicMock()
    mock_process1.stdout = MagicMock()
    mock_process1.wait.return_value = 0

    mock_process2 = MagicMock()
    mock_process2.stdout = MagicMock()
    mock_process2.wait.return_value = 0

    mock_process3 = MagicMock()
    mock_process3.communicate.return_value = (b"final output\n", None)
    mock_process3.wait.return_value = 0

    mock_popen.side_effect = [mock_process1, mock_process2, mock_process3]

    result = utils.get_pipe_output(["git log", "grep author", "wc -l"], quiet=True)
    assert result == "final output"
    assert mock_popen.call_count == 3


@patch("subprocess.Popen")
def test_get_pipe_output_normal_pipe_unicode_decode_error(mock_popen):
    """Test get_pipe_output with UnicodeDecodeError in normal pipe."""
    mock_process = MagicMock()
    # Return binary data that will cause UnicodeDecodeError
    mock_process.communicate.return_value = (b"\xff\xfe\x00\x01binary data\n", None)
    mock_process.wait.return_value = 0
    mock_process.stdout = MagicMock()
    mock_popen.return_value = mock_process

    result = utils.get_pipe_output(["git show HEAD:file.bin"], quiet=True)
    # Should fallback to latin-1
    assert isinstance(result, str)


@patch("gitstats.ON_LINUX", True)
@patch("os.isatty", return_value=True)
@patch("subprocess.Popen")
def test_get_pipe_output_not_quiet_tty_print(mock_popen, mock_isatty):
    """Test get_pipe_output with quiet=False shows progress on tty."""
    mock_process = MagicMock()
    mock_process.communicate.return_value = (b"output\n", None)
    mock_process.wait.return_value = 0
    mock_process.stdout = MagicMock()
    mock_popen.return_value = mock_process

    with patch("builtins.print") as mock_print:
        result = utils.get_pipe_output(["git log"], quiet=False)
        assert result == "output"
        # Should have printed progress indicator
        assert mock_print.called


def test_get_log_range_no_start_date(reset_config):
    """Test get_log_range without start_date."""
    with patch.dict(
        "gitstats.utils.conf",
        {"commit_end": "main", "start_date": "", "commit_begin": ""},
    ):
        result = utils.get_log_range()
        assert result == "main"
        assert "--since" not in result


def test_get_log_range_with_start_date(reset_config):
    """Test get_log_range with start_date."""
    with patch.dict(
        "gitstats.utils.conf",
        {"commit_end": "main", "start_date": "2024-01-01", "commit_begin": ""},
    ):
        result = utils.get_log_range()
        assert '--since="2024-01-01" "main"' == result
