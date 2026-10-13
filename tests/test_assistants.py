"""Tests for gitstats.assistants – which AI coding assistant a commit names."""

import os
import subprocess

import pytest

from gitstats.assistants import (
    _HINTS,
    IDENTITIES,
    SIGNATURES,
    UNNAMED,
    AssistedCommit,
    assistant_of,
    assistants_named,
    assisted_commits,
)

# ── an author or a co-author ─────────────────────────────────────────────
# As they are written in real histories.

ACCOUNTS = [
    ("Claude <noreply@anthropic.com>", "Claude"),
    ("Claude Opus 4.6 (1M context) <noreply@anthropic.com>", "Claude"),
    ("claude[bot] <209825114+claude[bot]@users.noreply.github.com>", "Claude"),
    ("anthropic-code-agent[bot] <242468646+Claude@users.noreply.github.com>", "Claude"),
    ("Copilot <198982749+Copilot@users.noreply.github.com>", "GitHub Copilot"),
    ("Copilot <175728472+Copilot@users.noreply.github.com>", "GitHub Copilot"),
    ("copilot-swe-agent[bot] <198982749+Copilot@users.noreply.github.com>", "GitHub Copilot"),
    ("GitHub Copilot <copilot@github.com>", "GitHub Copilot"),
    (
        "Copilot Autofix powered by AI "
        "<62310815+github-advanced-security[bot]@users.noreply.github.com>",
        "GitHub Copilot",
    ),
    ("Cursor <cursoragent@cursor.com>", "Cursor"),
    ("Cursor Agent <cursoragent@cursor.com>", "Cursor"),
    ("cursor[bot] <206951365+cursor[bot]@users.noreply.github.com>", "Cursor"),
    ("Codex <codex@openai.com>", "Codex"),
    (
        "chatgpt-codex-connector[bot] "
        "<199175422+chatgpt-codex-connector[bot]@users.noreply.github.com>",
        "Codex",
    ),
    ("Devin AI <158243242+devin-ai-integration[bot]@users.noreply.github.com>", "Devin"),
    (
        "devin-ai-integration[bot] <158243242+devin-ai-integration[bot]@users.noreply.github.com>",
        "Devin",
    ),
    (
        "google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
        "Jules",
    ),
    (
        "gemini-code-assist[bot] <176961590+gemini-code-assist[bot]@users.noreply.github.com>",
        "Gemini",
    ),
    ("aider (claude-sonnet-4) <aider@aider.chat>", "Aider"),
    ("Jane Doe (aider) <jane@example.com>", "Aider"),
    ("Amp <amp@ampcode.com>", "Amp"),
    ("openhands <openhands@all-hands.dev>", "OpenHands"),
    ("OpenCode:glm-5", "OpenCode"),
    ("opencode <noreply@opencode.ai>", "OpenCode"),
    ("Warp <agent@warp.dev>", "Warp"),
    ("Oz <oz-agent@warp.dev>", "Warp"),
    (
        "factory-droid[bot] <138933559+factory-droid[bot]@users.noreply.github.com>",
        "Factory Droid",
    ),
    (
        "amazon-q-developer[bot] <208079219+amazon-q-developer[bot]@users.noreply.github.com>",
        "Amazon Q",
    ),
    ("lovable-dev[bot] <159125892+lovable-dev[bot]@users.noreply.github.com>", "Lovable"),
    (
        "gpt-engineer-app[bot] <159125892+gpt-engineer-app[bot]@users.noreply.github.com>",
        "Lovable",
    ),
    ("sweep-ai[bot] <128439645+sweep-ai[bot]@users.noreply.github.com>", "Sweep"),
    ("coderabbitai[bot] <136622811+coderabbitai[bot]@users.noreply.github.com>", "CodeRabbit"),
    ("sourcery-ai[bot] <58596630+sourcery-ai[bot]@users.noreply.github.com>", "Sourcery"),
]


