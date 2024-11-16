# GitStats - git history statistics generator

**gitstats** is a statistics generator for git repositories. It examines the repository and produces some interesting statistics from the history of it.

It is mostly intended for developers, as a way to check some development statistics for a project.

Currently it produces only HTML output with tables and graphs.

> [!NOTE]
> This project is a fork of [gitstats](https://github.com/hoxu/gitstats), which only supports Python 2.7 and is no longer maintained.
>
> I forked the project to update it for compatibility with Python 3.9+ and to introduce new features.

Features
========

Here is a list of some statistics generated currently:

* General statistics: total files, lines, commits, authors.
* Activity: commits by hour of day, day of week, hour of week, month of year, year and month, and year.
* Authors: list of authors (name, commits (%), first commit date, last commit date, age), author of month, author of year.
* Files: file count by date, extensions
* Lines: Lines of Code by date

Requirements
============
- Python 3.9+
- Gnuplot (http://www.gnuplot.info/)

Usage
=====

    ./gitstats --help

    Usage: gitstats [options] <gitpath..> <outputpath>

    Options:
    -c key=value     Override configuration value

    Default config values:
    {'max_domains': 10, 'max_ext_length': 10, 'style': 'gitstats.css', 'max_authors': 20, 'authors_top': 5, 'commit_begin': '', 'commit_end': 'HEAD', 'linear_linestats': 1, 'project_name': '', 'processes': 8, 'start_date': ''}

    Please see the manual page for more details.

Examples
--------

    ./gitstats ../gitstats ~/public_html

The output will be generated in the given directory.

License
=======

Both the code and the web site are licensed under GPLv2/GPLv3.
