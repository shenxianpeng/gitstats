#!/usr/bin/env python3
"""Read the gallery's list of repositories, gallery/repos.yml.

The list says which repositories the gallery makes a report for and which
ecosystem each belongs to. The workflow builds its matrix from it, and the
portfolio page groups the reports by it.

Usage:
    python scripts/gallery_repos.py matrix gallery/repos.yml   # JSON, for a job matrix
    python scripts/gallery_repos.py ids gallery/repos.yml      # one id per line
"""

import json
import os
import re
import sys
from dataclasses import dataclass

# a report's folder, and the end of its address: never more than this
_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
_URL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9_.-]+")
# folders of the gallery's own: a report there would mix with them, and the
# deploy, which removes a report folder without a summary.json, would remove them
RESERVED_IDS = frozenset({"ai", "orgs", "ecosystems"})
DEFAULT_TIMEOUT = 90
# GitHub Actions: a matrix has at most 256 jobs, and a job runs at most 6 hours
MAX_REPOS = 256
MAX_TIMEOUT = 360


@dataclass(frozen=True)
class Group:
    id: str
    name: str
    # how a page title names its projects: "Python open source projects"
    title: str = ""


@dataclass(frozen=True)
class Repo:
    id: str
    name: str
    url: str
    group: str
    timeout: int = DEFAULT_TIMEOUT


class RepoListError(ValueError):
    """The list of repositories is not one the gallery can make."""


def parse_repos(data: object) -> tuple[list[Group], list[Repo]]:
    """The groups and repositories of a parsed repos.yml, in their order.

    Raises RepoListError for anything the workflow could not run or the
    pages could not name: a missing field, an id that is not a plain folder
    name or is one of the gallery's own folders, an id used twice, a URL that
    is not owner/name.
    """
    if not isinstance(data, dict) or not isinstance(data.get("groups"), list):
        raise RepoListError("expected a mapping with a list of groups")
    groups: list[Group] = []
    repos: list[Repo] = []
    for entry in data["groups"]:
        group, members = _parse_group(entry, {g.id for g in groups})
        groups.append(group)
        seen = {repo.id for repo in repos}
        for member in members:
            repo = _parse_repo(member, group.id)
            if repo.id in seen:
                raise RepoListError(f"repository id used twice: {repo.id!r}")
            seen.add(repo.id)
            repos.append(repo)
    if not repos:
        raise RepoListError("no repositories")
    if len(repos) > MAX_REPOS:
        raise RepoListError(f"{len(repos)} repositories: a job matrix takes at most {MAX_REPOS}")
    return groups, repos


def _parse_group(group: object, taken: set[str]) -> tuple[Group, list]:
    """One group, and the entries of its repositories."""
    if not isinstance(group, dict):
        raise RepoListError(f"not a group: {group!r}")
    group_id, group_name = _text(group, "id", "group"), _text(group, "name", "group")
    if not _ID.fullmatch(group_id) or group_id in taken:
        raise RepoListError(f"bad or repeated group id: {group_id!r}")
    title = group.get("title", f"{group_name} projects")
    if not isinstance(title, str) or not title.strip():
        raise RepoListError(f"group {group_id!r}: title must be text")
    entries = group.get("repos")
    if not isinstance(entries, list) or not entries:
        raise RepoListError(f"group {group_id!r} has no repos")
    return Group(group_id, group_name, title.strip()), entries


def _parse_repo(entry: object, group_id: str) -> Repo:
    """One repository of a group."""
    if not isinstance(entry, dict):
        raise RepoListError(f"not a repository: {entry!r}")
    repo_id = _text(entry, "id", "repository")
    if not _ID.fullmatch(repo_id):
        raise RepoListError(f"bad repository id: {repo_id!r}")
    if repo_id in RESERVED_IDS:
        raise RepoListError(f"repository id {repo_id!r} is a folder of the gallery's own")
    url = _text(entry, "url", repo_id)
    if not _URL.fullmatch(url) or ".." in url:
        raise RepoListError(f"{repo_id}: url must be owner/name on GitHub, not {url!r}")
    timeout = entry.get("timeout", DEFAULT_TIMEOUT)
    if not isinstance(timeout, int) or isinstance(timeout, bool):
        raise RepoListError(f"{repo_id}: timeout must be a number of minutes")
    if not 1 <= timeout <= MAX_TIMEOUT:
        raise RepoListError(f"{repo_id}: timeout must be 1 to {MAX_TIMEOUT} minutes")
    return Repo(repo_id, _text(entry, "name", repo_id), url, group_id, timeout)


def _text(mapping: dict, key: str, where: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RepoListError(f"{where}: {key} is missing")
    return value.strip()


def _list_file(path: str) -> str:
    """The file ``path`` names, as found in its directory: a .yml or .yaml
    file under the current directory (the checkout, in the workflow).

    The file opened is the directory's own entry, never the path as given."""
    base = os.path.realpath(os.getcwd())
    wanted = os.path.realpath(path)
    try:
        inside = os.path.commonpath([base, wanted]) == base
    except ValueError:
        inside = False
    folder, name = os.path.split(wanted)
    if inside and os.path.isdir(folder):
        with os.scandir(folder) as entries:
            for entry in entries:
                if (
                    entry.name == name
                    and entry.name.endswith((".yml", ".yaml"))
                    and entry.is_file()
                ):
                    return entry.path
    raise RepoListError("not a .yml file under the current directory")


def load_repos(path: str) -> tuple[list[Group], list[Repo]]:
    """Read and check repos.yml, only read."""
    list_file = _list_file(path)
    import yaml  # only the gallery needs it, not gitstats

    with open(list_file, encoding="utf-8") as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as error:
            raise RepoListError(f"not YAML: {error}") from error
    return parse_repos(data)


def matrix(repos: list[Repo]) -> list[dict]:
    """The job matrix of the workflow: one entry for each repository."""
    return [
        {"id": r.id, "name": r.name, "url": r.url, "group": r.group, "timeout": r.timeout}
        for r in repos
    ]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2 or args[0] not in ("matrix", "ids"):
        print(__doc__, file=sys.stderr)
        return 2
    try:
        _, repos = load_repos(args[1])
    except (OSError, RepoListError) as error:
        print(f"{args[1]}: {error}", file=sys.stderr)
        return 1
    if args[0] == "matrix":
        print(json.dumps(matrix(repos), separators=(",", ":")))
    else:
        print("\n".join(repo.id for repo in repos))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
