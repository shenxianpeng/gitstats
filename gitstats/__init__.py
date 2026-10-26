# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
from __future__ import annotations

import platform
import re
import time
from typing import Any

exectime_internal: float = 0.0
exectime_external: float = 0.0
time_start: float = time.time()

ON_LINUX: bool = platform.system() == "Linux"
WEEKDAYS: tuple[str, ...] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

DEFAULT_CONFIG: dict[str, Any] = {
    "max_domains": 10,  # Maximum number of domains to display in "Domains by Commits".
    "max_ext_length": 10,  # Maximum length of file extensions shown in statistics.
    "style": "gitstats.css",  # CSS stylesheet for the generated report.
    "max_authors": 20,  # Maximum number of authors to list in "Authors".
    "max_tags_authors": 50,  # Maximum number of authors per tag in "Tags" page.
    "max_authors_list": 50,  # Maximum number of "other" authors listed by name on the Authors page.
    "authors_top": 5,  # Number of top authors to highlight.
    "commit_begin": "",  # Start of commit range (empty = include all commits).
    "commit_end": "HEAD",  # End of commit range (default: HEAD).
    "linear_linestats": 1,  # Enable linear history for line statistics (1 = enabled, 0 = disabled).
    "project_name": "",  # Project name to display (default: repository directory name).
    "processes": 8,  # Parallel processes to use when gathering data, at most (1 = one git command at a time).
    "start_date": "",  # Starting date for commits, passed as --since to Git (optional).
    "end_date": "",  # Ending date for commits, passed as --until to Git (optional). Format: YYYY-MM-DD.
    "authors": "",  # Comma-separated list of authors to filter commits (empty = include all authors).
    "exclude_exts": "",  # File extensions to exclude from line counting (others detected via null bytes).
    # Shareable badge (badge.svg and badges/ in the report output)
    # Badge written as badge.svg: commits, last-commit, authors, files, lines,
    # release, active-days, summary, activity or health.
    "badge_metric": "commits",
    "badge_label": "gitstats",  # Left-side badge text.
    "badge_color": "",  # Value-segment color: shields name (green, orange, ...), hex, or any SVG color (empty = brand blue).
    # Badge style: flat (rounded, subtle gradient), flat-square (sharp corners),
    # terminal (monospace and square, like the report), for-the-badge (large)
    # or light (white and pale blue, for white READMEs).
    "badge_style": "flat",
    # Public address of the report (https://owner.github.io/repo/): fills in the
    # Badges page's snippets and prints the README badge. Also --site-url.
    "site_url": "",
    # With site_url: let the pages point to share-card.png, the image a link to
    # them shows where it is shared. gitstats writes the card as share-card.html
    # (1200 x 630 pixels); turning it into the PNG is up to whoever publishes it.
    "share_card": False,
    # AI-powered features
    "ai_enabled": False,  # Enable AI-powered summaries (requires AI provider configuration).
    "ai_provider": "openai",  # AI provider: openai, claude, gemini, ollama.
    "ai_api_key": "",  # API key for AI provider (can also use environment variables).
    "ai_model": "",  # AI model to use (e.g., gpt-4, claude-3-5-sonnet-20241022, gemini-pro, llama2).
    "ai_language": "en",  # Language for AI-generated summaries (en, zh, ja, ko, es, fr, de, etc.).
    "ai_cache_enabled": True,  # Cache AI-generated summaries to save API costs.
    "ai_max_retries": 3,  # Maximum retry attempts for AI API calls.
    "ai_retry_delay": 1,  # Delay in seconds between retries.
    "ollama_base_url": "http://localhost:11434",  # Base URL for Ollama local LLM.
}


_config: dict[str, Any] | None = None


