Getting Started
===============

Prerequisites
-------------

Before using gitstats, ensure you have the following installed:

- **Python 3.10+** - Download from https://www.python.org/downloads/
- **Git 2.24+** - Download from https://git-scm.com/

.. note::

    Starting from version ``2.0.0``, gitstats uses `Chart.js <https://www.chartjs.org/>`_ (bundled with the report) for rendering charts to modernize the visualizations and improve performance.

Installation
------------

Install `gitstats <https://pypi.org/project/gitstats/>`_ using `pip <https://pip.pypa.io/en/stable/>`_:

.. code-block:: bash

    pip install gitstats

Quick Start
-----------

Generate a basic report by running:

.. code-block:: bash

    gitstats .

.. tip::

    Alternatively, use `uv <https://docs.astral.sh/uv/>`_ to download and run gitstats in one command:

    .. code-block:: bash

        uvx gitstats .

Where:

- ``.`` is the current directory (your Git repository), you can specify any Git repository path.
- By default, reports are generated into ``gitstats-report/``. You can specify a custom output directory:

  .. code-block:: bash

      gitstats . my-custom-report

View a live example: https://shenxianpeng.dev/gitstats/index.html


Generate Report with JSON Output
---------------------------------

To generate both HTML and JSON formats:

.. code-block:: bash

    gitstats . --format json

This creates a ``report.json`` file alongside the HTML report.

.. tip::
   Use `jq <https://jqlang.github.io/jq/>`_ to parse the JSON file:

   .. code-block:: bash

       cat report.json | jq .

   This allows you to extract specific data or integrate with other tools.


Command Line Usage
------------------

Basic Syntax
~~~~~~~~~~~~

.. code-block:: bash

    gitstats [options] <gitpath> [<outputpath>]

**Arguments:**

- ``<gitpath>`` - Path to your Git repository (e.g., ``.`` for current directory).
  Give several to analyze each one and get a portfolio page that compares them;
  with two or more paths, the last one is the output directory.
- ``<outputpath>`` - Directory where the report will be generated (default: ``gitstats-report``)

**Options:**

- ``-h, --help`` - Show help message and exit
- ``-v, --version`` - Show program version number
- ``-c key=value, --config key=value`` - Override a configuration value (can be used
  multiple times). ``gitstats --help`` lists the keys; :doc:`configuration` explains them.
- ``-f {json}, --format {json}`` - Also write the report's data as JSON
- ``--site-url URL`` - Public address of the report, e.g. ``https://owner.github.io/repo/``.
  The snippets on the Badges page point at it, and the run log prints the README badge.
- ``--verbose`` - Enable debug logging, including command-level details
- ``--quiet`` - Only show warnings and errors

**Viewing the report:**

- ``--serve`` - After generating the report, serve it over HTTP until Ctrl+C
- ``--host HOST`` - Address the ``--serve`` server binds to (default: ``127.0.0.1``, this
  computer only; ``0.0.0.0`` makes it reachable from the network)
- ``--port PORT`` - Port of the ``--serve`` server, 1 to 65535 (default: ``8000``;
  ``0`` picks a free one)

**AI summaries** (see :doc:`ai-integration`):

- ``--ai, --no-ai`` - Turn AI-generated summaries on or off for this run
- ``--ai-provider {openai,claude,gemini,ollama}`` - AI provider to use
- ``--ai-model AI_MODEL`` - Model to use, as the provider names it
- ``--ai-language AI_LANGUAGE`` - Language of the summaries (``en``, ``zh``, ``ja``, ...)
- ``--refresh-ai`` - Ask the provider again instead of using cached summaries

**Repo Wrapped card:**

- ``--wrapped`` - Also write a shareable "Repo Wrapped" SVG card next to the report
- ``--wrapped-year YEAR`` - Year the card is for (default: the current year); a year
  without commits gets no card
- ``--wrapped-theme {midnight,sunset,clean}`` - Color theme of the card (default: ``midnight``)
- ``--wrapped-output PATH`` - File to write the card to, in an existing directory (default:
  ``<outputpath>/wrapped-<year>.svg``); single repository only

``gitstats --help`` prints the same list.

Examples
--------

Generate report for current directory:

.. code-block:: bash

    gitstats .

Generate report to a custom output directory:

.. code-block:: bash

    gitstats . my-report

Generate report for specific repository:

.. code-block:: bash

    gitstats /path/to/repo output-folder

Generate report with JSON output:

.. code-block:: bash

    gitstats . --format json

Show command-level debug logs:

.. code-block:: bash

    gitstats --verbose .

Show only warnings and errors:

.. code-block:: bash

    gitstats --quiet .

Generate the report and open it in a browser at http://127.0.0.1:8000/:

.. code-block:: bash

    gitstats . --serve

Also write this year's Repo Wrapped card:

.. code-block:: bash

    gitstats . --wrapped --wrapped-theme sunset

Override configuration values:

.. code-block:: bash

    gitstats . -c max_authors=10 -c authors_top=3

For more configuration options, see the :doc:`configuration` page.
