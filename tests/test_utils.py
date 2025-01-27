import pytest
from gitstats.utils import (
    get_version,
    get_git_version,
    get_gnuplot_version,
    get_pipe_output,
    get_commit_range,
    get_num_of_lines_in_blob,
    get_num_of_files_from_rev,
    get_stat_summary_counts,
)


def test_get_version(mocker):
    mock_get_version = mocker.patch("gitstats.utils.version", return_value="0.1.0")
    assert get_version() == "0.1.0"
    mock_get_version.assert_called_once()


def test_get_git_version(mocker):
    mock_get_git_version = mocker.patch(
        "gitstats.utils.get_pipe_output", return_value="git version 2.0.0"
    )
    assert get_git_version() == "git version 2.0.0"
    mock_get_git_version.assert_called_once()


def test_get_gnuplot_version(mocker):
    mock_get_gnuplot_version = mocker.patch(
        "gitstats.utils.get_pipe_output", return_value="gnuplot 5.0.0"
    )
    assert get_gnuplot_version() == "gnuplot 5.0.0"
    mock_get_gnuplot_version.assert_called_once()


def test_get_gnuplot_not_installed(mocker):
    mock_get_gnuplot_version = mocker.patch(
        "gitstats.utils.get_pipe_output", return_value="Command 'gnuplot' not found"
    )
    assert "not found" in get_gnuplot_version()
    mock_get_gnuplot_version.assert_called_once()


def test_get_pipe_output(mocker):
    mock_get_pipe_output = mocker.patch(
        "subprocess.Popen.communicate", return_value=(b"git version 2.0.0", b"")
    )
    assert "git version" in get_pipe_output(["git --version"])
    mock_get_pipe_output.assert_called_once()


def test_get_commit_range(mocker):
    mocker.patch("gitstats.utils.get_commit_range", return_value="HEAD")
    assert get_commit_range() == "HEAD"
    assert get_commit_range(end_only=True) == "HEAD"
    assert get_commit_range(end_only=False) == "HEAD"


@pytest.mark.skip("Test not implemented")
def test_get_num_of_lines_in_blob(mocker):
    mock_get_num_of_lines_in_blob = mocker.patch(
        "gitstats.utils.get_pipe_output", return_value="2"
    )
    assert get_num_of_lines_in_blob("ext", "blob_id") == ("ext", "blob_id", 2)
    mock_get_num_of_lines_in_blob.assert_called_once()


@pytest.mark.skip("Test not implemented")
def test_get_num_of_files_from_rev(mocker):
    mock_get_num_of_files_from_rev = mocker.patch(
        "gitstats.utils.get_num_of_files_from_rev", return_value="2"
    )
    assert get_num_of_files_from_rev("time", "rev") == ("time", "rev", 2)
    mock_get_num_of_files_from_rev.assert_called_once()


def test_get_stat_summary_counts(mocker):
    mocker.patch("gitstats.utils.get_stat_summary_counts", return_value=["2", "0", "0"])
    assert get_stat_summary_counts("2 0 0") == ["2", "0", "0"]
