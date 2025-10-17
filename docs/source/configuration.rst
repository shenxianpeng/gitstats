
Configuration
=============

You can create a ``gitstats.conf`` file in the current directory to customize the configuration.

* ``max_domains`` - Maximum number of domains to display in "Domains by Commits". Default: ``10``.
* ``max_ext_length`` - Maximum length of file extensions shown in statistics. Default: ``10``.
* ``style`` - CSS stylesheet for the generated report. Default: ``gitstats.css``.
* ``max_authors`` - Maximum number of authors to list in "Authors". Default: ``20``.
* ``authors_top`` - Number of top authors to highlight. Default: ``5``.
* ``commit_begin`` - Start of commit range (empty = include all commits). For example, ``10`` for last 10 commits. Default: ``""`` (empty).
* ``commit_end`` - End of commit range. Default: ``HEAD``.
* ``linear_linestats`` - Enable linear history for line statistics (``1`` = enabled, ``0`` = disabled). Default: ``1``.
* ``project_name`` - Project name to display (default: repository directory name). Default: ``""`` (empty).
* ``processes`` - Number of parallel processes to use when gathering data. Default: ``8``.
* ``start_date`` - Starting date for commits, passed as --since to Git (optional). Format: ``YYYY-MM-DD``. Default: ``""`` (empty).

Here is an example ``gitstats.conf`` file:

.. code-block:: ini

   [gitstats]
   max_domains = 10
   max_ext_length = 10
   style = gitstats.css
   max_authors = 20
   authors_top = 5
   commit_begin = 10
   commit_end = HEAD
   linear_linestats = 1
   project_name =
   processes = 8
   start_date =

You can also override configuration values using the ``-c key=value`` option when running the ``gitstats`` command.

For example:

.. code-block:: bash

   gitstats . report -c max_authors=10 -c authors_top=3

This command will generate a report with a maximum of 10 authors displayed and the top 3 authors shown.
