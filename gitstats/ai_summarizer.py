"""
AI Summarizer for GitStats reports.

Generates intelligent summaries for different report pages using configured AI providers.
"""

import hashlib
import pickle
import logging
from typing import Dict, Any, Optional
from pathlib import Path

from gitstats.ai_providers import AIProviderFactory, AIProviderError

logger = logging.getLogger("gitstats")


class AISummarizer:
    """Generates AI-powered summaries for GitStats reports."""

    # Common bot account patterns to filter out from analysis
    BOT_PATTERNS = [
        "[bot]",
        "bot@",
        "dependabot",
        "pre-commit-ci",
        "renovate",
        "github-actions",
        "greenkeeper",
        "snyk-bot",
        "codecov",
        "travis",
        "jenkins",
    ]

    # Language-specific prompt instructions
    LANGUAGE_INSTRUCTIONS = {
        "en": "Provide your analysis in English.",
        "zh": "请用中文提供分析。",
        "zh-CN": "请用简体中文提供分析。",
        "zh-TW": "請用繁體中文提供分析。",
        "ja": "日本語で分析を提供してください。",
        "ko": "한국어로 분석을 제공해 주세요.",
        "es": "Proporcione su análisis en español.",
        "fr": "Fournissez votre analyse en français.",
        "de": "Geben Sie Ihre Analyse auf Deutsch an.",
    }

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the AI summarizer.

        Args:
            config: Configuration dictionary containing AI settings
        """
        self.config = config
        self.provider = None
        self.cache_dir: Optional[Path] = None
        self.cache_enabled = config.get("ai_cache_enabled", True)

        # Initialize AI provider if enabled
        if config.get("ai_enabled", False):
            try:
                provider_name = config.get("ai_provider", "openai")
                provider_config = {
                    "api_key": config.get("ai_api_key"),
                    "model": config.get("ai_model"),
                    "base_url": config.get("ollama_base_url", "http://localhost:11434"),
                    "max_retries": config.get("ai_max_retries", 3),
                    "retry_delay": config.get("ai_retry_delay", 1),
                }
                self.provider = AIProviderFactory.create(provider_name, provider_config)
                logger.info(f"Initialized AI provider: {provider_name}")
            except Exception as e:
                logger.error(f"Failed to initialize AI provider: {str(e)}")
                raise

    def set_cache_dir(self, cache_dir: str):
        """Set the directory for caching AI summaries."""
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_key(self, page_type: str, data_hash: str) -> str:
        """Generate cache key for a specific page and data."""
        config_hash = hashlib.md5(
            f"{self.config.get('ai_provider')}-{self.config.get('ai_model')}-{self.config.get('ai_language', 'en')}".encode()
        ).hexdigest()[:8]
        return f"{page_type}_{data_hash}_{config_hash}"

    def _get_cached_summary(self, cache_key: str) -> Optional[str]:
        """Retrieve cached summary if available."""
        if not self.cache_enabled or not self.cache_dir:
            return None

        cache_file = self.cache_dir / f"{cache_key}.pkl"
        if cache_file.exists():
            try:
                with open(cache_file, "rb") as f:
                    cached_data = pickle.load(f)
                    logger.info(f"Using cached AI summary for {cache_key}")
                    return cached_data["summary"]
            except Exception as e:
                logger.warning(f"Failed to load cached summary: {str(e)}")
        return None

    def _save_cached_summary(self, cache_key: str, summary: str):
        """Save generated summary to cache."""
        if not self.cache_enabled or not self.cache_dir:
            return

        cache_file = self.cache_dir / f"{cache_key}.pkl"
        try:
            with open(cache_file, "wb") as f:
                pickle.dump({"summary": summary}, f)
            logger.info(f"Cached AI summary for {cache_key}")
        except Exception as e:
            logger.warning(f"Failed to cache summary: {str(e)}")

    def _get_language_instruction(self) -> str:
        """Get language-specific instruction for prompts."""
        language = self.config.get("ai_language", "en")
        return self.LANGUAGE_INSTRUCTIONS.get(
            language, self.LANGUAGE_INSTRUCTIONS["en"]
        )

    def _is_bot_account(self, author_name: str) -> bool:
        """Check if an author name is a bot account."""
        author_lower = author_name.lower()
        return any(pattern.lower() in author_lower for pattern in self.BOT_PATTERNS)

    def _filter_human_authors(self, authors: Dict[str, Any]) -> Dict[str, Any]:
        """Filter out bot accounts from authors dictionary."""
        return {
            name: info
            for name, info in authors.items()
            if not self._is_bot_account(name)
        }

    def prepare_index_data(self, data: Dict[str, Any]) -> str:
        """Prepare data context for index page summary."""
        commits_count = data.get("total_commits", 0)
        files_count = data.get("total_files", 0)
        lines_of_code = data.get("total_lines_of_code", 0)

        first_commit = data.get("first_commit_date", "Unknown")
        last_commit = data.get("last_commit_date", "Unknown")
        active_days = data.get("active_days", 0)

        # Get top human authors (filter out bots)
        authors = data.get("authors", {})
        human_authors = self._filter_human_authors(authors)
        authors_count = len(human_authors)
        bot_count = len(authors) - len(human_authors)

        top_authors = sorted(
            human_authors.items(), key=lambda x: x[1].get("commits", 0), reverse=True
        )[:5]
        top_authors_str = "\n".join(
            [
                f"  - {name}: {info.get('commits', 0)} commits"
                for name, info in top_authors
            ]
        )

        context = f"""Repository Statistics Overview:
