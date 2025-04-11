
Example
=======

Usage
-----

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

Example
-------

Run ``gitstats . report`` to generate a report like this: https://shenxianpeng.github.io/gitstats/index.html.

.. tip::
   Before running ``gitstats``, ensure all required dependencies are installed.
   See `Installation <#installation>`_ and `Requirements <#requirements>`_.
   The ``.`` refers to the current directory, or you can specify any other ``gitpath`` as needed.
   See `Usage <#usage>`_.

Run ``gitstats . report --format json`` to generate the same report along with a JSON file.

.. tip::
   You can use `jq <https://jqlang.github.io/jq/>`_ to parse the JSON file.
   For example: ``cat report.json | jq .`` — this allows you to extract any data you need.

📈 More examples: `Jenkins project example <https://shenxianpeng.github.io/gitstats/examples/jenkins/index.html>`_: A report showcasing data from the Jenkins project.


CI Workflow Example
-------------------

If you want to use gitstats with CI like GitHub Actions or Jenkins to generate reports and deploy them, please the following examples.

Use gitstats in GitHub Actions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Use gitstats in GitHub Actions to generate reports and deploy them to GitHub Pages.

.. code-block:: yaml

    name: GitStats

    on:
      push:
        branches:
          - main
      pull_request:
        branches:
          - main
      schedule:
        - cron: '0 0 * * 0'  # Run at every sunday at 00:00

    jobs:
      build:
        runs-on: ubuntu-latest

        steps:
        - name: Checkout Repository
          uses: actions/checkout@v4
          with:
            fetch-depth: 0 # get all history.

        - name: Install Dependencies
          run: |
            sudo apt-get update
            sudo apt-get install -y gnuplot

        - name: Generate GitStats Report
          run: |
            pipx install gitstats
            gitstats . gitstats-report

        - name: Deploy to GitHub Pages for view
          uses: peaceiris/actions-gh-pages@v4
          with:
            github_token: ${{ secrets.GITHUB_TOKEN }}
            publish_dir: gitstats-report


Use gitstats in Jenkins
^^^^^^^^^^^^^^^^^^^^^^^

Use gitstats in Jenkins to generate reports and publish them to Jenkins server.

.. code-block:: groovy

    pipeline {
        agent any
        options {
            cron('0 0 * * 0')  // Run at every sunday at 00:00
        }
        stages {
            stage('Generate GitStats Report') {
                steps {
                    checkout scm
                    sh '''
                    python3 -m venv venv
                    source venv/bin/activate
                    pip install gitstats
                    gitstats . gitstats-report
                    '''
                }
            }
            stage('Publish GitStats Report') {
                steps {
                    publishHTML([allowMissing: false, alwaysLinkToLastBuild: true, keepAll: true, reportDir: 'gitstats-report', reportFiles: 'index.html', reportName: 'GitStats Report'])
                }
            }
        }
        post {
            always {
                cleanWs()
            }
        }
    }