# Internationalization translations for AI Insights page
AI_INSIGHTS_I18N = {
    "en": {
        "ai_insights_title": "AI-Powered Insights",
        "ai_insights_intro": "This page contains AI-generated analysis and insights based on your repository statistics. The analysis focuses on human contributions and excludes automated bot accounts.",
        "project_overview": "Project Overview",
        "project_overview_desc": "Comprehensive analysis of the repository's development history and overall health",
        "activity_patterns": "Activity Patterns",
        "activity_patterns_desc": "Insights into commit frequency, development rhythm, and temporal patterns",
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
        "code_evolution": "代码演进",
        "code_evolution_desc": "代码库增长、代码变动和维护模式的理解",
        "analysis_unavailable": "分析不可用",
        "no_analysis": "此部分暂无可用分析。",
        "about_ai_insights": "关于 AI 洞察",
        "ai_disclaimer": "这些洞察是基于仓库统计数据使用人工智能生成的。虽然 AI 分析可以识别模式和趋势，但应将其视为补充信息，与您对项目的理解相结合。",
        "bot_note": "<strong>注意：</strong>机器人账户（如 dependabot[bot]、pre-commit-ci[bot] 和其他自动化贡献者）已自动从分析中排除，以专注于人类团队动态。",
    },
    "ja": {
        "ai_insights_title": "AI分析インサイト",
        "ai_insights_intro": "このページには、リポジトリ統計に基づくAI生成の分析と洞察が含まれています。分析は人間の貢献者に焦点を当て、自動化されたボットアカウントを除外しています。",
        "project_overview": "プロジェクト概要",
        "project_overview_desc": "リポジトリの開発履歴と全体的な健全性の包括的な分析",
        "activity_patterns": "活動パターン",
        "activity_patterns_desc": "コミット頻度、開発リズム、時間的パターンに関する洞察",
        "code_evolution": "コードの進化",
        "code_evolution_desc": "コードベースの成長、コード変更、メンテナンスパターンの理解",
        "analysis_unavailable": "分析は利用できません",
        "no_analysis": "このセクションの分析は利用できません。",
        "about_ai_insights": "AIインサイトについて",
        "ai_disclaimer": "これらのインサイトは、リポジトリ統計に基づいて人工知能を使用して生成されています。AI分析はパターンとトレンドを識別できますが、プロジェクトに対する自身の理解と併せて補足情報として考慮する必要があります。",
        "bot_note": "<strong>注意：</strong>ボットアカウント（dependabot[bot]、pre-commit-ci[bot]などの自動化された貢献者）は、人間のチームダイナミクスに焦点を当てるため、分析から自動的に除外されます。",
    },
    "ko": {
        "ai_insights_title": "AI 기반 인사이트",
        "ai_insights_intro": "이 페이지는 저장소 통계를 기반으로 AI가 생성한 분석 및 인사이트를 포함합니다. 분석은 인간 기여자에 초점을 맞추고 자동화된 봇 계정은 제외합니다.",
        "project_overview": "프로젝트 개요",
        "project_overview_desc": "저장소의 개발 이력과 전반적인 상태에 대한 종합 분석",
        "activity_patterns": "활동 패턴",
        "activity_patterns_desc": "커밋 빈도, 개발 리듬 및 시간적 패턴에 대한 인사이트",
        "code_evolution": "코드 진화",
        "code_evolution_desc": "코드베이스 성장, 코드 변경 및 유지 관리 패턴에 대한 이해",
        "analysis_unavailable": "분석을 사용할 수 없음",
        "no_analysis": "이 섹션에 대한 분석을 사용할 수 없습니다.",
        "about_ai_insights": "AI 인사이트 정보",
        "ai_disclaimer": "이러한 인사이트는 저장소 통계를 기반으로 인공지능을 사용하여 생성됩니다. AI 분석은 패턴과 추세를 식별할 수 있지만 프로젝트에 대한 자신의 이해와 함께 보충 정보로 간주해야 합니다.",
        "bot_note": "<strong>참고:</strong> 봇 계정(dependabot[bot], pre-commit-ci[bot] 및 기타 자동화된 기여자)은 인간 팀 역학에 초점을 맞추기 위해 분석에서 자동으로 제외됩니다.",
    },
    "es": {
        "ai_insights_title": "Perspectivas impulsadas por IA",
        "ai_insights_intro": "Esta página contiene análisis e información generados por IA basados en las estadísticas de su repositorio. El análisis se centra en las contribuciones humanas y excluye las cuentas de bots automatizados.",
        "project_overview": "Descripción del proyecto",
        "project_overview_desc": "Análisis integral del historial de desarrollo del repositorio y su salud general",
        "activity_patterns": "Patrones de actividad",
        "activity_patterns_desc": "Perspectivas sobre la frecuencia de commits, el ritmo de desarrollo y los patrones temporales",
        "code_evolution": "Evolución del código",
        "code_evolution_desc": "Comprensión del crecimiento del código base, cambios de código y patrones de mantenimiento",
        "analysis_unavailable": "Análisis no disponible",
        "no_analysis": "No hay análisis disponible para esta sección.",
        "about_ai_insights": "Acerca de las perspectivas de IA",
        "ai_disclaimer": "Estas perspectivas se generan mediante inteligencia artificial basada en estadísticas del repositorio. Si bien el análisis de IA puede identificar patrones y tendencias, debe considerarse como información complementaria junto con su propia comprensión del proyecto.",
        "bot_note": "<strong>Nota:</strong> Las cuentas de bots (como dependabot[bot], pre-commit-ci[bot] y otros contribuyentes automatizados) se excluyen automáticamente del análisis para centrarse en la dinámica del equipo humano.",
    },
    "fr": {
        "ai_insights_title": "Analyses générées par l'IA",
        "ai_insights_intro": "Cette page contient des analyses et des informations générées par l'IA basées sur les statistiques de votre dépôt. L'analyse se concentre sur les contributions humaines et exclut les comptes de bots automatisés.",
        "project_overview": "Aperçu du projet",
        "project_overview_desc": "Analyse complète de l'historique de développement du dépôt et de sa santé globale",
        "activity_patterns": "Modèles d'activité",
        "activity_patterns_desc": "Aperçu de la fréquence des commits, du rythme de développement et des modèles temporels",
        "code_evolution": "Évolution du code",
        "code_evolution_desc": "Compréhension de la croissance de la base de code, des modifications de code et des modèles de maintenance",
        "analysis_unavailable": "Analyse non disponible",
        "no_analysis": "Aucune analyse disponible pour cette section.",
        "about_ai_insights": "À propos des analyses IA",
        "ai_disclaimer": "Ces analyses sont générées à l'aide de l'intelligence artificielle basée sur les statistiques du dépôt. Bien que l'analyse IA puisse identifier des modèles et des tendances, elle doit être considérée comme des informations complémentaires en plus de votre propre compréhension du projet.",
        "bot_note": "<strong>Remarque :</strong> Les comptes de bots (tels que dependabot[bot], pre-commit-ci[bot] et autres contributeurs automatisés) sont automatiquement exclus de l'analyse pour se concentrer sur la dynamique de l'équipe humaine.",
    },
    "de": {
        "ai_insights_title": "KI-gestützte Einblicke",
        "ai_insights_intro": "Diese Seite enthält KI-generierte Analysen und Einblicke basierend auf Ihren Repository-Statistiken. Die Analyse konzentriert sich auf menschliche Beiträge und schließt automatisierte Bot-Konten aus.",
        "project_overview": "Projektübersicht",
        "project_overview_desc": "Umfassende Analyse der Entwicklungsgeschichte des Repositorys und seiner allgemeinen Gesundheit",
        "activity_patterns": "Aktivitätsmuster",
        "activity_patterns_desc": "Einblicke in Commit-Häufigkeit, Entwicklungsrhythmus und zeitliche Muster",
        "code_evolution": "Code-Evolution",
        "code_evolution_desc": "Verständnis des Codebase-Wachstums, der Code-Änderungen und der Wartungsmuster",
        "analysis_unavailable": "Analyse nicht verfügbar",
        "no_analysis": "Für diesen Abschnitt ist keine Analyse verfügbar.",
        "about_ai_insights": "Über KI-Einblicke",
        "ai_disclaimer": "Diese Einblicke werden mithilfe künstlicher Intelligenz basierend auf Repository-Statistiken generiert. Obwohl KI-Analysen Muster und Trends identifizieren können, sollten sie als ergänzende Informationen neben Ihrem eigenen Verständnis des Projekts betrachtet werden.",
        "bot_note": "<strong>Hinweis:</strong> Bot-Konten (wie dependabot[bot], pre-commit-ci[bot] und andere automatisierte Mitwirkende) werden automatisch aus der Analyse ausgeschlossen, um sich auf die menschliche Teamdynamik zu konzentrieren.",
    },
}


