FAQ
===

1. How do I generate statistics of a non-master branch?

    Use the ``-c commit_end=devel`` parameter.

2. I have files in my git repository that I would like to exclude from the statistics. How do I do that?

    At the moment, the only way is to use `git-filter-branch(1) <https://git-scm.com/docs/git-filter-branch>`_ to create a temporary repository and generate the statistics from that.

3. How do I merge author information when the same author has made commits using different names or emails?

    GitStats automatically merges authors who share the same email address, so commits made under different display names (e.g. ``Xianpeng Shen`` vs ``Xianpeng``) are unified under the most recently used name with no extra configuration needed.

    For cases where the same person has used *different* email addresses, use Git's ``.mailmap`` feature to map them to a single canonical identity, as described in the `gitmailmap <https://git-scm.com/docs/gitmailmap>`_ documentation.

4. How does GitStats know that a commit is AI-assisted?

    It does not know how a commit was written: Git does not record that. The Authors page counts the commits that *name* an AI coding assistant, in one of four ways:

    - The author is an assistant's own account, such as the Copilot coding agent, Devin or Cursor's agent.
    - A ``Co-authored-by:`` line names an assistant, as Claude Code, GitHub Copilot, Cursor, Codex, Aider and others add when they commit for a person. A review bot whose suggestion was applied is named the same way.
    - An ``Assisted-by:`` or ``Generated-by:`` line names an assistant, as in ``Assisted-by: Claude Code``.
    - The message has the line an assistant leaves in it, such as ``Generated with [Claude Code]`` or the link to a Devin or Codex session.

    The numbers are lower bounds. An assistant that completes lines in an editor leaves no mark in the commit, and an assistant that signs can be told not to. A mark says that an assistant took part in a commit, not how much of it the assistant wrote, which is why lines are not counted.

    Accounts and addresses are matched, not first names: a person called Claude, Devin or Jules is not an assistant. The marks are listed in ``gitstats/assistants.py``; the same numbers are in the JSON output as ``ai_assisted_commits``, ``ai_assisted_authored``, ``ai_assisted_by_month`` and ``ai_assistants``.
