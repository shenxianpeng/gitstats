<div align="center">
  <img src="https://raw.githubusercontent.com/shenxianpeng/gitstats/main/docs/source/logo.png" alt="Project Logo" width="200px">
</div>

[![PyPI - Version](https://img.shields.io/pypi/v/gitstats?color=blue)](https://pypi.org/project/gitstats/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/gitstats)](https://pypi.org/project/gitstats/)
[![PyPI Downloads](https://static.pepy.tech/badge/gitstats/week)](https://pepy.tech/projects/gitstats)
[![Test](https://github.com/shenxianpeng/gitstats/actions/workflows/test.yml/badge.svg)](https://github.com/shenxianpeng/gitstats/actions/workflows/test.yml)
[![Docs](https://img.shields.io/badge/docs-mkdocs--material-blue)](https://shenxianpeng.github.io/gitstats/docs/)
[![GitHub contributors](https://img.shields.io/github/contributors/shenxianpeng/gitstats)](https://github.com/shenxianpeng/gitstats/graphs/contributors)

**English** | [中文](README.zh.md)

# `$ gitstats`

📊 Generate insightful visual reports from Git.

📘 Documentation: [shenxianpeng.github.io/gitstats/docs](https://shenxianpeng.github.io/gitstats/docs/)

## Example

`gitstats . report` generates this [gitstats report](https://shenxianpeng.github.io/gitstats/report/index.html).

## Installation

```bash
pip install gitstats
```

gitstats is compatible with Python 3.9 and newer.

## Usage

```bash
gitstats <gitpath> <outputpath>
```

Run `gitstats --help` for more options, or check the [documentation](https://shenxianpeng.github.io/gitstats/docs/).

## What's New in v2.0.0

v2.0.0 is a major release focused on modernizing the report UI and removing the Gnuplot dependency.

**Terminal-inspired UI redesign**

The entire report interface has been redesigned with a terminal / OpenCode-inspired aesthetic:
zero border-radius (sharp, angular corners), monospace fonts in headings and navigation,
border-heavy layout, and a GitHub-style green heatmap. Both light and dark modes are supported
with a one-click toggle — no flash of unstyled content when switching pages.

**Chart.js replaces Gnuplot**

All charts are now rendered interactively in the browser using [Chart.js](https://www.chartjs.org/).
Gnuplot is no longer required. Reports are fully self-contained HTML files.

## Features

Here is a list of some features of `gitstats`:

- **General**: total files, lines, commits, authors, age.
- **Activity**: commits by hour of day, day of week, hour of week, month of year, year and month, and year.
- **Authors**: list of authors (name, commits (%), first commit date, last commit date, age), author of month, author of year.
- **Files**: file count by date, extensions.
- **Lines**: line of code by date.
- **Tags**: tags by date and author.
- **Customizable**: config values through `gitstats.conf`.
- **Cross-platform**: works on Linux, Windows, and macOS.

## AI-Powered Features 🤖

GitStats supports AI-powered insights to enhance your repository analysis with natural language summaries and actionable recommendations.

**Quick Start:**

```bash
# Install with AI support
pip install gitstats[ai]

# Enable AI with OpenAI
export OPENAI_API_KEY=your-api-key
gitstats --ai --ai-provider openai <gitpath> <outputpath>
```

For detailed setup instructions, configuration options, and examples, see the [AI Integration Documentation](https://shenxianpeng.github.io/gitstats/docs/ai-integration/).

## Contributing

As an open source project, gitstats welcomes contributions of all forms.

---

The gitstats project was originally created by [Heikki Hokkanen](https://github.com/hoxu) and is currently maintained by [Xianpeng Shen](https://github.com/shenxianpeng).
