# Get Started

## Requirements

- Python 3.9+ (https://www.python.org/downloads/)
- Git (http://git-scm.com/)
- Gnuplot (http://www.gnuplot.info): You can install Gnuplot on
  - Ubuntu with `sudo apt install gnuplot`
  - macOS with `brew install gnuplot`
  - Windows with `choco install gnuplot`

## Installation

### Install from PyPI

```bash
pip install gitstats
```

### Install from Docker

You can also get gitstats docker image.

```bash
docker run ghcr.io/shenxianpeng/gitstats:latest --help
```

## Usage

```
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
```

## Example

Run `gitstats . report` to generate a report like this: https://shenxianpeng.github.io/gitstats/index.html.

> [!TIP]
> Before running `gitstats`, ensure all required dependencies are installed. See [Installation](#Installation) and [Requirements](#Requirements). The `.` refers the current directory, or you can specify any other `gitpath` as needed. See [Usage](#Usage).

Run `gitstats . report --format json` to generate the same report along with a JSON file.

> [!TIP]
> You can use [jq](https://jqlang.github.io/jq/) to parse the JSON file. For example: `cat report.json | jq .`, this allows you to extract any data you need.

📈 More examples: [Jenkins project example](https://shenxianpeng.github.io/gitstats/examples/jenkins/index.html): A report showcasing data from the Jenkins project.

## CI Workflow Example

If you want to use gitstats with CI like GitHub Actions or Jenkins to generate reports and deploy them, please the following examples.

## Use gitstats in GitHub Actions

Use gitstats in GitHub Actions to generate reports and deploy them to GitHub Pages.

```yaml
name: GitStats Preview

on:
  cron:
    - cron: '0 0 * * 0'  # Run at every sunday at 00:00
  workflow_dispatch:

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
```

## Use gitstats in Jenkins

Use gitstats in Jenkins to generate reports and publish them to Jenkins server.

```groovy
// Example Jenkinsfile
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
```
