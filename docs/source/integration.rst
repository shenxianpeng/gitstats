Integration
===========

Generate gitstats reports in CI (GitHub Actions, GitLab CI, Bitbucket
Pipelines, Jenkins) and publish them, then link them from your README with a
badge.

Fetch the full history first
----------------------------

CI checkouts are shallow by default, so gitstats would only see the last few
commits: ``actions/checkout`` fetches 1, GitLab CI 20 and Bitbucket Pipelines
50. Every example below turns that off:

- GitHub Actions: ``fetch-depth: 0`` on ``actions/checkout``
- GitLab CI: ``GIT_DEPTH: 0`` in the job's ``variables``
- Bitbucket Pipelines: ``clone: depth: full`` on the step
- Jenkins: leave the checkout's *shallow clone* option off (the default)

gitstats warns when it runs on a shallow clone, and the report says so under
its heading. To repair an existing checkout, run ``git fetch --unshallow``.

Use gitstats in GitHub Actions
------------------------------

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

        - name: Generate GitStats Report
          run: |
            pipx install gitstats
            gitstats . gitstats-report

        - name: Deploy to GitHub Pages for view
          uses: peaceiris/actions-gh-pages@v4
          with:
            github_token: ${{ secrets.GITHUB_TOKEN }}
            publish_dir: gitstats-report


Use gitstats in GitLab CI
-------------------------

Use gitstats in GitLab CI to generate reports and publish them to GitLab Pages.
A job named ``pages`` whose artifacts contain a ``public/`` folder is all GitLab
Pages needs, so the report is served at ``https://<group>.gitlab.io/<project>/``.

.. code-block:: yaml

    pages:
      image: python:3.12
      rules:
        - if: $CI_PIPELINE_SOURCE == "schedule"
        - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
      variables:
        GIT_DEPTH: 0          # fetch all history
      script:
        - pip install gitstats
        - gitstats . public   # public/ is what GitLab Pages serves
      artifacts:
        paths:
          - public

Schedule a weekly run via **Build → Pipeline schedules** in your GitLab project
(e.g., ``0 0 * * 0`` for every Sunday at 00:00).

Use gitstats in Bitbucket Pipelines
-----------------------------------

Bitbucket has no Pages feature and shows HTML files as source, so publish the
report folder to a static host you already have: an S3 bucket, an internal
nginx, Netlify and so on. Put your upload command in the last line.

.. code-block:: yaml

    pipelines:
      branches:
        main:
          - step:
              name: GitStats report
              image: python:3.12
              clone:
                depth: full   # fetch all history
              script:
                - pip install gitstats
                - gitstats . gitstats-report
                - aws s3 sync gitstats-report "s3://<bucket>/<repo>/"   # or your host

Run it on a schedule via **Repository settings → Pipelines → Schedules**.

Use gitstats in Jenkins
-----------------------

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

Jenkins does not run the scripts of the files it publishes by default, so the
report's charts are missing until it is set up to: see :ref:`blank-charts`.

.. _blank-charts:

If the charts are blank
-----------------------

The report draws its charts in the browser, with JavaScript, and sets parts of
its layout with inline styles. Where the server the report is on forbids
those, its numbers and tables are all there but its charts are not: each
chart's place says "Chart not shown", or is left empty in a report made by an
older gitstats.

Jenkins is the usual case. It sends the files that builds publish (HTML
Publisher reports, archived artifacts, the workspace) with a
``Content-Security-Policy`` header that allows no JavaScript and no inline
styles, so that a build cannot run scripts in the browser of the people who
open its files. Besides the charts, the tiles at the top of a page then leave
a grey gap, every share bar is full width, tables do not sort and the theme
switch does nothing.

To check that this is the cause, open the browser's developer console on the
report: it lists the scripts and styles that were blocked. The same report
opened from disk, or from another host, shows its charts.

There are three ways to get them back, safest first:

1. **Publish the report somewhere else**, as the other examples on this page
   do (GitHub Pages, GitLab Pages, an S3 bucket), and link to it from the job.
2. **Set a Resource Root URL**, in *Manage Jenkins → System → Serve resource
   files from another domain*. Jenkins then serves the published files from
   that second host name, without the header. This is what `Jenkins recommends
   <https://www.jenkins.io/doc/book/security/user-content/>`_.
