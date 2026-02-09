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

|pypi-version| |python-versions| |python-download| |test-badge| |docs-badge| |contributors|

``$ gitstats``
===============

📊 Generate insightful visual reports from Git.

📘 Documentation: `gitstats.readthedocs.io <https://gitstats.readthedocs.io/>`_

Example
-------

``gitstats . report`` generates this `gitstats report <https://shenxianpeng.github.io/gitstats/index.html>`_.

Installation
------------

.. code-block:: bash

   pip install gitstats


gitstats is compatible with Python 3.9 and newer.


Usage
-----

.. code-block:: bash

   gitstats <gitpath> <outputpath>


Run ``gitstats --help`` for more options, or check the `documentation <https://gitstats.readthedocs.io/en/latest/getting-started.html>`_.


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

GitStats now supports AI-powered insights to enhance your repository analysis. Get detailed, natural language summaries and actionable recommendations on:

* **Project Overview**: Comprehensive analysis of development history and project health
* **Activity Patterns**: Insights into commit frequency, peak periods, and development rhythm
* **Team Collaboration**: Analysis of contribution distribution and potential knowledge silos
* **Code Evolution**: Understanding of codebase growth patterns and maintenance burden

**Supported AI Providers:**

* OpenAI (GPT-4, GPT-3.5)
* Anthropic Claude
* Google Gemini
* Ollama (local LLMs)
* GitHub Copilot (experimental / limited support)

**Installation with AI Support:**

.. code-block:: bash

   pip install gitstats[ai]

**Basic Usage:**

.. code-block:: bash

   # Enable AI with OpenAI
   export OPENAI_API_KEY=your-api-key
   gitstats --ai --ai-provider openai <gitpath> <outputpath>

   # Use local LLM with Ollama
   gitstats --ai --ai-provider ollama --ai-model llama2 <gitpath> <outputpath>

   # Generate Chinese summaries
   gitstats --ai --ai-language zh <gitpath> <outputpath>

**Configuration:**

Add these options to ``gitstats.conf``:

.. code-block:: ini

   [gitstats]
   ai_enabled = true
   ai_provider = openai
   ai_model = gpt-4
   ai_language = en
   ai_cache_enabled = true

See the `AI Integration Documentation <https://gitstats.readthedocs.io/>`_ for detailed setup instructions for each AI provider.

.. end-of-about

Contributing
------------

As an open source project, gitstats welcomes contributions of all forms.

----

The gitstats project was originally created by `Heikki Hokkainen <https://github.com/hoxu>`_ and is currently maintained by `Xianpeng Shen <https://github.com/shenxianpeng>`_.