def get_i18n_text(key: str, language: str = "en") -> str:
    """Get internationalized text for AI Insights page.

    Args:
        key: Translation key
        language: Language code (e.g., 'en', 'zh', 'ja', 'ko', 'es', 'fr', 'de')

    Returns:
        Translated text
    """
    # Normalize language code
    if language.startswith("zh"):
        language = "zh"  # All Chinese variants map to zh

    # Get translations for the language, fallback to English
    translations = AI_INSIGHTS_I18N.get(language, AI_INSIGHTS_I18N["en"])

    # Get the translated text, fallback to English if key not found
    return translations.get(key, AI_INSIGHTS_I18N["en"].get(key, key))


# what a boolean setting may be written as, like ConfigParser.getboolean()
_TRUE_WORDS = ("true", "yes", "on", "1")
_FALSE_WORDS = ("false", "no", "off", "0")

# What load_config() could not take from the configuration file, a sentence
# each. Those settings keep their defaults; the command line reports these
# before it does anything else, and `gitstats --version` still works.
config_errors: list[str] = []


def parse_config_value(value: str, key: str | None = None) -> Any:
    """Convert a config value from the config file or ``-c key=value``.

    A setting of DEFAULT_CONFIG takes the type of its default: an integer, a
    boolean (true/false, yes/no, on/off, 1/0) or a string. A string stays as
    written even when it is all digits, like a short commit hash for
    ``commit_end``. A value that is not of its setting's type raises
    ValueError, with a message that names the setting.

    Any other key (or none) is guessed at: integers, including negative ones
    such as ``-1``, become ``int`` and ``true``/``false`` become ``bool``;
    anything else stays a string.
    """
    default = DEFAULT_CONFIG.get(key) if key is not None else None
    if isinstance(default, bool):
        word = value.strip().lower()
        if word in _TRUE_WORDS or word in _FALSE_WORDS:
            return word in _TRUE_WORDS
        raise ValueError(f"{key} must be true or false, not {value!r}")
    if isinstance(default, int):
        try:
            return int(value)
        except ValueError:
            raise ValueError(f"{key} must be a whole number, not {value!r}") from None
    if isinstance(default, str):
        return value
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    return value


