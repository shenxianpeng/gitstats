"""Which files of a repository are its own source, for counting lines.

A history's line counts include what nobody wrote by hand: a vendored copy of
a dependency committed and later removed, test fixtures written out by a
tool and rewritten with every change, lock files. In CoreDNS 97% of the lines
ever added are under vendor/; in Tailwind CSS most are generated CSS under
fixtures/. Counted with them, "how much of what was written is still there"
says more about a project's dependencies than about its code.

The same rules give git a pathspec for the history and Python a test for the
files of the last commit, so that both sides of a ratio count the same files.
"""

from __future__ import annotations

import fnmatch

# A path with one of these folders anywhere in it is left out.
EXCLUDED_FOLDERS: tuple[str, ...] = (
    "vendor",
    "third_party",
    "third-party",
    "thirdparty",
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


def pathspecs() -> list[str]:
    """The pathspecs that leave these files out of a `git log`, after ``--``."""
    specs = ["."]
    specs += [f":(exclude,glob)**/{folder}/**" for folder in EXCLUDED_FOLDERS]
    specs += [f":(exclude,glob)**/{name}" for name in EXCLUDED_NAMES]
    return specs


def is_source(path: str) -> bool:
    """Whether a path (relative, with "/") counts as the project's own source."""
    parts = path.split("/")
    if any(part in EXCLUDED_FOLDERS for part in parts[:-1]):
        return False
    return not any(fnmatch.fnmatchcase(parts[-1], name) for name in EXCLUDED_NAMES)
