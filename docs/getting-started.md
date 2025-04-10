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
