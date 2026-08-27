.. image:: https://raw.githubusercontent.com/shenxianpeng/gitstats/main/docs/source/banner-dark.png#gh-dark-mode-only
   :alt: gitstats — git history statistics
   :width: 100%

.. image:: https://raw.githubusercontent.com/shenxianpeng/gitstats/main/docs/source/banner-light.png#gh-light-mode-only
   :alt: gitstats — git history statistics
   :width: 100%

.. start-of-about

.. |pypi-version| image:: https://img.shields.io/pypi/v/gitstats?color=blue
   :target: https://pypi.org/project/gitstats/
   :alt: PyPI - Version

.. |python-versions| image:: https://img.shields.io/pypi/pyversions/gitstats
   :alt: PyPI - Python Version

.. |python-download| image:: https://static.pepy.tech/badge/gitstats/week
   :target: https://pepy.tech/projects/gitstats
   :alt: PyPI Downloads

.. |test-badge| image:: https://github.com/shenxianpeng/gitstats/actions/workflows/test.yml/badge.svg
   :target: https://github.com/shenxianpeng/gitstats/actions/workflows/test.yml
   :alt: Test

.. |sonarcloud| image:: https://sonarcloud.io/api/project_badges/measure?project=shenxianpeng_gitstats&metric=alert_status
   :target: https://sonarcloud.io/summary/new_code?id=shenxianpeng_gitstats
   :alt: Quality Gate Status

.. |docs-badge| image:: https://readthedocs.org/projects/gitstats/badge/?version=latest
   :target: https://gitstats.readthedocs.io/
   :alt: Documentation

.. |contributors| image:: https://img.shields.io/github/contributors/shenxianpeng/gitstats
   :target: https://github.com/shenxianpeng/gitstats/graphs/contributors
   :alt: GitHub contributors

.. |marketplace| image:: https://img.shields.io/badge/GitHub_Marketplace-gitstats--action-blue.svg
   :target: https://github.com/marketplace/actions/gitstats-action
   :alt: GitHub Marketplace

.. |gitstats-report| image:: https://shenxianpeng.github.io/gitstats/badge.svg
   :target: https://shenxianpeng.github.io/gitstats/
   :alt: GitStats report

.. |gitstats-last-commit| image:: https://shenxianpeng.github.io/gitstats/badges/last-commit.svg
   :target: https://shenxianpeng.github.io/gitstats/
   :alt: GitStats last commit

|pypi-version| |python-versions| |python-download| |test-badge| |docs-badge| |contributors| |marketplace| |gitstats-report|

``$ gitstats``
===============

📊 Generate insightful visual reports from Git.

📘 Documentation: `gitstats.readthedocs.io <https://gitstats.readthedocs.io/>`_
📊 GitStats Gallery: `shenxianpeng.github.io/gitstats/gallery/ <https://shenxianpeng.github.io/gitstats/gallery/>`_

.. contents:: Table of Contents
   :depth: 2
   :local:
   :backlinks: none

Example
-------

``gitstats .`` generates this `gitstats report <https://shenxianpeng.github.io/gitstats/index.html>`_.

Check out the `GitStats Gallery <https://shenxianpeng.github.io/gitstats/gallery/>`_ for live reports on the world's largest open-source projects — auto-generated weekly.

.. image:: https://raw.githubusercontent.com/shenxianpeng/gitstats/main/docs/source/demo.gif
   :alt: gitstats terminal demo
   :align: center



Installation
------------

.. code-block:: bash

   pip install gitstats

Or, using `uv <https://docs.astral.sh/uv/>`_ (recommended):

.. code-block:: bash

   uv pip install gitstats      # install into current environment
   uvx gitstats .              # run instantly, no install required


gitstats is compatible with Python 3.10 and newer.


Usage
-----

.. code-block:: bash

   gitstats <gitpath> [<outputpath>]

If ``<outputpath>`` is omitted, reports are written to ``gitstats-report/`` by default.

Analyze several repositories at once to get a portfolio overview — useful for
seeing how all of a team's projects are doing in one place:

.. code-block:: bash

   gitstats repo1 repo2 repo3 <outputpath>

Each repository gets its full report in ``<outputpath>/<repo>/`` along with a
machine-readable ``summary.json``, and an aggregate page at
``<outputpath>/index.html`` shows a sortable table of every repository —
commits, authors, recent activity, lines of code and a health label — linking
into the individual reports. Repositories that fail to analyze are listed on
the page without stopping the run.

Use ``--verbose`` to show debug-level command logs, or ``--quiet`` to show only warnings and errors:

.. code-block:: bash

   gitstats --verbose .
   gitstats --quiet .


Run ``gitstats --help`` for more options, or check the `documentation <https://gitstats.readthedocs.io/en/latest/getting-started.html>`_.


GitHub Action
-------------

Automate your gitstats report generation with the official `GitStats Action <https://github.com/marketplace/actions/gitstats-action>`_.

.. code-block:: yaml

   - uses: shenxianpeng/gitstats-action@v0.1.1
     with:
       deploy-to-pages: true

With just one ``uses`` line, the Action generates a full gitstats report and deploys it to GitHub Pages automatically.

See the `gitstats-action repository <https://github.com/shenxianpeng/gitstats-action>`_ for detailed inputs, examples, and advanced usage (AI-powered reports, custom config, manual deploy, etc.).


Share Your Report with a Badge
------------------------------

