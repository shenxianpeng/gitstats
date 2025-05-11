Usage
=====

.. code-block::

    gitstats --help
    usage: gitstats [-h] [-v] [-c key=value] [-f {json}] <gitpath> [<gitpath> ...] <outputpath>

    Generate statistics for a Git repository.

    positional arguments:
    <gitpath>             Path(s) to the Git repository.
    <outputpath>          Path to the directory where the output will be stored.

    options:
    -h, --help            show this help message and exit
    -v, --version         show program's version number and exit
    -c key=value, --config key=value
                            Override configuration value. Can be specified multiple times. Default configuration: {'max_domains':
                            10, 'max_ext_length': 10, 'style': 'gitstats.css', 'max_authors': 20, 'authors_top': 5, 'commit_begin':
                            '', 'commit_end': 'HEAD', 'linear_linestats': 1, 'project_name': '', 'processes': 8, 'start_date': ''}.
    -f {json}, --format {json}
                            The extra format of the output file.


Run ``gitstats . report`` to generate a report like this: https://shenxianpeng.github.io/gitstats/index.html.

.. tip::
   Before running ``gitstats``, ensure all required dependencies are installed.
   See :doc:`installation`.
   The ``.`` refers to the current directory, or you can specify any other ``gitpath`` as needed.
   See `Usage <#usage>`_.

Run ``gitstats . report --format json`` to generate the same report along with a JSON file.

.. tip::
   You can use `jq <https://jqlang.github.io/jq/>`_ to parse the JSON file.
   For example: ``cat report.json | jq .`` — this allows you to extract any data you need.

..
   📈 More examples: `Jenkins project example <https://shenxianpeng.github.io/gitstats/examples/jenkins/index.html>`_: A report showcasing data from the Jenkins project.
