"""Tests for scripts/gallery_repos.py and the list it reads, gallery/repos.yml.

The script lives outside the ``gitstats`` package (it is not installed, only
run directly from a checkout), so it is loaded here by file path.
"""

import importlib.util
import json
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT_PATH = os.path.join(_ROOT, "scripts", "gallery_repos.py")
_REPOS_YML = os.path.join(_ROOT, "gallery", "repos.yml")


@pytest.fixture
def repos_script():
    spec = importlib.util.spec_from_file_location("gallery_repos_under_test", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield module
    del sys.modules[spec.name]


def _list(*repos, group="python"):
    return {"groups": [{"id": group, "name": "Python", "repos": list(repos)}]}


def _repo(repo_id="flask", **fields):
    return {"id": repo_id, "name": "Flask", "url": "pallets/flask", **fields}


def test_parse_repos(repos_script):
    data = {
        "groups": [
            {"id": "python", "name": "Python", "repos": [_repo(), _repo("pip", url="pypa/pip")]},
            {
                "id": "cncf",
                "name": "CNCF",
                "repos": [_repo("etcd", url="etcd-io/etcd", timeout=30)],
            },
        ]
    }
    groups, repos = repos_script.parse_repos(data)
    assert [(g.id, g.name) for g in groups] == [("python", "Python"), ("cncf", "CNCF")]
    assert [(r.id, r.group, r.timeout) for r in repos] == [
        ("flask", "python", 90),
        ("pip", "python", 90),
        ("etcd", "cncf", 30),
    ]


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ([], "mapping"),
        ({"groups": "python"}, "mapping"),
        ({"groups": ["python"]}, "not a group"),
        ({"groups": [{"id": "python", "name": "Python"}]}, "no repos"),
        (_list(_repo(), group="Py thon"), "group id"),
        ({"groups": [{"id": "a", "name": "A", "repos": [_repo()]}] * 2}, "group id"),
        (_list("flask"), "not a repository"),
        (_list(_repo("../escape")), "bad repository id"),
        (_list(_repo("Flask")), "bad repository id"),
        (_list(_repo(), _repo()), "used twice"),
        (_list(_repo(url="https://github.com/pallets/flask")), "owner/name"),
        (_list(_repo(url="pallets/../flask")), "owner/name"),
        (_list(_repo(url="")), "url is missing"),
        (_list(_repo(name=" ")), "name is missing"),
        (_list(_repo(timeout="90")), "number of minutes"),
        (_list(_repo(timeout=True)), "number of minutes"),
        (_list(_repo(timeout=361)), "1 to 360"),
        ({"groups": []}, "no repositories"),
    ],
)
def test_parse_repos_rejects(repos_script, data, message):
    with pytest.raises(repos_script.RepoListError, match=message):
        repos_script.parse_repos(data)


def test_parse_repos_at_most_a_matrix(repos_script):
    repos = [_repo(f"r{i}") for i in range(repos_script.MAX_REPOS + 1)]
    with pytest.raises(repos_script.RepoListError, match="at most 256"):
        repos_script.parse_repos(_list(*repos))


def test_the_gallery_list(repos_script):
    groups, repos = repos_script.load_repos(_REPOS_YML)
    assert 90 <= len(repos) <= repos_script.MAX_REPOS
    assert groups[0].id == "python"
    # the reports published before keep their addresses
    ids = {repo.id for repo in repos}
    assert {
        "cpython", "vscode", "git", "nginx", "kubernetes", "nodejs", "django", "rust",
        "react", "homebrew", "codex", "gemini-cli", "opencode", "aider", "pytorch",
        "transformers", "langchain", "fastapi", "pandas", "numpy",
    } <= ids  # fmt: skip
    # a repository is in the gallery once, whatever its id
    urls = [repo.url.lower() for repo in repos]
    assert len(urls) == len(set(urls))
    # the ecosystems the issue template offers are the list's
    template = os.path.join(_ROOT, ".github", "ISSUE_TEMPLATE", "gallery.yml")
    with open(template, encoding="utf-8") as f:
        text = f.read()
    for group in groups:
        assert f"        - {group.name}\n" in text


def test_load_repos_rejects_what_is_not_yaml(repos_script, tmp_path):
    path = tmp_path / "repos.yml"
    path.write_text("groups: [unclosed\n", encoding="utf-8")
    with pytest.raises(repos_script.RepoListError, match="not YAML"):
        repos_script.load_repos(str(path))


def test_main_prints_the_matrix(repos_script, capsys):
    assert repos_script.main(["matrix", _REPOS_YML]) == 0
    matrix = json.loads(capsys.readouterr().out)
    assert matrix[0] == {
        "id": "cpython",
        "name": "CPython",
        "url": "python/cpython",
        "group": "python",
        "timeout": 90,
    }


def test_main_prints_the_ids(repos_script, capsys):
    assert repos_script.main(["ids", _REPOS_YML]) == 0
    assert capsys.readouterr().out.splitlines()[:2] == ["cpython", "django"]


def test_main_usage_and_errors(repos_script, tmp_path, capsys):
    assert repos_script.main([]) == 2
    assert repos_script.main(["list", _REPOS_YML]) == 2
    assert "Usage:" in capsys.readouterr().err
    missing = str(tmp_path / "missing.yml")
    assert repos_script.main(["ids", missing]) == 1
    assert missing in capsys.readouterr().err
