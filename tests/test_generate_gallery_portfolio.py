"""Tests for scripts/generate_gallery_portfolio.py.

The script lives outside the ``gitstats`` package (it is not installed, only
run directly from a checkout), so it is loaded here by file path.
"""

import importlib.util
import json
import os
import sys

import pytest

_SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts",
    "generate_gallery_portfolio.py",
)


@pytest.fixture
def gallery_script():
    spec = importlib.util.spec_from_file_location("generate_gallery_portfolio", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield module
    del sys.modules[spec.name]


def test_load_gallery_summaries_basic(temp_dir, gallery_script):
    repo_dir = os.path.join(temp_dir, "repo")
    os.makedirs(repo_dir)
    with open(os.path.join(repo_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"name": "repo"}, f)

    summaries = gallery_script.load_gallery_summaries(temp_dir)

    assert len(summaries) == 1
    assert summaries[0]["name"] == "repo"
    assert summaries[0]["report_path"] == "repo/index.html"


def test_load_gallery_summaries_skips_dir_without_summary(temp_dir, gallery_script):
    os.makedirs(os.path.join(temp_dir, "empty"))
    assert gallery_script.load_gallery_summaries(temp_dir) == []


def test_load_gallery_summaries_skips_corrupt_json(temp_dir, gallery_script):
    good_dir = os.path.join(temp_dir, "good")
    os.makedirs(good_dir)
    with open(os.path.join(good_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"name": "good"}, f)

    bad_dir = os.path.join(temp_dir, "bad")
    os.makedirs(bad_dir)
    with open(os.path.join(bad_dir, "summary.json"), "w", encoding="utf-8") as f:
        f.write("{not valid json")

    # A corrupt summary.json must be skipped, not abort the whole scan.
    summaries = gallery_script.load_gallery_summaries(temp_dir)
    assert [s["name"] for s in summaries] == ["good"]


def test_load_gallery_summaries_skips_entry_commonpath_cannot_compare(
    temp_dir, gallery_script, monkeypatch
):
    # A symlinked entry whose realpath lands somewhere commonpath() cannot
    # compare to base (e.g. a different drive on Windows) must be skipped,
    # not crash the whole scan: os.path.commonpath() raises ValueError for
    # that case, which the original code did not catch.
    good_dir = os.path.join(temp_dir, "good")
    os.makedirs(good_dir)
    with open(os.path.join(good_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"name": "good"}, f)
    os.makedirs(os.path.join(temp_dir, "outside_link"))

    real_realpath = os.path.realpath

    def fake_realpath(path):
        if "outside_link" in path and path.endswith("summary.json"):
            return r"D:\outside\summary.json"
        return real_realpath(path)

    monkeypatch.setattr(gallery_script.os.path, "realpath", fake_realpath)

    summaries = gallery_script.load_gallery_summaries(temp_dir)
    assert [s["name"] for s in summaries] == ["good"]


def _write_summary(root, entry, **summary):
    os.makedirs(os.path.join(root, entry))
    with open(os.path.join(root, entry, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f)


def test_load_gallery_summaries_names_unnamed_entries(temp_dir, gallery_script):
    _write_summary(temp_dir, "linux", total_commits=5)

    (summary,) = gallery_script.load_gallery_summaries(temp_dir)

    assert summary["name"] == "linux"
    assert summary["report_path"] == "linux/index.html"


def test_main_prints_usage_without_one_argument(gallery_script, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["generate_gallery_portfolio.py"])
    assert gallery_script.main() == 2
    assert "Usage:" in capsys.readouterr().err


def test_main_rejects_a_missing_directory(gallery_script, temp_dir, monkeypatch, capsys):
    missing = os.path.join(temp_dir, "missing")
    monkeypatch.setattr(sys, "argv", ["generate_gallery_portfolio.py", missing])
    assert gallery_script.main() == 1
    assert f"Not a directory: {missing}" in capsys.readouterr().err


def test_main_needs_at_least_one_summary(gallery_script, temp_dir, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["generate_gallery_portfolio.py", temp_dir])
    assert gallery_script.main() == 1
    assert "No summary.json found" in capsys.readouterr().err


def test_main_writes_the_portfolio_page(gallery_script, temp_dir, monkeypatch, capsys):
    _write_summary(temp_dir, "cpython", name="CPython", total_commits=120)
    _write_summary(temp_dir, "git", name="Git", total_commits=80)
    monkeypatch.setattr(sys, "argv", ["generate_gallery_portfolio.py", temp_dir])

    assert gallery_script.main() == 0

    with open(os.path.join(temp_dir, "index.html"), encoding="utf-8") as f:
        page = f.read()
    assert "GitStats Gallery" in page
    assert 'href="cpython/index.html"' in page
    assert 'href="git/index.html"' in page
    assert "Portfolio page written for 2 repositories" in capsys.readouterr().out
