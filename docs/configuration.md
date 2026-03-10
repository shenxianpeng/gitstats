# Configuration

You can create a `gitstats.conf` file in the current directory to customize the configuration.

| Key | Description | Default |
|-----|-------------|---------|
| `max_domains` | Maximum number of domains to display in "Domains by Commits" | `10` |
| `max_ext_length` | Maximum length of file extensions shown in statistics | `10` |
| `style` | CSS stylesheet for the generated report | `gitstats.css` |
| `max_authors` | Maximum number of authors to list in "Authors" | `20` |
| `authors_top` | Number of top authors to highlight | `5` |
| `commit_begin` | Start of commit range (empty = include all commits). E.g. `10` for last 10 commits | `""` |
| `commit_end` | End of commit range | `HEAD` |
| `linear_linestats` | Enable linear history for line statistics (`1` = enabled, `0` = disabled) | `1` |
| `project_name` | Project name to display (default: repository directory name) | `""` |
| `processes` | Number of parallel processes to use when gathering data | `8` |
| `start_date` | Starting date for commits, passed as `--since` to Git. Format: `YYYY-MM-DD` | `""` |
| `end_date` | Ending date for commits, passed as `--until` to Git. Format: `YYYY-MM-DD` | `""` |
| `authors` | Comma-separated list of authors to filter commits (OR logic). If empty, all authors are included | `""` |
| `exclude_exts` | Comma-separated file extensions to exclude from line counting. Files with null bytes are auto-detected as binary and also excluded | `""` |

## Example Configuration File

```ini
[gitstats]
max_domains = 10
max_ext_length = 10
style = gitstats.css
max_authors = 20
authors_top = 5
commit_begin = 10
commit_end = HEAD
linear_linestats = 1
project_name =
processes = 8
start_date =
end_date =
authors =
exclude_exts = png,jpg,bin,exe,dll,class,jar,zip,tar
```

## CLI Overrides

You can also override configuration values using the `-c key=value` option:

```bash
gitstats . report -c max_authors=10 -c authors_top=3
```

## Filtering Examples

```bash
# Filter commits by date range
gitstats . report -c start_date=2024-01-01 -c end_date=2024-12-31

# Filter commits by specific authors
gitstats . report -c authors="John Doe,Jane Smith"

# Combine multiple filters
gitstats . report -c start_date=2024-01-01 -c authors="John Doe"
```