3. **Relax the policy** with the ``hudson.model.DirectoryBrowserSupport.CSP``
   system property. This value is enough for a gitstats report:

   .. code-block:: text

       sandbox allow-scripts; default-src 'none'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline';

   Pass it when Jenkins starts, as
   ``-Dhudson.model.DirectoryBrowserSupport.CSP="<value>"``, or try it first in
   the Script Console, where it lasts until Jenkins restarts:

   .. code-block:: groovy

       System.setProperty("hudson.model.DirectoryBrowserSupport.CSP", "sandbox allow-scripts; default-src 'none'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline';")

   It applies to every file Jenkins serves, not only to this report: the
   scripts of any HTML a build publishes will run. Read `Configuring Content
   Security Policy
   <https://www.jenkins.io/doc/book/security/configuring-content-security-policy/>`_
   before changing it.

Add a report badge to your README
---------------------------------

Every generated report includes a ``badge.svg`` next to ``index.html`` — a
shields.io-style badge in the gitstats brand colors showing live repository
data (commit count by default). It is served from the same place as the
report and refreshes automatically on every regeneration, so once the report
is deployed (GitHub Pages, GitLab Pages, Jenkins, any static hosting) you
can embed:

.. code-block:: markdown

   [![GitStats](https://<your-report-url>/badge.svg)](https://<your-report-url>/)

Or open the report's **Badges** page: it shows every badge in every style
with a Copy button for a Markdown, reStructuredText or HTML snippet that
already points at the report. It reads the report's address from its own
URL; pass ``--site-url https://<your-report-url>/`` when generating the report
to fill it in for copies opened from a file, and to print the README badge
in the CI job log.

The report also contains a ``badges/`` directory with one pre-rendered badge
per metric (``commits``, ``last-commit``, ``authors``, ``files``,
``lines``, ``release``, ``active-days``), plus ``summary`` (commits, authors
and lines in one badge), ``activity`` (a sparkline of commits per month) and
``health`` (active, quiet or dormant by the age of the last commit) — pick
one by pointing at ``badges/<name>.svg``, or at ``badges/<style>/<name>.svg``
for a fixed style. The ``badge_metric``,
``badge_label``, ``badge_color`` and ``badge_style`` config keys choose the
default badge, its label, color and style (``flat``, ``flat-square``,
``terminal``, ``for-the-badge`` or ``light``), and ``badges/<name>.json``
exposes each badge in the
`shields.io endpoint schema <https://shields.io/badges/endpoint-badge>`_ for
full URL-parameter customization via ``img.shields.io/endpoint``. See the
README's "Share Your Report with a Badge" section for details.

For GitHub projects using the `GitStats Action
<https://github.com/marketplace/actions/gitstats-action>`_ with
``deploy-to-pages: true``, the workflow's job summary prints ready-to-copy
badge markdown pointing at your GitHub Pages report.

Badges on GitLab
~~~~~~~~~~~~~~~~

With the ``pages`` job above, embed the badge in the README:

.. code-block:: markdown

   [![GitStats](https://<group>.gitlab.io/<project>/badge.svg)](https://<group>.gitlab.io/<project>/)

GitLab can also show it at the top of the project page, above the README:
**Settings → General → Badges**. Add it once on a *group* and every project in
the group gets it, using GitLab's placeholders. For private projects on a
self-managed instance, serving the badge from the job artifacts keeps GitLab's
own sign-in, so members see it and nobody else does:

- Link: ``https://<gitlab-host>/%{project_path}/-/jobs/artifacts/%{default_branch}/file/public/index.html?job=pages``
- Badge image: ``https://<gitlab-host>/%{project_path}/-/jobs/artifacts/%{default_branch}/raw/public/badge.svg?job=pages``

Opening an HTML artifact in the browser needs GitLab Pages to be enabled on
the instance.

Badges on Bitbucket
~~~~~~~~~~~~~~~~~~~

Point the badge at the static host the pipeline publishes to:

.. code-block:: markdown

   [![GitStats](https://reports.example.com/<repo>/badge.svg)](https://reports.example.com/<repo>/)

Without a web host for the report, the badge alone can live in the
repository: have the pipeline commit ``badge.svg`` to a ``gitstats`` branch and
use its raw URL, ``https://bitbucket.org/<workspace>/<repo>/raw/gitstats/badge.svg``
on Bitbucket Cloud or
``https://<bitbucket-host>/projects/<KEY>/repos/<repo>/raw/badge.svg?at=refs/heads/gitstats``
on Bitbucket Data Center.