- Total Human Authors: {authors_count}
- Bot Accounts: {bot_count}
- Total Commits: {commits_count}
- Total Files: {files_count}
- Total Lines of Code: {lines_of_code:,}
- First Commit: {first_commit}
- Last Commit: {last_commit}
- Active Days: {active_days}

Top 5 Human Contributors:
{top_authors_str}

Note: Bot accounts (like dependabot[bot], pre-commit-ci[bot]) are excluded from author counts to focus on human contributions.
"""
        return context

    def prepare_activity_data(self, data: Dict[str, Any]) -> str:
        """Prepare data context for activity page summary."""
        commits_by_year = data.get("commits_by_year", {})
        commits_by_hour = data.get("commits_by_hour_of_day", {})
        commits_by_day = data.get("commits_by_day_of_week", {})
        commits_by_timezone = data.get("commits_by_timezone", {})

        # Find peak activity periods
        if commits_by_hour:
            peak_hour = max(commits_by_hour.items(), key=lambda x: x[1])
            peak_hour_str = f"Hour {peak_hour[0]}: {peak_hour[1]} commits"
        else:
            peak_hour_str = "N/A"

        if commits_by_day:
            days = [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ]
            peak_day = max(commits_by_day.items(), key=lambda x: x[1])
            peak_day_str = f"{days[int(peak_day[0])]}: {peak_day[1]} commits"
        else:
            peak_day_str = "N/A"

        # Year over year trend
        years_str = "\n".join(
            [
                f"  - {year}: {count} commits"
                for year, count in sorted(commits_by_year.items())
            ]
        )

        context = f"""Activity Patterns:

Commits by Year:
{years_str}

Peak Activity:
- Peak Hour: {peak_hour_str}
- Peak Day: {peak_day_str}

Timezone Distribution: {len(commits_by_timezone)} different timezones
"""
        return context

    def prepare_authors_data(self, data: Dict[str, Any]) -> str:
        """Prepare data context for authors page summary."""
        authors = data.get("authors", {})

        # Filter human authors (exclude bots)
        human_authors = self._filter_human_authors(authors)
        total_authors = len(human_authors)
        bot_count = len(authors) - len(human_authors)

        # Sort human authors by commits
        authors_by_commits = sorted(
            human_authors.items(), key=lambda x: x[1].get("commits", 0), reverse=True
        )

        # Calculate statistics (for human authors only)
        total_commits = sum(info.get("commits", 0) for info in human_authors.values())

        # Top 10 human authors
        top_10 = authors_by_commits[:10]
        top_authors_str = "\n".join(
            [
                f"  - {name}: {info.get('commits', 0)} commits, +{info.get('lines_added', 0)}/-{info.get('lines_removed', 0)} lines"
                for name, info in top_10
            ]
        )

        # Calculate contribution concentration
        if authors_by_commits:
            top_author_percentage = (
                (authors_by_commits[0][1].get("commits", 0) / total_commits * 100)
                if total_commits > 0
                else 0
            )
            top_5_commits = sum(
                info.get("commits", 0) for _, info in authors_by_commits[:5]
            )
            top_5_percentage = (
                (top_5_commits / total_commits * 100) if total_commits > 0 else 0
            )
        else:
            top_author_percentage = 0
            top_5_percentage = 0

        context = f"""Author Statistics:

Total Human Authors: {total_authors}
Bot Accounts Excluded: {bot_count}
Total Human Commits: {total_commits}

Contribution Distribution:
- Top contributor: {top_author_percentage:.1f}% of commits
- Top 5 contributors: {top_5_percentage:.1f}% of commits

Top 10 Human Contributors:
{top_authors_str}