def load_config(file_path: str = "gitstats.conf") -> dict[str, Any]:
    """Load configuration from a file, or fall back to defaults.

    The file's ``[gitstats]`` section is read as it is written: a "%" is a
    "%". A file without that section leaves every setting at its default,
    with a warning. What cannot be read, a malformed file or a value of the
    wrong type, is added to ``config_errors`` and leaves those settings at
    their defaults: an import of gitstats never fails on it.
    """
    import configparser
    import logging
    import os

    global _config

    if _config is not None:
        return _config

    config = DEFAULT_CONFIG.copy()  # Start with defaults
    errors: list[str] = []
    config_parser = configparser.ConfigParser(interpolation=None)

    if os.path.exists(file_path):
        try:
            config_parser.read(file_path, encoding="utf-8")
        except configparser.MissingSectionHeaderError:
            pass  # settings without a section: reported as such below
        except (configparser.Error, UnicodeDecodeError) as error:
            errors.append(f"{file_path}: {error}")
        if errors:
            pass  # nothing is taken from a file that could not be read
        elif config_parser.has_section("gitstats"):
            for k, v in config_parser["gitstats"].items():
                try:
                    config[k] = parse_config_value(v, k)
                except ValueError as error:
                    errors.append(f"{file_path}: {error}")
        else:
            logging.getLogger("gitstats").warning(
                f"Warning: {file_path} has no [gitstats] section; using the default settings"
            )
    config_errors[:] = errors
    _config = config
    return _config
