# Copyright (c) 2007-2014 Heikki Hokkanen <hoxu@users.sf.net> & others contributors
# GPLv2 / GPLv3
# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
"""The report: its pages, written one after the other.

HTMLReportCreator is the pages of gitstats.pages together. What the pages are
made of is in the modules next to this one: gitstats.markup (the HTML they
share), gitstats.charts, gitstats.periods (months, years and quiet periods),
gitstats.history, gitstats.ownership and gitstats.share_card.
"""

import os
import shutil
from typing import Any

from gitstats import load_config
from gitstats.badge import create_badges
from gitstats.pages.activity import ActivityPage
from gitstats.pages.ai_insights import AIInsightsPage
from gitstats.pages.authors import AuthorsPage
from gitstats.pages.badges import BadgesPage
from gitstats.pages.files import FilesPage
from gitstats.pages.history import HistoryPage
from gitstats.pages.hotspots import HotspotsPage
from gitstats.pages.lines import LinesPage
from gitstats.pages.overview import OverviewPage
from gitstats.pages.ownership import OwnershipPage
from gitstats.pages.tags import TagsPage
from gitstats.share_card import report_share_card_html, report_share_description


class ReportCreator:
    """Creates the actual report based on given data."""

    def __init__(self) -> None:
        self.data: Any = None
        self.path: str | None = None

    def create(self, data: Any, path: str) -> None:
        self.data = data
        self.path = path


class HTMLReportCreator(
    OverviewPage,
    ActivityPage,
    AuthorsPage,
    FilesPage,
    LinesPage,
    TagsPage,
    OwnershipPage,
    HotspotsPage,
    HistoryPage,
    BadgesPage,
    AIInsightsPage,
    ReportCreator,
):
    """Writes the report: every page of it, and what the pages link to."""

    def create(self, data: Any, path: str) -> None:
        ReportCreator.create(self, data, path)
        self.title = data.project_name

        # copy static files to the report directory
        basedir = os.path.dirname(os.path.abspath(__file__))
        for file in (
            load_config()["style"],
            "sortable.js",
            "chart.umd.min.js",
        ):
            src = basedir + "/" + file
            if os.path.exists(src):
                shutil.copyfile(src, path + "/" + file)

        # shareable badges served alongside the report (see gitstats/badge.py)
        create_badges(data, path)
        # what a link to the report shows where it is shared
        self.share_description = report_share_description(data)
        with open(os.path.join(path, "share-card.html"), "w", encoding="utf-8") as card:
            card.write(report_share_card_html(data))

        self.create_index_html(data, path)
        self.create_activity_html(data, path)
        self.create_authors_html(data, path)
        self.create_files_html(data, path)
        self.create_lines_html(data, path)
        self.create_tags_html(data, path)
        self.create_ownership_html(data, path)
        self.create_hotspots_html(data, path)
        self.create_history_html(data, path)
        self.create_badges_html(data, path)

        # Create AI Insights page if AI is enabled
        if hasattr(data, "ai_summaries") and data.ai_summaries:
            self.create_ai_insights_html(data, path)
        elif os.path.isfile(os.path.join(path, "ai-insights.html")):
            # an earlier run's page, no longer linked and with its old numbers
            os.remove(os.path.join(path, "ai-insights.html"))
