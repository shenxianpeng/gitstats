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
