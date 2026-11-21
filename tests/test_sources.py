"""Tests for telling a project's own source from what it vendors or generates."""

import pytest

from gitstats.sources import file_kind, is_code, is_source


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


@pytest.mark.parametrize(
    ("path", "kind"),
    [
        ("src/requests/models.py", "source"),
        ("Makefile", "source"),
        (".github/workflows/ci.yml", "source"),
        ("requirements.txt", "source"),
        ("CMakeLists.txt", "source"),
        # a module named like a document is code
        ("src/history.py", "source"),
        ("pkg/security.go", "source"),
        ("tests/test_requests.py", "test"),
        ("test_utils.py", "test"),
        ("pkg/server_test.go", "test"),
        ("web/app.spec.ts", "test"),
        ("ui/Button.test.tsx", "test"),
        ("spec/models/user_spec.rb", "test"),
        ("app/src/test/java/AppTest.java", "test"),
        ("README.md", "docs"),
        ("HISTORY.md", "docs"),
        ("docs/conf.py", "docs"),
        ("Documentation/howto.html", "docs"),
        ("LICENSE", "docs"),
        ("LICENSE-MIT", "docs"),
        ("NOTICE.APACHE", "docs"),
        ("license.txt", "docs"),
        ("AUTHORS", "docs"),
        ("notes.txt", "source"),
        ("ext/requests-logo.ai", "asset"),
        ("tests/certs/server.pem", "asset"),
        ("assets/icon.svg", "asset"),
        ("data/cities.csv", "asset"),
        ("ext/logo.PNG", "asset"),
        ("vendor/github.com/x/y.go", "vendored"),
        ("web/node_modules/react/index.js", "vendored"),
        ("tests/fixtures/output.css", "generated"),
        ("Cargo.lock", "generated"),
        ("static/app.min.js", "generated"),
        # a file named like a folder is no folder
        ("docs/vendor", "docs"),
        (".gitignore", "source"),
    ],
)
def test_file_kind(path, kind):
    assert file_kind(path) == kind


def test_the_code_is_the_source_and_its_tests():
    assert is_code("src/app.py")
    assert is_code("tests/test_app.py")
    assert not is_code("README.md")
    assert not is_code("ext/logo.ai")
    assert not is_code("vendor/x/y.go")
    # the documentation is the project's own, and its lines are lines of code
    assert is_source("README.md")
    assert not is_source("ext/logo.ai")
