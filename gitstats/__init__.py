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


# Internationalization translations for AI Insights page
AI_INSIGHTS_I18N = {
    "en": {
        "ai_insights_title": "AI-Powered Insights",
        "ai_insights_intro": "This page contains AI-generated analysis and insights based on your repository statistics. The analysis focuses on human contributions and excludes automated bot accounts.",
        "project_overview": "Project Overview",
        "project_overview_desc": "Comprehensive analysis of the repository's development history and overall health",
        "activity_patterns": "Activity Patterns",
        "activity_patterns_desc": "Insights into commit frequency, development rhythm, and temporal patterns",
        "team_collaboration": "Team Collaboration",
        "team_collaboration_desc": "Analysis of contributor dynamics, team diversity, and collaboration patterns",
        "code_evolution": "Code Evolution",
        "code_evolution_desc": "Understanding of codebase growth, code churn, and maintenance patterns",
        "analysis_unavailable": "Analysis Unavailable",
        "no_analysis": "No analysis available for this section.",
        "about_ai_insights": "About AI Insights",
        "ai_disclaimer": "These insights are generated using artificial intelligence based on repository statistics. While AI analysis can identify patterns and trends, it should be considered as supplementary information alongside your own understanding of the project.",
        "bot_note": "<strong>Note:</strong> Bot accounts (such as dependabot[bot], pre-commit-ci[bot], and other automated contributors) are automatically excluded from the analysis to focus on human team dynamics.",
    },
    "zh": {
        "ai_insights_title": "AI智能分析",
        "ai_insights_intro": "本页面包含基于代码仓库统计数据的 AI 生成分析和见解。分析专注于人类贡献者，排除了自动化机器人账户。",
        "project_overview": "项目概览",
        "project_overview_desc": "对仓库开发历史和整体健康状况的综合分析",
        "activity_patterns": "活跃模式",
        "activity_patterns_desc": "关于提交频率、开发节奏和时间模式的洞察",
        "team_collaboration": "团队协作",
        "team_collaboration_desc": "贡献者动态、团队多样性和协作模式的分析",
        "code_evolution": "代码演进",
        "code_evolution_desc": "代码库增长、代码变动和维护模式的理解",
        "analysis_unavailable": "分析不可用",
        "no_analysis": "此部分暂无可用分析。",
        "about_ai_insights": "关于 AI 洞察",
        "ai_disclaimer": "这些洞察是基于仓库统计数据使用人工智能生成的。虽然 AI 分析可以识别模式和趋势，但应将其视为补充信息，与您对项目的理解相结合。",
        "bot_note": "<strong>注意：</strong>机器人账户（如 dependabot[bot]、pre-commit-ci[bot] 和其他自动化贡献者）已自动从分析中排除，以专注于人类团队动态。",
    },
    "zh-CN": {
        "ai_insights_title": "AI智能分析",
        "ai_insights_intro": "本页面包含基于代码仓库统计数据的 AI 生成分析和见解。分析专注于人类贡献者，排除了自动化机器人账户。",
        "project_overview": "项目概览",
        "project_overview_desc": "对仓库开发历史和整体健康状况的综合分析",
        "activity_patterns": "活跃模式",
        "activity_patterns_desc": "关于提交频率、开发节奏和时间模式的洞察",
        "team_collaboration": "团队协作",
        "team_collaboration_desc": "贡献者动态、团队多样性和协作模式的分析",
        "code_evolution": "代码演进",
        "code_evolution_desc": "代码库增长、代码变动和维护模式的理解",
        "analysis_unavailable": "分析不可用",
        "no_analysis": "此部分暂无可用分析。",
        "about_ai_insights": "关于 AI 洞察",
        "ai_disclaimer": "这些洞察是基于仓库统计数据使用人工智能生成的。虽然 AI 分析可以识别模式和趋势，但应将其视为补充信息，与您对项目的理解相结合。",
        "bot_note": "<strong>注意：</strong>机器人账户（如 dependabot[bot]、pre-commit-ci[bot] 和其他自动化贡献者）已自动从分析中排除，以专注于人类团队动态。",
    },
}


def get_i18n_text(key: str, language: str = "en") -> str:
    """Get internationalized text for AI Insights page.

    Args:
        key: Translation key
        language: Language code (e.g., 'en', 'zh', 'zh-CN')

    Returns:
        Translated text
    """
    # Normalize language code
    if language.startswith("zh"):
        language = "zh-CN" if "CN" in language or "Hans" in language else "zh"

    # Get translations for the language, fallback to English
    translations = AI_INSIGHTS_I18N.get(language, AI_INSIGHTS_I18N["en"])

    # Get the translated text, fallback to English if key not found
    return translations.get(key, AI_INSIGHTS_I18N["en"].get(key, key))


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
            elif v.lower() in ("true", "false"):
                _config[k] = v.lower() == "true"
            else:
                _config[k] = v
    return _config
