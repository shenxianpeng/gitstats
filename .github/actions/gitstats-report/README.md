# GitStats GitHub Action

Generate an HTML/JSON statistics report from a Git repository and upload it
as a workflow artifact — all within GitHub Actions.

---

## Quick Start

Add this to your repository's `.github/workflows/gitstats.yml`:

```yaml
name: GitStats Report

on:
  pull_request:
  push:
    branches: [main]

jobs:
  report:
    uses: shenxianpeng/gitstats/.github/workflows/gitstats-report.yml@main
    with:
      artifact-name: repo-stats
    secrets: inherit
```

On every push to `main` and every pull request, GitStats will:

1. Analyze the repository's Git history
2. Generate an interactive HTML report (with optional JSON output)
3. Upload the report as a workflow artifact
4. Post a summary comment on the pull request

---

## Usage

### Option 1 — Reusable Workflow (recommended)

Call the reusable workflow from your own workflow file. The workflow handles
everything: report generation, artifact upload, PR comments, and optional
GitHub Pages deployment.

```yaml
jobs:
  stats:
    uses: shenxianpeng/gitstats/.github/workflows/gitstats-report.yml@main
    with:
      # Path to the Git repository (default: '.')
      gitpath: '.'
      # Output directory (default: 'gitstats-report')
      outputpath: 'gitstats-report'
      # Python version (default: '3.12')
      python-version: '3.12'
      # Additional format: 'json' or 'none' (default: 'json')
      format: 'json'
      # Artifact name (default: 'gitstats-report')
      artifact-name: 'my-project-stats'
      # Artifact retention days (default: 30)
      retention-days: '90'
      # Extra config overrides (comma-separated key=value)
      config: 'max_authors=30,authors_top=10'
      # Enable debug logging
      verbose: false
      # Post PR comment (default: true)
      comment-on-pr: true
      # Deploy to GitHub Pages (default: false)
      deploy-pages: false
      # Pages subdirectory (empty = root)
      pages-destination-dir: 'stats'
    secrets: inherit
```

### Option 2 — Composite Action

Use the action directly as a composite step. This gives you full control over
the surrounding workflow. Note: PR commenting and Pages deployment are **not**
included — you must add those steps yourself.

```yaml
jobs:
  stats:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0

      - name: Generate GitStats Report
        uses: shenxianpeng/gitstats/.github/actions/gitstats-report@main
        with:
          gitpath: '.'
          outputpath: 'gitstats-report'
          python-version: '3.12'
          format: 'json'
          artifact-name: gitstats-report
          retention-days: 30

      # Add your own PR comment or Pages deploy steps here
```

### Option 3 — Manual (pip install)

If you don't want to use the action at all, just install gitstats directly:

```yaml
jobs:
  stats:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v6
        with:
          python-version: '3.12'

      - run: pip install gitstats

      - run: gitstats . gitstats-report -f json

      - uses: actions/upload-artifact@v7
        with:
          name: gitstats-report
          path: gitstats-report
```

---

## Inputs

### Composite Action (`action.yml`)

| Input | Default | Description |
|-------|---------|-------------|
| `gitpath` | `.` | Path to the Git repository to analyze |
| `outputpath` | `gitstats-report` | Output directory for the report |
| `python-version` | `3.12` | Python version used to run gitstats |
| `format` | `json` | Additional output format (`json` or `none`) |
| `artifact-name` | `gitstats-report` | Name for the uploaded artifact |
| `upload-artifact` | `true` | Whether to upload the report as an artifact |
| `retention-days` | `30` | Days to retain the uploaded artifact |
| `config` | `''` | Extra config overrides (comma-separated `key=value`) |
| `verbose` | `false` | Enable debug-level logging |

### Reusable Workflow (`workflow.yml`)

All composite action inputs plus:

| Input | Default | Description |
|-------|---------|-------------|
| `comment-on-pr` | `true` | Post a stats summary comment on PRs |
| `deploy-pages` | `false` | Deploy the report to GitHub Pages |
| `pages-destination-dir` | `''` | Subdirectory under gh-pages root |

---

## Outputs

| Output | Description |
|--------|-------------|
| `artifact-url` | Download URL of the uploaded artifact |
| `artifact-id` | ID of the uploaded artifact |

---

## Example: Deploy to GitHub Pages

```yaml
name: Deploy GitStats to Pages

on:
  push:
    branches: [main]

jobs:
  deploy:
    uses: shenxianpeng/gitstats/.github/workflows/gitstats-report.yml@main
    with:
      deploy-pages: true
      pages-destination-dir: stats
    secrets: inherit
```

This will deploy the report to `https://<user>.github.io/<repo>/stats/`.

---

## PR Comment Example

When `comment-on-pr` is enabled, the bot posts a comment like:

> ## 📊 GitStats Report
>
> | Metric | Value |
> | ------ | ----- |
> | Total Commits | 1,234 |
> | Total Files | 567 |
> | Lines of Code | 89,012 |
> | Authors | 42 |
> | Longest Streak | 15 days |
>
> ### 🔝 Top Contributors
> | Author | Commits | Lines Added | Lines Removed |
> | ------ | ------- | ----------- | ------------- |
> | ... | ... | ... | ... |

The comment is updated (not duplicated) on each subsequent push.

---

## Permissions

The reusable workflow needs these permissions (set automatically):

```yaml
permissions:
  contents: read      # for checkout
  actions: read       # for artifact operations
  pull-requests: write  # for PR comments
  pages: write        # for Pages deployment
  id-token: write     # for Pages deployment
```

When calling the reusable workflow, use `secrets: inherit` to pass the
`GITHUB_TOKEN`.

---

## Configuration

To customize the report, pass config overrides via the `config` input:

```yaml
with:
  config: 'max_authors=50,authors_top=10,max_ext_length=15'
```

See [gitstats.conf](https://github.com/shenxianpeng/gitstats/blob/main/gitstats.conf)
for all available options.

---

## License

GPLv2 / GPLv3
