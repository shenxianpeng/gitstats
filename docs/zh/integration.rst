集成
====

将 gitstats 与 CI/CD 工具集成使用。

在 GitHub Actions 中使用 gitstats
----------------------------------

如果你想在 GitHub Actions 或 Jenkins 等 CI 工具中使用 gitstats 来生成报告并部署，请参考以下示例。

在 GitHub Actions 中使用 gitstats 生成报告并部署到 GitHub Pages。

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
        - cron: '0 0 * * 0'  # 每周日 00:00 运行

    jobs:
      build:
        runs-on: ubuntu-latest

        steps:
        - name: Checkout Repository
          uses: actions/checkout@v4
          with:
            fetch-depth: 0 # 获取全部历史记录

        - name: Generate GitStats Report
          run: |
            pipx install gitstats
            gitstats . gitstats-report

        - name: Deploy to GitHub Pages for view
          uses: peaceiris/actions-gh-pages@v4
          with:
            github_token: ${{ secrets.GITHUB_TOKEN }}
            publish_dir: gitstats-report


在 Jenkins 中使用 gitstats
---------------------------

在 Jenkins 中使用 gitstats 生成报告并发布到 Jenkins 服务器。

.. code-block:: groovy

    pipeline {
        agent any
        options {
            cron('0 0 * * 0')  // 每周日 00:00 运行
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