@pytest.mark.parametrize("identity, assistant", ACCOUNTS)
def test_an_assistant_is_known_by_its_account(identity, assistant):
    assert assistant_of(identity) == assistant
    # whatever the case it is written in
    assert assistant_of(identity.upper()) == assistant


def test_every_assistant_listed_has_an_account_tried_here():
    assert {name for name, _ in IDENTITIES} == {assistant for _, assistant in ACCOUNTS}


@pytest.mark.parametrize(
    "identity",
    [
        # people, all of them with commits in the histories these were taken from
        "Cody Maloney <cmaloney@users.noreply.github.com>",
        "Jules Lasne <jules.lasne@gmail.com>",
        "Devin Nusbaum <d.w.nusbaum@gmail.com>",
        "Ludovic Claude <ludovic.claude@lbpoker.com>",
        "memento <claude.rc@gmail.com>",
        "Giovanni Tirloni <gpt@gtirloni.com>",
        "Raunak Madan <CodexRaunak@users.noreply.github.com>",
        "Eli Libman <eli@hyro.ai>",
        "Claude Monet <12345+claude@users.noreply.github.com>",
        # a name anyone may give themselves is not enough
        "Copilot <someone@example.com>",
        "Cursor <me@example.com>",
        # bots that are not assistants
        "dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
        "pre-commit-ci[bot] <66853113+pre-commit-ci[bot]@users.noreply.github.com>",
        "github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>",
        "",
    ],
)
def test_a_person_or_another_bot_is_not_an_assistant(identity):
    assert assistant_of(identity) is None


# ── what a commit names ──────────────────────────────────────────────────

PERSON = "Alice Smith <alice@example.com>"


def _message(*lines):
    return "Fix the parser\n\nIt lost the last line.\n\n" + "\n".join(lines) + "\n"


@pytest.mark.parametrize(
    "lines, assistants",
    [
        (["Co-authored-by: Claude Opus 4.6 <noreply@anthropic.com>"], ["Claude"]),
        (["Co-Authored-By: Claude <noreply@anthropic.com>"], ["Claude"]),
        (["co-authored-by : Cursor <cursoragent@cursor.com>  "], ["Cursor"]),
        (
            [
                "Co-authored-by: Bob Jones <bob@example.com>",
                "Co-authored-by: Copilot <175728472+Copilot@users.noreply.github.com>",
                "Co-authored-by: Claude <noreply@anthropic.com>",
                "Co-authored-by: Copilot <175728472+Copilot@users.noreply.github.com>",
            ],
            ["GitHub Copilot", "Claude"],
        ),
        (["Co-authored-by: OpenCode:glm-5"], ["OpenCode"]),
        # the line an assistant signs with
        (["🤖 Generated with [Claude Code](https://claude.com/claude-code)"], ["Claude"]),
        (["Generated with [Claude Code](https://claude.ai/code)"], ["Claude"]),
        (["https://claude.ai/code/session_01AbCdEf"], ["Claude"]),
        (["🤖 Generated with [opencode](https://opencode.ai)"], ["OpenCode"]),
        (["Amp-Thread-ID: https://ampcode.com/threads/T-1234"], ["Amp"]),
        (["Link to Devin run: https://app.devin.ai/sessions/abc123"], ["Devin"]),
        (["------", "https://chatgpt.com/codex/tasks/task_e_68a1"], ["Codex"]),
        # the trailers a project asks for
        (["Assisted-by: Claude Code"], ["Claude"]),
        (["Assisted-By: GitHub Copilot"], ["GitHub Copilot"]),
        (["Generated-by: ChatGPT (GPT-4)"], ["ChatGPT"]),
        (["Generated-By: Gemini 2.5 Pro"], ["Gemini"]),
        (["Assisted-by: Cursor <cursoragent@cursor.com>"], ["Cursor"]),
        (["Assisted-by: claude and copilot"], ["Claude", "GitHub Copilot"]),
        # the assistant, then the model it ran: the assistant is the one counted
        (["Assisted-by: Copilot:claude-sonnet-4.6"], ["GitHub Copilot"]),
        (["Assisted-by: OpenCode:Kimi-K2.6", "Assisted-by: OpenCode:glm-5.1"], ["OpenCode"]),
        (["Assisted-by: Claude:claude-3-opus coccinelle sparse"], ["Claude"]),
        # an assistant it does not know runs a model it does
        (["Assisted-by: Kimi:claude-opus-4"], ["Claude"]),
        (["Assisted-by: AI"], [UNNAMED]),
        (["Generated-by: an LLM, then edited"], [UNNAMED]),
        # several marks, one commit
        (
            [
                "🤖 Generated with [Claude Code](https://claude.com/claude-code)",
                "",
                "Co-Authored-By: Claude <noreply@anthropic.com>",
            ],
            ["Claude"],
        ),
    ],
)
def test_a_commit_names_its_assistants(lines, assistants):
    message = _message(*lines)
    assert assistants_named(PERSON, message) == (assistants, False)
    # and the message is one that is looked at: see _HINTS
    assert any(hint in message.lower() for hint in _HINTS)


