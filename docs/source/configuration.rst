
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
* ``end_date`` - Ending date for commits, passed as --until to Git (optional). Format: ``YYYY-MM-DD``. Default: ``""`` (empty).
* ``authors`` - Comma-separated list of authors to filter commits. Only commits from these authors will be included (uses OR logic: commits from any of the listed authors). If empty, all authors are included. Default: ``""`` (empty).
* ``commit_message_grep`` - Search expression to filter commits by commit message. Only commits matching this pattern will be included. Supports regex patterns as per Git's --grep option. If empty, all commits are included. Default: ``""`` (empty).
* ``exclude_exts`` - Comma-separated list of file extensions to exclude from line counting. If empty, no files are excluded. Files with null bytes in their content are automatically detected as binary and excluded from line counting. This detection occurs in addition to any extensions specified in exclude_exts. Default: ``""`` (empty).

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
   end_date =
   authors =
   commit_message_grep =
   exclude_exts = png,jpg,bin,exe,dll,class,jar,zip,tar

You can also override configuration values using the ``-c key=value`` option when running the ``gitstats`` command.

For example:

.. code-block:: bash

   gitstats . report -c max_authors=10 -c authors_top=3

This command will generate a report with a maximum of 10 authors displayed and the top 3 authors shown.

Filtering examples:

.. code-block:: bash

   # Filter commits by date range
   gitstats . report -c start_date=2024-01-01 -c end_date=2024-12-31

   # Filter commits by specific authors
   gitstats . report -c authors="John Doe,Jane Smith"

   # Filter commits by commit message pattern
   gitstats . report -c commit_message_grep="bug fix"

   # Filter commits matching any pattern (OR logic)
   gitstats . report -c commit_message_grep="sec|SQL|SQLi"

   # Filter commits matching ALL patterns (AND logic)
   gitstats . report -c commit_message_grep="sec&SQLi"

   # Combine multiple filters
   gitstats . report -c start_date=2024-01-01 -c authors="John Doe" -c commit_message_grep="feature"
