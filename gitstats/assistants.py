"""Which AI coding assistant a commit names.

Git records who made a commit, not how it was written. What a history does
keep is what the assistants sign with: the account an agent commits under, the
co-author line an assistant adds to a person's commit, the line it closes the
message with, and the trailers some projects ask their contributors for. A
commit that carries one of these marks is counted as AI-assisted, under the
assistant it names.

That makes the count a lower bound. An assistant that completes lines in an
editor leaves no mark, and those that sign can be told not to. A mark says
that an assistant took part in the commit, not how much of it it wrote.

The marks are matched narrowly: an account or an address, never a first name.
People are called Claude, Cody, Devin and Jules, and they commit a lot.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import NamedTuple

from gitstats.utils import get_pipe_output

# An assistant, and what it looks like as an author or a co-author: "Name <email>",
# whatever the case. An agent that commits under its own account is the author;
# one that helps a person is named in a "Co-authored-by:" trailer, as is a
# review bot whose suggestion was applied.
IDENTITIES: tuple[tuple[str, str], ...] = (
    ("Claude", r"<noreply@anthropic\.com>$|^(claude|anthropic-code-agent)\[bot\] <"),
    (
        "GitHub Copilot",
        r"<(\d+\+)?copilot@users\.noreply\.github\.com>$|<copilot@github\.com>$"
        r"|^copilot(-swe-agent|-pull-request-reviewer)?\[bot\] <|^copilot autofix ",
    ),
    ("Cursor", r"<cursoragent@cursor\.com>$|^cursor\[bot\] <"),
    ("Codex", r"<codex@openai\.com>$|^chatgpt-codex-connector\[bot\] <"),
    ("Devin", r"devin-ai-integration\[bot\]"),
    ("Jules", r"^google-labs-jules\[bot\] <"),
    ("Gemini", r"^gemini-code-assist\[bot\] <"),
    # its own addresses, not every one at aider.chat: its maintainer commits from one
    ("Aider", r"<(aider@aider\.chat|noreply@aider\.dev)>$|\(aider\) <"),
    ("Amp", r"<amp@ampcode\.com>$"),
    ("OpenHands", r"<openhands@all-hands\.dev>$"),
    # Not the accounts the OpenCode project commits under: "opencode
    # <opencode@sst.dev>" makes its releases, and opencode-agent[bot] mostly
    # regenerates files, between the changes its agent makes.
    ("OpenCode", r"<noreply@opencode\.ai>$|^opencode[:/]"),
    ("Warp", r"<(agent|oz-agent)@warp\.dev>$"),
    ("Factory Droid", r"^factory-droid\[bot\] <"),
    ("Amazon Q", r"^amazon-q-developer\[bot\] <"),
    ("Lovable", r"^(lovable-dev|gpt-engineer-app)\[bot\] <"),
    ("Sweep", r"^sweep-ai\[bot\] <"),
    ("CodeRabbit", r"^coderabbitai\[bot\] <"),
    ("Sourcery", r"^sourcery-ai\[bot\] <"),
)

# An assistant, and a line it leaves in the commit message
SIGNATURES: tuple[tuple[str, str], ...] = (
    ("Claude", r"generated with \[claude code\]|https://claude\.ai/code/session_"),
    ("OpenCode", r"generated with \[opencode\]"),
    ("Amp", r"^amp-thread-id: *https://ampcode\.com/"),
    ("Devin", r"https://app\.devin\.ai/sessions/"),
    ("Codex", r"https://chatgpt\.com/codex/tasks/"),
    ("Aider", r"^aider: "),
)

CO_AUTHOR = r"^co-authored-by *:"
# The trailers a project may ask for when an assistant took part, as in
# "Assisted-by: Claude Code" or "Generated-by: GitHub Copilot". They are also
# used for people and for scripts, so the value has to name an assistant.
DISCLOSURE = r"^(?:assisted|generated)-by *:"
NAMED: tuple[tuple[str, str], ...] = (
    # or one of its models by name and version, as in "Assisted-by: Opus 5.5":
    # without the version, Opus is an audio codec too
    ("Claude", r"claude|anthropic|\b(?:opus|sonnet|haiku|fable)[- ]?\d"),
    ("GitHub Copilot", r"copilot"),
    ("Cursor", r"\bcursor\b"),
    ("Codex", r"\bcodex\b"),
    ("ChatGPT", r"chatgpt|openai|\bgpt-?\d"),
    ("Gemini", r"\bgemini\b"),
    ("Jules", r"google[- ]labs[- ]jules"),
    ("Devin", r"\bdevin ai\b|devin\.ai"),
    ("Aider", r"\baider\b"),
    # "Amp" alone, but not as a word in a longer value
    ("Amp", r"ampcode|\bamp code\b|^amp$"),
    ("OpenHands", r"openhands"),
    ("OpenCode", r"\bopencode\b"),
    ("Windsurf", r"windsurf|codeium"),
    ("Kiro", r"\bkiro\b"),
    ("Cline", r"\bcline\b"),
    ("Amazon Q", r"amazon q\b|codewhisperer"),
    ("Grok", r"\bgrok\b"),
    # not Bob alone, who is a person
    ("IBM Bob", r"\bibm bob\b"),
    # the pi coding agent: "pi" only as the whole value, never as a word in it
    ("Pi", r"\bpi[- ]coding[- ]agent\b|^pi$"),
)
# An assistant the trailer admits to without naming it: "Assisted-by: AI", or
# "Assisted-by: a closed-source coding agent", as Node.js suggests to those who
# would rather not name a brand
UNNAMED = "Unnamed assistant"
_UNNAMED = re.compile(
    r"\b(?:ai|llm|genai)\b|\bcoding (?:agent|assistant)\b|\b(?:reasoning|language) model\b",
    re.I,
)

_IDENTITIES = [(name, re.compile(pattern, re.I)) for name, pattern in IDENTITIES]
_SIGNATURES = [(name, re.compile(pattern, re.I | re.M)) for name, pattern in SIGNATURES]
_NAMED = [(name, re.compile(pattern, re.I)) for name, pattern in NAMED]
_CO_AUTHOR = re.compile(CO_AUTHOR + r" *(.+?) *$", re.I | re.M)
_DISCLOSURE = re.compile(DISCLOSURE + r" *(.+?) *$", re.I | re.M)
# What a message that holds a mark has in it, in lower case. Most messages
# have none of these, and running the patterns above on every one of them
# would take longer than git takes to print them.
_HINTS = (
    "co-authored-by",
    "assisted-by",
    "generated-by",
    "generated with [",
    "claude.ai/code/",
    "amp-thread-id",
    "devin.ai/sessions/",
    "chatgpt.com/codex/",
    "aider: ",
)
# What starts a commit in the output of `git log` below: no message holds one
_COMMIT = "\x00"


class AssistedCommit(NamedTuple):
    stamp: int  # when it was written, as the author's clock had it
    assistants: list[str]  # those it names, in the order found
    authored: bool  # one of them is its author, not a person's co-author


def assistant_of(identity: str) -> str | None:
    """The assistant that commits or co-authors as "Name <email>", if it is one."""
    for name, pattern in _IDENTITIES:
        if pattern.search(identity):
            return name
    return None


def assistants_named(author: str, message: str) -> tuple[list[str], bool]:
    """The assistants named by the commit of this author ("Name <email>") and
    message, and whether one of them is the author."""
    found: dict[str, None] = {}
    authored = assistant_of(author)
    if authored:
        found[authored] = None
    for co_author in _CO_AUTHOR.findall(message):
        name = assistant_of(co_author)
        if name:
            found[name] = None
    for name, pattern in _SIGNATURES:
        if pattern.search(message):
            found[name] = None
    for value in _DISCLOSURE.findall(message):
        name = assistant_of(value)
        if name:
            found[name] = None
            continue
        if "@" in value:
            # a person: "Assisted-by: Jane Doe <jane@example.com>"
            continue
        # "Assisted-by: Copilot:claude-sonnet-4.6" is the assistant, then the
        # model it ran: the assistant is the one to count, when it is known
        agent = value.partition(":")[0]
        named = [name for name, pattern in _NAMED if pattern.search(agent)] or [
            name for name, pattern in _NAMED if pattern.search(value)
        ]
        if named:
            found.update(dict.fromkeys(named))
        elif _UNNAMED.search(value):
            found[UNNAMED] = None
    return list(found), authored is not None


def assisted_commits(log_range: str) -> Iterator[AssistedCommit]:
    """The commits of ``log_range`` that name an AI coding assistant.

    One reading of the history, which compares nothing: who wrote each
    commit, and its message. (Having git pick the messages with --grep is
    slower than having it print them all.)
    """
    output = get_pipe_output([f'git log --format="%x00%at%x09%aN <%aE>%n%B" {log_range}'])
    # a few thousand different authors at most: each is looked at once
    is_assistant: dict[str, bool] = {}
    for block in output.split(_COMMIT)[1:]:
        header, _, message = block.partition("\n")
        stamp, _, author = header.partition("\t")
        if author not in is_assistant:
            is_assistant[author] = assistant_of(author) is not None
        if not is_assistant[author]:
            lowered = message.lower()
            if not any(hint in lowered for hint in _HINTS):
                continue
        assistants, authored = assistants_named(author, message)
        if assistants and stamp.isdigit():
            yield AssistedCommit(int(stamp), assistants, authored)