Every report ships with a ``badge.svg`` next to ``index.html`` — a
shields.io-style badge in the gitstats brand colors that shows live
repository data (commit count by default). Because the badge lives inside
the report directory, wherever you host the report the badge is served from
the same URL, and it refreshes automatically every time the report is
regenerated.

This repository eats its own dog food — these are live badges served from
the `demo report <https://shenxianpeng.github.io/gitstats/>`_ (click one):

|gitstats-report| |gitstats-last-commit|

Embed it in your README so visitors can jump straight to the report:

.. code-block:: markdown

   [![GitStats](https://<your-report-url>/badge.svg)](https://<your-report-url>/)

Or in reStructuredText:

.. code-block:: rst

   .. image:: https://<your-report-url>/badge.svg
      :target: https://<your-report-url>/
      :alt: GitStats report

**Projects on GitHub** — the easiest path is the
`GitStats Action <https://github.com/marketplace/actions/gitstats-action>`_
with ``deploy-to-pages: true`` (see above). After the first run, the workflow's
job summary contains ready-to-copy badge markdown pointing at your GitHub
Pages report, e.g. ``https://<owner>.github.io/<repo>/badge.svg``.

**Projects hosted elsewhere** — publish the report output directory with any
static hosting you already use (GitLab Pages, Netlify, an internal web
server, ...) and point the badge at it. For example, on GitLab CI:

.. code-block:: yaml

   pages:
     script:
       - pip install gitstats
       - gitstats . public
     artifacts:
       paths:
         - public

then embed ``https://<group>.gitlab.io/<project>/badge.svg`` linking to
``https://<group>.gitlab.io/<project>/``.

Customizing the badge
~~~~~~~~~~~~~~~~~~~~~

Static hosting can't vary a file on ``?query`` parameters, so customization
works through pre-rendered files and configuration instead.

**Pick a metric by URL.** Alongside ``badge.svg``, every report contains a
``badges/`` directory with one badge per metric — switching what the badge
says is just switching the URL:

- ``badges/commits.svg`` — ``1,234 commits``
- ``badges/last-commit.svg`` — ``Aug 2026`` (date of the latest commit)
- ``badges/authors.svg`` — ``12 authors``
- ``badges/files.svg`` — ``245 files``
- ``badges/lines.svg`` — ``44,025 lines``

**Style with config keys.** The ``badge_*`` options control every generated
badge (including which metric ``badge.svg`` itself shows):

.. code-block:: bash

   gitstats -c badge_metric=last-commit \
            -c badge_label="my project" \
            -c badge_color=green \
            -c badge_style=flat-square . gitstats-report

``badge_color`` accepts shields.io color names (``brightgreen``, ``green``,
``yellow``, ``orange``, ``red``, ``blue``, ``lightgrey``), hex values like
``#30a14e``, or any SVG color. ``badge_style`` is ``flat`` (rounded, subtle
gradient) or ``flat-square`` (sharp corners, matching the report's angular
terminal aesthetic).

**Full shields.io customization.** Each metric is also exported as
``badges/<metric>.json`` in the `shields.io endpoint schema
<https://shields.io/badges/endpoint-badge>`_. Point shields at it and use
any of their URL parameters — arbitrary colors, ``style=for-the-badge``,
logos — while the data stays yours and stays live:

.. code-block:: markdown

   [![GitStats](https://img.shields.io/endpoint?url=https://<your-report-url>/badges/commits.json&style=for-the-badge&color=orange)](https://<your-report-url>/)


What's New in v2.0.0
--------------------

v2.0.0 is a major release focused on modernizing the report UI and removing the Gnuplot dependency.

**Terminal-inspired UI redesign**
   The entire report interface has been redesigned with a terminal / OpenCode-inspired aesthetic:
   zero border-radius (sharp, angular corners), monospace fonts in headings and navigation,
   border-heavy layout, and a GitHub-style green heatmap. Both light and dark modes are supported
   with a one-click toggle — no flash of unstyled content when switching pages.

**Chart.js replaces Gnuplot**
   All charts are now rendered interactively in the browser using `Chart.js <https://www.chartjs.org/>`_.
   Gnuplot is no longer required. Reports are fully self-contained HTML files.

Features
--------

Here is a list of some features of ``gitstats``:

* **General**: total files, lines, commits, authors, age.
* **Activity**: commits by hour of day, day of week, hour of week, month of year, year and month, and year.
* **Authors**: list of authors (name, commits (%), first commit date, last commit date, age), author of month, author of year.
* **Files**: file count by date, extensions.
* **Lines**: line of code by date.
* **Tags**: tags by date and author.
* **Customizable**: config values through ``gitstats.conf``.
* **Cross-platform**: works on Linux, Windows, and macOS.

AI-Powered Features 🤖
-----------------------

GitStats supports AI-powered insights to enhance your repository analysis with natural language summaries and actionable recommendations.

**Quick Start:**

.. code-block:: bash

   # Install with AI support
   pip install gitstats[ai]

   # Enable AI with OpenAI
   export OPENAI_API_KEY=your-api-key
   gitstats --ai --ai-provider openai <gitpath> [<outputpath>]

For detailed setup instructions, configuration options, and examples, see the `AI Integration Documentation <https://gitstats.readthedocs.io/en/stable/ai-integration.html>`_.

.. end-of-about

Contributing
------------

As an open source project, gitstats welcomes contributions of all forms.

----

The gitstats project was originally created by `Heikki Hokkainen <https://github.com/hoxu>`_ and is currently maintained by `Xianpeng Shen <https://github.com/shenxianpeng>`_.
