# gitstats

gitstats is a statistics generator for git repositories. It is mostly intended
for developers, as a way to check some development statistics for a project.

Currently it produces only HTML output with tables and graphs.

> [!NOTE]
> This project is a fork of [gitstats](https://github.com/hoxu/gitstats), which only supports Python 2.7 and is no longer maintained.
>
> I forked the project to update it for compatibility with Python 3.9+ and to introduce new features.

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

Contributions
=============
Patches should be sent under "GPLv2 or later" license - this will allow
upgrading to newer GPL versions if they are sensible.