@pytest.mark.parametrize(
    "lines",
    [
        [],
        ["Co-authored-by: Bob Jones <bob@example.com>"],
        ["Co-authored-by: Cody Maloney <cmaloney@users.noreply.github.com>"],
        ["Signed-off-by: Claude Monet <claude@example.com>", "Reviewed-by: Devin Nusbaum <d@e.f>"],
        # these trailers are used for people and for scripts as well
        ["Assisted-by: Jeff Layton <jlayton@kernel.org>"],
        ["Assisted-by: Jeff Layton"],
        ["Generated-by: make update-deps"],
        # a template, not an assistant
        ["Generated with [Copier](https://copier.readthedocs.io)"],
        # said in passing, not signed
        ["We tried Claude Code and Copilot on this, and wrote it by hand in the end."],
        ["See the notes on aider: they are in docs/tools.md"],
        ["The cursor: pointer rule was missing"],
    ],
)
def test_a_commit_that_names_none(lines):
    assert assistants_named(PERSON, _message(*lines)) == ([], False)


def test_a_commit_an_assistant_made_itself():
    copilot = "copilot-swe-agent[bot] <198982749+Copilot@users.noreply.github.com>"
    assert assistants_named(copilot, "Initial plan\n") == (["GitHub Copilot"], True)
    # the person it worked for is its co-author
    message = _message("Co-authored-by: Alice Smith <alice@example.com>")
    assert assistants_named(copilot, message) == (["GitHub Copilot"], True)
    # the author comes first, whatever else is named
    message = _message("Co-authored-by: Claude <noreply@anthropic.com>")
    assert assistants_named(copilot, message) == (["GitHub Copilot", "Claude"], True)


def test_aider_names_itself_in_the_subject():
    assert assistants_named(PERSON, "aider: Fix the off-by-one in the parser\n") == (
        ["Aider"],
        False,
    )
    # not anywhere else in a line
    assert assistants_named(PERSON, "Fix the parser\n\nNotes for aider: none\n") == ([], False)


def test_every_signature_has_a_hint():
    """A message that holds a signature holds one of the hints it is looked
    for by: each pattern has a literal part that is one, or contains one."""
    for _, pattern in SIGNATURES:
        for alternative in pattern.split("|"):
            literal = alternative.replace("\\", "").lstrip("^").replace(" *", " ")
            assert any(hint in literal for hint in _HINTS), alternative


# ── the commits of a history ─────────────────────────────────────────────


