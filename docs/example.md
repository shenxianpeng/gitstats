# Examples

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
