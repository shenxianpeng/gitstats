.. start-of-about

GitStats
========

.. |pypi-version| image:: https://img.shields.io/pypi/v/gitstats?color=blue
   :target: https://pypi.org/project/gitstats/
   :alt: PyPI - Version

.. |python-versions| image:: https://img.shields.io/pypi/pyversions/gitstats
   :alt: PyPI - Python Version

.. |test-badge| image:: https://github.com/shenxianpeng/gitstats/actions/workflows/test.yml/badge.svg
   :target: https://github.com/shenxianpeng/gitstats/actions/workflows/test.yml
   :alt: Test

.. |sonarcloud| image:: https://sonarcloud.io/api/project_badges/measure?project=shenxianpeng_gitstats&metric=alert_status
   :target: https://sonarcloud.io/summary/new_code?id=shenxianpeng_gitstats
   :alt: Quality Gate Status

.. |docs-badge| image:: https://readthedocs.org/projects/gitstats/badge/?version=latest
   :target: https://gitstats.readthedocs.io/
   :alt: Documentation

|pypi-version| |python-versions| |test-badge| |sonarcloud| |docs-badge|

A tool for generating insightful visual reports from your Git repositories. 📊

📘 Documentation: `gitstats.readthedocs.io <https://gitstats.readthedocs.io/>`_

Example
-------

``gitstats . report`` generates this `gitstats report <https://shenxianpeng.github.io/gitstats/index.html>`_

Installation
------------

.. code-block:: bash

   pip install gitstats


gitstats is compatible with Python 3.9 and newer.


Usage
-----

.. code-block:: bash

   gitstats <gitpath> <outputpath>


Run ``gitstats --help`` for more options, or check the `documentation <https://gitstats.readthedocs.io/en/latest/usage.html>`_.


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

.. end-of-about

---

**gitstats** was originally created by `Heikki Hokkainen <https://github.com/hoxu>`_ and is now maintained by `Xianpeng Shen <https://github.com/shenxianpeng>`_.