def _commit(repo, author, date, *paragraphs):
    name, _, email = author.partition(" <")
    env = {
        **os.environ,
        "LC_ALL": "C",
        "GIT_AUTHOR_NAME": name,
        "GIT_AUTHOR_EMAIL": email.rstrip(">"),
        "GIT_COMMITTER_NAME": "Alice Smith",
        "GIT_COMMITTER_EMAIL": "alice@example.com",
        "GIT_AUTHOR_DATE": date,
        "GIT_COMMITTER_DATE": date,
    }
    args = [arg for paragraph in paragraphs for arg in ("-m", paragraph)]
    subprocess.run(
        ["git", "commit", "-q", "--allow-empty", *args],
        cwd=repo,
        check=True,
        env=env,
        capture_output=True,
    )


@pytest.fixture
def assisted_repo(temp_dir):
    """Seven commits: four name an assistant, one of them as its author."""
    repo = os.path.join(temp_dir, "assisted")
    os.makedirs(repo)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    _commit(repo, PERSON, "2025-01-10T12:00:00+0000", "Start")
    _commit(
        repo,
        "Cody Maloney <cody@example.com>",
        "2025-02-10T12:00:00+0000",
        "By hand",
        "Co-authored-by: Bob Jones <bob@example.com>",
    )
    _commit(
        repo,
        PERSON,
        "2025-03-10T12:00:00+0000",
        "Parse the header",
        "The first line was skipped.",
        "🤖 Generated with [Claude Code](https://claude.com/claude-code)\n\n"
        "Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>",
    )
    _commit(
        repo,
        "copilot-swe-agent[bot] <198982749+Copilot@users.noreply.github.com>",
        "2025-03-20T12:00:00+0000",
        "Initial plan",
    )
    _commit(
        repo,
        "Bob Jones <bob@example.com>",
        "2025-04-10T12:00:00+0000",
        "Tidy up",
        "Assisted-by: Copilot:claude-sonnet-4.6",
    )
    _commit(repo, PERSON, "2025-05-10T12:00:00+0000", "Docs, about Claude Code and Copilot")
    _commit(
        repo,
        "Zoë Müller <zoe@example.com>",
        "2025-06-10T12:00:00+0000",
        "Un café, s'il vous plaît",
        "Co-authored-by: Cursor <cursoragent@cursor.com>\n"
        "Co-authored-by: Claude <noreply@anthropic.com>",
    )
    return repo


def _stamp(date):
    import datetime

    return int(datetime.datetime.fromisoformat(date).timestamp())


def test_assisted_commits_of_a_history(assisted_repo, monkeypatch):
    monkeypatch.chdir(assisted_repo)
    # newest first, as git log lists them
    assert list(assisted_commits("HEAD")) == [
        AssistedCommit(_stamp("2025-06-10T12:00:00+00:00"), ["Cursor", "Claude"], False),
        AssistedCommit(_stamp("2025-04-10T12:00:00+00:00"), ["GitHub Copilot"], False),
        AssistedCommit(_stamp("2025-03-20T12:00:00+00:00"), ["GitHub Copilot"], True),
        AssistedCommit(_stamp("2025-03-10T12:00:00+00:00"), ["Claude"], False),
    ]


@pytest.mark.parametrize(
    "log_range, assistants",
    [
        ('--since="2025-04-01" "HEAD"', [["Cursor", "Claude"], ["GitHub Copilot"]]),
        ('--until="2025-03-15" "HEAD"', [["Claude"]]),
        # the commits of these authors, and not those an assistant made itself
        ('--author="Alice Smith" --author="Bob Jones" "HEAD"', [["GitHub Copilot"], ["Claude"]]),
        ("HEAD~2..HEAD", [["Cursor", "Claude"]]),
        ('--author="Nobody" "HEAD"', []),
    ],
)
def test_assisted_commits_keep_to_the_range(assisted_repo, monkeypatch, log_range, assistants):
    monkeypatch.chdir(assisted_repo)
    assert [commit.assistants for commit in assisted_commits(log_range)] == assistants


def test_assisted_commits_of_a_history_without_any(git_repo, monkeypatch):
    monkeypatch.chdir(git_repo)
    assert list(assisted_commits("HEAD")) == []
