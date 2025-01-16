# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
import platform
import time

exectime_internal = 0.0
exectime_external = 0.0
time_start = time.time()

GNUPLOT_COMMON = "set terminal png transparent size 640,240\nset size 1.0,1.0\n"
ON_LINUX = platform.system() == "Linux"
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

DEFAULT_CONFIG = {
    "max_domains": 10,  # Maximum number of domains to display in "Domains by Commits".
    "max_ext_length": 10,  # Maximum length of file extensions shown in statistics.
    "style": "gitstats.css",  # CSS stylesheet for the generated report.
    "max_authors": 20,  # Maximum number of authors to list in "Authors".
    "authors_top": 5,  # Number of top authors to highlight.
    "commit_begin": "",  # Start of commit range (empty = include all commits).
    "commit_end": "HEAD",  # End of commit range (default: HEAD).
    "linear_linestats": 1,  # Enable linear history for line statistics (1 = enabled, 0 = disabled).
    "project_name": "",  # Project name to display (default: repository directory name).
    "processes": 8,  # Number of parallel processes to use when gathering data.
    "start_date": "",  # Starting date for commits, passed as --since to Git (optional).
}


def load_config(file_path="gitstats.conf") -> dict:
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
