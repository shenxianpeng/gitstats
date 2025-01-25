from gitstats.utils import (
    get_version,
    get_git_version,
    get_gnuplot_version,
    get_pipe_output,
)


def test_get_version():
    assert get_version() > "0.4.3"
    assert get_version() < "0.6.0"


def test_get_git_version():
    assert get_git_version().startswith("git version")


def test_get_gnuplot_version():
    assert get_gnuplot_version().startswith("gnuplot")


def test_get_pipe_output():
    assert get_pipe_output(["git --version"]).startswith("git version")


def test_get_commit_range():
    pass
