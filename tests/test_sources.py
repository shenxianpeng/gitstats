"""Tests for telling a project's own source from what it vendors or generates."""

import subprocess

import pytest

from gitstats.sources import EXCLUDED_FOLDERS, EXCLUDED_NAMES, is_source, pathspecs


@pytest.mark.parametrize(
    ("path", "source"),
    [
        ("src/main.go", True),
        ("README.md", True),
        ("vendor/github.com/x/y.go", False),
        ("src/vendor/lib.c", False),
        ("tests/fixtures/output.css", False),
        ("pkg/testdata/case.json", False),
        ("ui/__snapshots__/a.snap", False),
        ("web/node_modules/react/index.js", False),
        ("third_party/zlib/zlib.h", False),
        ("Cargo.lock", False),
        ("app/package-lock.json", False),
        ("go.sum", False),
        ("static/app.min.js", False),
        ("api/service.pb.go", False),
        ("proto/service_pb2.py", False),
        # a file named like a folder is still source
        ("docs/vendor", True),
        ("vendoring.md", True),
        ("lockfile.py", True),
    ],
)
def test_is_source(path, source):
    assert is_source(path) is source


def test_pathspecs():
    specs = pathspecs()
    assert specs[0] == "."
    assert ":(exclude,glob)**/vendor/**" in specs
    assert ":(exclude,glob)**/*.lock" in specs
    assert len(specs) == 1 + len(EXCLUDED_FOLDERS) + len(EXCLUDED_NAMES)


def test_pathspecs_and_is_source_agree(tmp_path):
    """git leaves out the files is_source() does, at any depth."""
    paths = [
        "src/a.py", "vendor/b.go", "src/vendor/c.go", "x/fixtures/d.css",
        "Cargo.lock", "web/e.min.js", "docs/vendor", "f.snap",
    ]  # fmt: skip
    for path in paths:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    listed = subprocess.run(
        ["git", "ls-files", "--", *pathspecs()],
        cwd=tmp_path, check=True, capture_output=True, text=True,
    ).stdout.split()  # fmt: skip
    assert sorted(listed) == sorted(path for path in paths if is_source(path))
