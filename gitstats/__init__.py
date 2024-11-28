DEFAULT_CONFIG = {
    "max_domains": 10,
    "max_ext_length": 10,
    "style": "gitstats.css",
    "max_authors": 20,
    "authors_top": 5,
    "commit_begin": "",
    "commit_end": "HEAD",
    "linear_linestats": 1,
    "project_name": "",
    "processes": 8,
    "start_date": "",
}


def load_config(file_path="gitstats.conf"):
    """Load configuration from a file, or fall back to defaults."""
    import configparser
    import os

    config = DEFAULT_CONFIG.copy()  # Start with defaults
    config_parser = configparser.ConfigParser()

    if os.path.exists(file_path):
        config_parser.read(file_path)
        config = {
            k: int(v) if v.isdigit() else v
            for k, v in config_parser["gitstats"].items()
        }
    return config
