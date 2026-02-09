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
    "ai_language": "en",  # Language for AI-generated summaries (en, zh, ja, ko, es, fr, de, etc.).
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
