Getting Started
===============

Prerequisites
-------------

Before using gitstats, ensure you have the following installed:

- **Python 3.9+** - Download from https://www.python.org/downloads/
- **Git** - Download from https://git-scm.com/

.. note::

    Starting from version ``1.0.0``, gitstats uses the `gnuplot-wheel <https://pypi.org/project/gnuplot-wheel/>`_ package which bundles gnuplot as a Python dependency. You no longer need to install gnuplot separately!

Installation
------------

Install `gitstats <https://pypi.org/project/gitstats/>`_ using `pip <https://pip.pypa.io/en/stable/>`_:

.. code-block:: bash

    pip install gitstats

Quick Start
-----------

Generate a basic report by running:

.. code-block:: bash

    gitstats . report

.. tip::

    Alternatively, use `uv <https://docs.astral.sh/uv/>`_ to download and run gitstats in one command:

    .. code-block:: bash

        uvx gitstats . report

Where:

- ``.`` is the current directory (your Git repository), you can specify any Git repository path.
- ``report`` is the output directory where HTML files will be generated

View a live example: https://shenxianpeng.github.io/gitstats/index.html


Generate Report with JSON Output
---------------------------------

To generate both HTML and JSON formats:

.. code-block:: bash

    gitstats . report --format json

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

    gitstats [options] <gitpath> <outputpath>

**Arguments:**

- ``<gitpath>`` - Path to your Git repository (e.g., ``.`` for current directory)
- ``<outputpath>`` - Directory where the report will be generated

**Options:**

- ``-h, --help`` - Show help message and exit
- ``-v, --version`` - Show program version number
- ``-c key=value, --config key=value`` - Override configuration values (can be used multiple times)
- ``-f {json}, --format {json}`` - Generate additional output format

Full Help Output
~~~~~~~~~~~~~~~~

.. code-block:: text

    usage: gitstats [-h] [-v] [-c key=value] [-f {json}] <gitpath> <outputpath>

    Generate statistics for a Git repository.

    positional arguments:
      <gitpath>             Path(s) to the Git repository.
      <outputpath>          Path to the directory where the output will be stored.

    options:
      -h, --help            show this help message and exit
      -v, --version         show program's version number and exit
      -c key=value, --config key=value
                            Override configuration value. Can be specified multiple
                            times. See configuration documentation for available options.
      -f {json}, --format {json}
                            Generate additional output format.

Examples
--------

Generate report for current directory:

.. code-block:: bash

    gitstats . my-report

Generate report for specific repository:

.. code-block:: bash

    gitstats /path/to/repo output-folder

Generate report with JSON output:

.. code-block:: bash

    gitstats . report --format json

Override configuration values:

.. code-block:: bash

    gitstats . report -c max_authors=10 -c authors_top=3

For more configuration options, see the :doc:`configuration` page.
