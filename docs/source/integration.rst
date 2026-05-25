Integration
===========

Use gitstats integration with CI/CD tools.

Use gitstats in GitHub Actions
------------------------------

If you want to use gitstats with CI like GitHub Actions, GitLab CI, or Jenkins to generate reports and deploy them, see the following examples.

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

.. code-block:: yaml

    gitstats-report:
      image: python:3.12
      stage: report
      rules:
        - if: $CI_PIPELINE_SOURCE == "schedule"
        - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
      variables:
        GIT_DEPTH: 0          # fetch all history
      before_script:
        - pip install gitstats
      script:
        - gitstats . public   # output to public/ for GitLab Pages
      artifacts:
        paths:
          - public
        expire_in: 30 days
      # Optional: deploy to GitLab Pages
      # GitLab Pages requires a 'pages' job with artifacts in public/

    # Uncomment the job below to publish to GitLab Pages automatically.
    # pages:
    #   stage: deploy
    #   needs: [gitstats-report]
    #   script:
    #     - mv public/index.html public/index.html  # artifact is already in public/
    #   artifacts:
    #     paths:
    #       - public

Schedule a weekly run via **Build → Pipeline schedules** in your GitLab project
(e.g., ``0 0 * * 0`` for every Sunday at 00:00).

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
