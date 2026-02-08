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
    "end_date": "",  # Ending date for commits, passed as --until to Git (optional). Format: YYYY-MM-DD.
    "authors": "",  # Comma-separated list of authors to filter commits (empty = include all authors).
    "exclude_exts": "",  # File extensions to exclude from line counting (others detected via null bytes).
    # AI-powered features
    "ai_enabled": False,  # Enable AI-powered summaries (requires AI provider configuration).
    "ai_provider": "openai",  # AI provider: openai, claude, gemini, ollama, copilot.
    "ai_api_key": "",  # API key for AI provider (can also use environment variables).
    "ai_model": "",  # AI model to use (e.g., gpt-4, claude-3-5-sonnet-20241022, gemini-pro, llama2).
    "ai_language": "en",  # Language for AI-generated summaries (en, zh, zh-CN, ja, ko, es, fr, de, etc.).
    "ai_cache_enabled": True,  # Cache AI-generated summaries to save API costs.
    "ai_max_retries": 3,  # Maximum retry attempts for AI API calls.
    "ai_retry_delay": 1,  # Delay in seconds between retries.
    "ollama_base_url": "http://localhost:11434",  # Base URL for Ollama local LLM.
}


_config = None


def load_config(file_path="gitstats.conf") -> dict:
    """Load configuration from a file, or fall back to defaults."""
    import configparser
    import os

    global _config

    if _config is not None:
        return _config

    _config = DEFAULT_CONFIG.copy()  # Start with defaults
    config_parser = configparser.ConfigParser()

    if os.path.exists(file_path):
        config_parser.read(file_path)
        for k, v in config_parser["gitstats"].items():
            # Convert to appropriate type
            if v.isdigit():
                _config[k] = int(v)
            elif v.lower() in ('true', 'false'):
                _config[k] = v.lower() == 'true'
            else:
                _config[k] = v
    return _config
