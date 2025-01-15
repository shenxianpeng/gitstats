# GitStats 📊

Visualize Your Git Repositories.

<!--[![PyPI - Downloads](https://img.shields.io/pypi/dm/gitstats?color=blue)](https://pypistats.org/packages/gitstats)-->
[![GitStats Report](https://img.shields.io/badge/GitStats_Report-passing-lightgreen?style=flat&&logo=git&&logoColor=white)](https://shenxianpeng.github.io/gitstats/index.html)
[![Test](https://github.com/shenxianpeng/gitstats/actions/workflows/test.yml/badge.svg)](https://github.com/shenxianpeng/gitstats/actions/workflows/test.yml)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=shenxianpeng_gitstats&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=shenxianpeng_gitstats)
[![PyPI - Version](https://img.shields.io/pypi/v/gitstats?color=blue)](https://pypi.org/project/gitstats/)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/gitstats)

## Example

Run `gitstats . report`[^1] to generate this report: https://shenxianpeng.github.io/gitstats/index.html

[^1]: Before running `gitstats`, ensure all required dependencies are installed on your system. See [requirements](#Requirements)

## Features

Here is a list of some features of _gitstats_:

* **General**: total files, lines, commits, authors, age.
* **Activity**: commits by hour of day, day of week, hour of week, month of year, year and month, and year.
* **Authors**: list of authors (name, commits (%), first commit date, last commit date, age), author of month, author of year.
* **Files**: file count by date, extensions.
* **Lines**: line of code by date.
* **Tags**: tags by date and author.
* **Customizable**: config values through `gitstats.conf`.
* **Cross-platform**: works on Linux, Windows, and macOS.

📈 More examples: [Jenkins project example](https://shenxianpeng.github.io/gitstats/examples/jenkins/index.html): A report showcasing data from the Jenkins project.

## Requirements

- Python 3.9+
- Gnuplot (http://www.gnuplot.info): You can install Gnuplot on
  - Ubuntu with `sudo apt install gnuplot`
  - macOS with `brew install gnuplot`
  - Windows with `choco install gnuplot`
- Git (http://git-scm.com/)

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

```bash
Usage: gitstats [options] <gitpath..> <outputpath>

Options:
-c key=value     Override configuration value

Default config values:
{'max_domains': 10, 'max_ext_length': 10, 'style': 'gitstats.css', 'max_authors': 20, 'authors_top': 5, 'commit_begin': '', 'commit_end': 'HEAD', 'linear_linestats': 1, 'project_name': '', 'processes': 8, 'start_date': ''}

Please see the manual page for more details.

```

> [!TIP]
> If you want to use gitstats with CI like GitHub Actions or Jenkins to generate reports and deploy them, please the following examples.

### Use gitstats in GitHub Actions

<details>
<summary>Example GitHub Actions</summary>

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
</details>

### Use gitstats in Jenkins

<details>
<summary>Example Jenkinsfile</summary>

Use gitstats in Jenkins to generate reports and publish them to Jenkins server.

```groovy
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
</details>

## FAQ

1. How do I generate statistics of a non-master branch?

    Use the `-c commit_end=web` parameter.

2. I have files in my git repository that I would like to exclude from the statistics. How do I do that?

    At the moment, the only way is to use [git-filter-branch(1)](https://git-scm.com/docs/git-filter-branch) to create a temporary repository and generate the statistics from that.

3. How do I merge author information when the same author has made commits using different names or emails?

    Use Git's `.mailmap` feature, as described in the **MAPPING AUTHORS** section of the [git-shortlog(1)](https://git-scm.com/docs/git-shortlog) documentation.

## Contributors

[![GitStats Report](https://contrib.rocks/image?repo=shenxianpeng/gitstats)](https://github.com/shenxianpeng/gitstats/graphs/contributors)

## License

Both the code and the web site are licensed under GPLv2/GPLv3.

---

The gitstats project was originally created by [H​eikki H​okkanen](https://github.com/hoxu) but is no longer maintained since 2015. It is now maintained by [Xianpeng Shen](https://github.com/shenxianpeng).