Note: Bot accounts (dependabot[bot], pre-commit-ci[bot], etc.) are excluded from this analysis to focus on human team collaboration patterns.
"""
        return context

    def prepare_lines_data(self, data: Dict[str, Any]) -> str:
        """Prepare data context for lines page summary."""
        total_lines = data.get("total_lines_of_code", 0)
        total_added = data.get("total_lines_added", 0)
        total_removed = data.get("total_lines_removed", 0)

        lines_by_date = data.get("lines_by_date", {})

        # Calculate growth trend
        if lines_by_date:
            dates = sorted(lines_by_date.keys())
            if len(dates) >= 2:
                start_lines = lines_by_date[dates[0]]
                end_lines = lines_by_date[dates[-1]]
                growth = end_lines - start_lines
                growth_rate = (growth / start_lines * 100) if start_lines > 0 else 0
                trend_str = f"Growth from {start_lines:,} to {end_lines:,} lines ({growth_rate:+.1f}%)"
            else:
                trend_str = f"Current: {total_lines:,} lines"
        else:
            trend_str = f"Current: {total_lines:,} lines"

        # Lines by human authors (exclude bots)
        authors = data.get("authors", {})
        human_authors = self._filter_human_authors(authors)
        authors_by_lines = sorted(
            human_authors.items(),
            key=lambda x: x[1].get("lines_added", 0) - x[1].get("lines_removed", 0),
            reverse=True,
        )[:5]

        top_authors_str = "\n".join(
            [
                f"  - {name}: +{info.get('lines_added', 0):,}/-{info.get('lines_removed', 0):,} (net: {info.get('lines_added', 0) - info.get('lines_removed', 0):+,})"
                for name, info in authors_by_lines
            ]
        )

        context = f"""Code Lines Statistics:

Total Lines of Code: {total_lines:,}
Total Lines Added: {total_added:,}
Total Lines Removed: {total_removed:,}
Net Change: {total_added - total_removed:+,}

Growth Trend:
{trend_str}

Top 5 Contributors by Lines:
{top_authors_str}
"""
        return context

    def generate_summary(
        self, page_type: str, data: Dict[str, Any], force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Generate AI summary for a specific page type.

        Args:
            page_type: Type of page (index, activity, authors, lines)
            data: Repository statistics data
            force_refresh: Force regenerate even if cached

        Returns:
            Dictionary with 'summary' (str) and 'error' (str or None)
        """
        result = {"summary": "", "error": None}

        if not self.provider:
            result["error"] = "AI provider not initialized"
            return result

        try:
            # Prepare page-specific data
            if page_type == "index":
                data_context = self.prepare_index_data(data)
                prompt_focus = "Provide a comprehensive overview of this repository's development history, highlighting key statistics, contribution patterns, and overall project health. Identify any notable trends or insights."
            elif page_type == "activity":
                data_context = self.prepare_activity_data(data)
                prompt_focus = "Analyze the activity patterns over time. Identify trends in commit frequency, peak activity periods, and any notable changes in development pace. Provide insights into the project's development rhythm."
            elif page_type == "authors":
                data_context = self.prepare_authors_data(data)
                prompt_focus = "Analyze the contributor dynamics and team collaboration patterns. Discuss contribution distribution, potential knowledge silos, team diversity, and recommendations for healthy collaboration."
            elif page_type == "lines":
                data_context = self.prepare_lines_data(data)
                prompt_focus = "Analyze the codebase evolution in terms of code volume. Discuss growth patterns, code churn, and what these metrics might indicate about the project's maturity and maintenance burden."
            else:
                result["error"] = f"Unknown page type: {page_type}"
                return result

            # Generate cache key
            data_hash = hashlib.md5(data_context.encode()).hexdigest()[:8]
            cache_key = self._get_cache_key(page_type, data_hash)

            # Check cache unless force refresh
            if not force_refresh:
                cached_summary = self._get_cached_summary(cache_key)
                if cached_summary:
                    result["summary"] = cached_summary
                    return result

            # Construct prompt
            language_instruction = self._get_language_instruction()
            prompt = f"""You are analyzing git repository statistics. Based on the following data, {prompt_focus}

{data_context}

Requirements:
- Provide detailed analysis with 3-5 paragraphs
- Include specific numbers and percentages from the data
- Identify trends, patterns, and anomalies
- Offer actionable insights or recommendations where relevant
- Format your response in HTML (use <p>, <ul>, <li>, <strong>, <em> tags)
- {language_instruction}

Generate your analysis:"""

            # Call AI provider
            logger.info(f"Generating AI summary for {page_type} page...")
            summary = self.provider.generate_summary(data, prompt)

            # Cache the result
            self._save_cached_summary(cache_key, summary)

            result["summary"] = summary

        except AIProviderError as e:
            logger.error(f"AI provider error: {str(e)}")
            result["error"] = str(e)
        except Exception as e:
            logger.error(f"Unexpected error generating summary: {str(e)}")
            result["error"] = f"Unexpected error: {str(e)}"

        return result

    def generate_all_summaries(
        self, data: Dict[str, Any], force_refresh: bool = False
    ) -> Dict[str, Dict[str, Any]]:
        """
        Generate summaries for all report pages.

        Args:
            data: Repository statistics data
            force_refresh: Force regenerate even if cached

        Returns:
            Dictionary mapping page types to summary results
        """
        summaries = {}
        page_types = ["index", "activity", "authors", "lines"]

        for page_type in page_types:
            summaries[page_type] = self.generate_summary(page_type, data, force_refresh)

        return summaries
