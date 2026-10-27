"""Tests for telling a project's own source from what it vendors or generates."""

import pytest

from gitstats.sources import is_source


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
