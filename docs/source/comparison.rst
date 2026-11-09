======================
Lineage and comparison
======================

Where gitstats comes from
=========================

``gitstats`` was written by `Heikki Hokkanen <https://github.com/hoxu>`_ and
released from 2007 to 2014. This project is its maintained continuation. It
keeps the name, the licence (GPLv2 or GPLv3, at your option) and the original
idea: read a repository's Git history and write a report you can open in a
browser.

The original is credited in full in :doc:`copyright` and :doc:`contributors`,
and its licence terms still govern this code: see :doc:`license`.

If you arrived here from a page that lists ``gitstats`` as unmaintained, it was
describing the original. This continuation is released regularly from
`PyPI <https://pypi.org/project/gitstats/>`_.

What changed since the original
===============================

**Python 3.10 and newer.**
   The original needed Python 2. There is no Python 2 code left.

**Charts are drawn in the browser.**
   The original shipped PNG files rendered by Gnuplot, which had to be
   installed first. Charts are now drawn by `Chart.js
   <https://www.chartjs.org/>`_, bundled into the report, so a report is
   self-contained HTML and Gnuplot is not required.

**A redesigned report.**
   Monospace headings and navigation, a border-heavy layout, a GitHub-style
   green heatmap, and light and dark themes with a one-click toggle that does
   not flash when you move between pages. The layouts work on a phone.

**JSON as well as HTML.**
   ``-f json`` writes the same numbers as data, so a report can be queried,
   diffed or fed to something else rather than only read.

**Pages the original did not have.**
   Code ownership and bus factor, hotspots, a per-year history, the commits
   that name an AI coding assistant, commits grouped by the organization behind
   each author's email domain, and a portfolio view across several
   repositories. See the feature list in the `README
   <https://github.com/shenxianpeng/gitstats>`_.

**Things to share.**
   SVG badges, a square ``--wrapped`` card for one year, and a link-preview
   card on every page.

**A way to run it on a schedule.**
   `gitstats-action <https://github.com/marketplace/actions/gitstats-action>`_
   builds the report in CI and publishes it to GitHub Pages.

Other tools in this space
=========================

These tools overlap with ``gitstats`` but answer different questions. Pick by
the question you have, not by the size of the tool.

The release dates below were read from PyPI on 9 November 2026. They say
whether a project is still shipping, which is usually the thing you want to
know; they are not a measure of quality.

.. list-table::
   :header-rows: 1
   :widths: 22 48 30

   * - Tool
     - What it gives you
     - Latest release on PyPI
   * - ``gitstats``
     - A multi-page HTML report plus JSON, for one repository or several.
     - 2.12.2, 30 October 2026
   * - `git-fame <https://pypi.org/project/git-fame/>`_
     - Per-author line, commit and file totals, printed in the terminal.
     - 4.2.1, 7 September 2026
   * - `git-of-theseus <https://pypi.org/project/git-of-theseus/>`_
     - How much of today's code survives from each past commit, as plots.
     - 0.3.4, 7 March 2023
   * - `gitinspector <https://pypi.org/project/gitinspector/>`_
     - Per-author statistics as text, HTML or XML.
     - 0.3.2, 5 August 2015

Outside Python, `git-quick-stats <https://github.com/arzzen/git-quick-stats>`_
is a shell menu over ``git log`` for quick answers in a terminal, and `onefetch
<https://github.com/o2sh/onefetch>`_ prints a summary beside the project's
logo. `cloc <https://github.com/AlDanial/cloc>`_, `tokei
<https://github.com/XAMPPRocky/tokei>`_ and `scc
<https://github.com/boyter/scc>`_ count lines by language in a working tree and
do not read history at all. For a hosted dashboard over many repositories,
look at `Apache DevLake <https://devlake.apache.org/>`_, `GrimoireLab
<https://chaoss.github.io/grimoirelab/>`_ or `OSS Insight
<https://ossinsight.io/>`_ instead; those are services to run, not a command to
put in CI.

What gitstats does not claim
============================

The numbers in a report describe **activity**, not productivity or worth.
Commit counts depend on how a person happens to split their work, and lines of
code go down when someone refactors well. Both are easy to inflate on purpose,
so neither belongs in a performance review. Read them as a description of what
happened in a repository, which is what they are.

For the same reason, per-author figures stay in the report you generate, on
your own machine or in your own CI. The public `gallery
<https://shenxianpeng.dev/gitstats/gallery/>`_ ranks projects, never people.

``gitstats`` also cannot tell you how a commit was written. The AI-assisted
count looks for commits that *name* an assistant, which is a lower bound and
nothing more: see the FAQ entry in :doc:`faq`.
