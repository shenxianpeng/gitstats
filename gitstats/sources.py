"""What kind of file a path of a repository is, for counting lines and for
the analyses of its code.

A history's line counts include what nobody wrote by hand: a vendored copy of
a dependency committed and later removed, test fixtures written out by a
tool and rewritten with every change, lock files. In CoreDNS 97% of the lines
ever added are under vendor/; in Tailwind CSS most are generated CSS under
fixtures/. Counted with them, "how much of what was written is still there"
says more about a project's dependencies than about its code.

Some files are text without being code either: a logo saved from
Illustrator is PostScript, a test certificate is base64. requests' logo,
ext/requests-logo.ai, is 8,722 lines, more than any of its Python files.

One test, is_source(), decides for the files of the history and for those of
the last commit, so that both sides of a ratio count the same files. A
second, is_code(), picks out of those the files whose history says something
about the code: the hotspots and the ownership of the files leave out the
documentation, which a project changes often and on purpose.
"""

from __future__ import annotations

import fnmatch

# A path with one of these folders anywhere in it is left out.
EXCLUDED_FOLDERS: tuple[str, ...] = (
    "vendor",
    "third_party",
    "third-party",
    "thirdparty",  # codespell:ignore
    "Godeps",
    "node_modules",
    "bower_components",
    "fixtures",
    "testdata",
    "__snapshots__",
)

# A file whose name matches one of these is left out.
EXCLUDED_NAMES: tuple[str, ...] = (
    "*.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "go.sum",
    "*.min.js",
    "*.min.css",
    "*.map",
    "*.snap",
    "*.pb.go",
    "*_pb2.py",
    "*_pb2_grpc.py",
)

# What is not code: vector artwork and documents (PostScript and PDF are
# text with binary parts), keys and certificates, tabular data and logs,
# whose lines are not lines of code; and images, fonts, media and archives,
# which count no lines, and whose history is no code's.
ASSET_EXTENSIONS: frozenset[str] = frozenset(
    {
        # images, fonts, media and archives
        "png",
        "jpg",
        "jpeg",
        "gif",
        "bmp",
        "ico",
        "icns",
        "webp",
        "avif",
        "tif",
        "tiff",
        "psd",
        "ttf",
        "otf",
        "woff",
        "woff2",
        "eot",
        "mp3",
        "mp4",
        "wav",
        "ogg",
        "webm",
        "mov",
        "zip",
        "gz",
        "tgz",
        "bz2",
        "xz",
        "7z",
        "jar",
        "whl",
        # artwork and documents
        "ai",
        "eps",
        "ps",
        "pdf",
        "svg",
        # keys and certificates
        "pem",
        "key",
        "crt",
        "cer",
        "csr",
        "der",
        "srl",
        "p12",
        "pfx",
        "jks",
        "keystore",
        "gpg",
        "asc",
        # data
        "csv",
        "tsv",
        "log",
    }
)

# The documentation: by extension, by name (README, LICENSE, AUTHORS; see
# _is_doc_name()), and anything in a folder of these names. Not .txt: that is
# requirements.txt and CMakeLists.txt as often as notes.
DOC_EXTENSIONS: frozenset[str] = frozenset(
    {"md", "markdown", "mdx", "rst", "adoc", "asciidoc", "rdoc", "textile", "org"}
)
DOC_NAMES: frozenset[str] = frozenset(
    {
        "readme",
        "changelog",
        "changes",
        "history",
        "news",
        "authors",
        "contributors",
        "maintainers",
        "license",
        "licence",
        "copying",
        "notice",
        "contributing",
        "code_of_conduct",
        "security",
    }
)
DOC_FOLDERS: frozenset[str] = frozenset({"doc", "docs", "documentation"})

# The tests: anything in a folder of these names, or named like a test.
TEST_FOLDERS: frozenset[str] = frozenset(
    {"test", "tests", "__tests__", "spec", "specs", "testing", "e2e"}
)
TEST_NAMES: tuple[str, ...] = (
    "test_*",
    "*_test.*",
    "*.test.*",
    "*.spec.*",
    "*_spec.rb",
    "*Test.java",
    "*Tests.java",
    "*Test.kt",
    "*Tests.kt",
    "*Tests.cs",
    "*Tests.swift",
)

# What file_kind() says of a path
SOURCE = "source"
TEST = "test"
DOCS = "docs"
ASSET = "asset"
VENDORED = "vendored"
GENERATED = "generated"

# The folders of EXCLUDED_FOLDERS that hold someone else's code; the others
# hold what a tool wrote
_VENDOR_FOLDERS = frozenset(EXCLUDED_FOLDERS) - {"fixtures", "testdata", "__snapshots__"}


def _extension(name: str) -> str:
    """The extension of a file name, lowercased: "" for "Makefile" and ".gitignore"."""
    stem, dot, extension = name.rpartition(".")
    return extension.lower() if dot and stem else ""


def _is_doc_name(name: str, extension: str) -> bool:
    """Whether a file is named like a project's documentation: LICENSE,
    AUTHORS, LICENSE-MIT, license.txt, NOTICE.APACHE. A module named
    history.py or security.go is code."""
    base = name.partition(".")[0]
    if base.lower().partition("-")[0] not in DOC_NAMES:
        return False
    return extension in ("", "txt") or base.isupper()


def file_kind(path: str) -> str:
    """What a path (relative, with "/") is: VENDORED, GENERATED, ASSET, DOCS,
    TEST or SOURCE, the first that fits in that order."""
    parts = path.split("/")
    folders, name = parts[:-1], parts[-1]
    if any(part in _VENDOR_FOLDERS for part in folders):
        return VENDORED
    if any(part in EXCLUDED_FOLDERS for part in folders) or any(
        fnmatch.fnmatchcase(name, pattern) for pattern in EXCLUDED_NAMES
    ):
        return GENERATED
    extension = _extension(name)
    if extension in ASSET_EXTENSIONS:
        return ASSET
    lowered = [folder.lower() for folder in folders]
    if (
        extension in DOC_EXTENSIONS
        or _is_doc_name(name, extension)
        or any(folder in DOC_FOLDERS for folder in lowered)
    ):
        return DOCS
    if any(folder in TEST_FOLDERS for folder in lowered) or any(
        fnmatch.fnmatchcase(name, pattern) for pattern in TEST_NAMES
    ):
        return TEST
    return SOURCE


def is_source(path: str) -> bool:
    """Whether a path counts as the project's own: its lines are the lines
    of code. Vendored, generated and asset files are not."""
    return file_kind(path) in (SOURCE, TEST, DOCS)


def is_code(path: str) -> bool:
    """Whether a path is code the project maintains, its tests included:
    the files whose changes the hotspots and the ownership of the files
    look at."""
    return file_kind(path) in (SOURCE, TEST)
