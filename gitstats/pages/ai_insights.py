# Copyright (c) 2007-2014 Heikki Hokkanen <hoxu@users.sf.net> & others contributors
# GPLv2 / GPLv3
# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
"""The AI Insights page: every AI-generated summary of the report in one place."""

import html
from typing import Any

from gitstats import get_i18n_text, load_config
from gitstats.pages.base import PageWriter
from gitstats.safe_html import sanitize_ai_html


class AIInsightsPage(PageWriter):
    """Writes ai-insights.html."""

    def create_ai_insights_html(self, data: Any, path: str) -> None:
        """
        Create a dedicated AI Insights page with all AI-generated summaries.
        """
        # Get language from config
        language = load_config().get("ai_language", "en")

        f = open(path + "/ai-insights.html", "w", encoding="utf-8")
        self.print_header(f, "ai-insights.html")
        self.print_nav(f, "ai-insights.html")
        f.write(f"<h1>{get_i18n_text('ai_insights_title', language)}</h1>")

        f.write(f"""
        <div class="ai-insights-intro">
            <p>{get_i18n_text("ai_insights_intro", language)}</p>
        </div>
        """)

        # Get all AI summaries
        summaries = data.ai_summaries

        # Define sections with titles and descriptions
        sections = [
            {
                "key": "index",
                "title": get_i18n_text("project_overview", language),
                "description": get_i18n_text("project_overview_desc", language),
            },
            {
                "key": "activity",
                "title": get_i18n_text("activity_patterns", language),
                "description": get_i18n_text("activity_patterns_desc", language),
            },
            {
                "key": "lines",
                "title": get_i18n_text("code_evolution", language),
                "description": get_i18n_text("code_evolution_desc", language),
            },
        ]

        # Generate sections
        for section in sections:
            key = section["key"]
            if key not in summaries:
                continue

            summary_data = summaries[key]
            summary_text = summary_data.get("summary", "")
            error = summary_data.get("error")

            f.write('<div class="ai-insight-section">')
            f.write(f'<h2 id="{key}">{section["title"]}</h2>')
            f.write(f'<p class="section-description"><em>{section["description"]}</em></p>')

            if error:
                f.write(f"""
                <div class="ai-summary-error">
                    <p><strong>{get_i18n_text("analysis_unavailable", language)}</strong></p>
                    <p><em>{html.escape(str(error))}</em></p>
                </div>
                """)
            elif summary_text:
                # the model's HTML, down to paragraphs, lists and emphasis: its
                # data holds author names and commit subjects, which anyone who
                # commits can write
                f.write(f"""
                <div class="ai-summary-content">
                    {sanitize_ai_html(summary_text)}
                </div>
                """)
            else:
                f.write(f"<p><em>{get_i18n_text('no_analysis', language)}</em></p>")

            f.write("</div>")

        # Add disclaimer
        f.write(f"""
        <div class="ai-disclaimer">
            <h3>{get_i18n_text("about_ai_insights", language)}</h3>
            <p>{get_i18n_text("ai_disclaimer", language)}</p>
            <p>{get_i18n_text("bot_note", language)}</p>
        </div>
        """)

        self.print_footer(f)
        f.write("</body></html>")
        f.close()
