.. start-of-about

.. figure:: https://raw.githubusercontent.com/shenxianpeng/gitstats/main/docs/source/logo.png
   :alt: Project Logo
   :align: center
   :width: 200px

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

|pypi-version| |python-versions| |python-download| |test-badge| |docs-badge| |contributors| |marketplace|

``$ gitstats``
===============

📊 Generate insightful visual reports from Git.

📘 Documentation: `gitstats.readthedocs.io <https://gitstats.readthedocs.io/>`_

⚡ `GitStats Gallery <https://shenxianpeng.github.io/gitstats/gallery/>`_ — live reports for the Linux Kernel, CPython, VS Code, and more.

.. contents:: Table of Contents
   :depth: 2
   :local:


Example
-------

``gitstats .`` generates this `gitstats report <https://shenxianpeng.github.io/gitstats/index.html>`_.

Check out the `GitStats Gallery <https://shenxianpeng.github.io/gitstats/gallery/>`_ for live reports on the world's largest open-source projects — auto-generated weekly.

.. list-table:: Featured Reports
   :header-rows: 1

   * - Project
     - Report
     - Repository
   * - Linux Kernel
     - `Report <https://shenxianpeng.github.io/gitstats/gallery/linux/index.html>`_
     - `torvalds/linux <https://github.com/torvalds/linux>`_
   * - CPython
     - `Report <https://shenxianpeng.github.io/gitstats/gallery/cpython/index.html>`_
     - `python/cpython <https://github.com/python/cpython>`_
   * - VS Code
     - `Report <https://shenxianpeng.github.io/gitstats/gallery/vscode/index.html>`_
     - `microsoft/vscode <https://github.com/microsoft/vscode>`_
   * - Git
     - `Report <https://shenxianpeng.github.io/gitstats/gallery/git/index.html>`_
     - `git/git <https://github.com/git/git>`_
   * - nginx
     - `Report <https://shenxianpeng.github.io/gitstats/gallery/nginx/index.html>`_
     - `nginx/nginx <https://github.com/nginx/nginx>`_
   * - Kubernetes
     - `Report <https://shenxianpeng.github.io/gitstats/gallery/kubernetes/index.html>`_
     - `kubernetes/kubernetes <https://github.com/kubernetes/kubernetes>`_

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
