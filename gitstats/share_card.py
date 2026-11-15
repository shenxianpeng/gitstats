# Copyright (c) 2007-2014 Heikki Hokkanen <hoxu@users.sf.net> & others contributors
# GPLv2 / GPLv3
# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
"""What a link to a page shows where it is shared: the tags that preview it
(Open Graph, and X's own) and the share card, an HTML page of the size those
places ask for, left to render as an image.
"""

import datetime
import html
from typing import Any

from gitstats.markup import plural, share_text
from gitstats.periods import month_range, months_back, sum_since
from gitstats.utils import format_int

# A share card is what a link shows where it is posted, at the size those
# places ask for. gitstats writes it as an HTML page; the pages point to it as
# an image (share-card.png) when the report is published with share_card on.
SHARE_CARD_WIDTH = 1200
SHARE_CARD_HEIGHT = 630
_CARD_MONO = 'ui-monospace, SFMono-Regular, Menlo, "DejaVu Sans Mono", monospace'
SHARE_CARD_CSS = f"""
*{{box-sizing:border-box}}
html,body{{margin:0}}
body{{width:{SHARE_CARD_WIDTH}px;height:{SHARE_CARD_HEIGHT}px;background:#ffffff;color:#211e1e;
font:24px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI","DejaVu Sans",sans-serif}}
main{{height:{SHARE_CARD_HEIGHT}px;padding:54px 64px 44px;display:flex;flex-direction:column}}
.brand{{font:600 22px {_CARD_MONO};color:#716b6b;letter-spacing:.04em}}
h1{{font:700 72px/1.1 {_CARD_MONO};margin:14px 0 8px;white-space:nowrap;overflow:hidden;
text-overflow:ellipsis}}
.sub{{margin:0 0 30px;color:#716b6b}}
.tiles{{display:grid;grid-template-columns:repeat(4,1fr);margin:0;border:2px solid #cfcecd}}
.tiles div{{padding:16px 22px;border-left:2px solid #cfcecd}}
.tiles div:first-child{{border-left:0}}
.tiles dt{{font:15px {_CARD_MONO};letter-spacing:.08em;text-transform:uppercase;color:#716b6b}}
.tiles dd{{margin:6px 0 0;font:700 40px {_CARD_MONO};white-space:nowrap}}
.tiles dd span{{margin-left:12px;font-size:20px;font-weight:600;color:#716b6b}}
.tiles dd .wrapped-up{{color:#2d6a3f}}
.tiles dd .wrapped-down{{color:#8b2323}}
.note{{margin:20px 0 0}}
.names{{margin:8px 0 0;font:600 30px/1.5 {_CARD_MONO};display:-webkit-box;-webkit-line-clamp:5;
-webkit-box-orient:vertical;overflow:hidden}}
.history{{margin:26px 0 0}}
.history .columns{{display:flex;align-items:flex-end;gap:2px;height:88px}}
.history i{{flex:1;background:#4a7ab5;border-radius:2px 2px 0 0;min-height:1px}}
.history .axis{{display:flex;justify-content:space-between;margin-top:6px;color:#716b6b;
font:16px {_CARD_MONO}}}
.bars{{display:grid;gap:12px;margin:4px 0 0}}
.bars div{{display:grid;grid-template-columns:240px 1fr 120px;align-items:center;gap:18px}}
.bars b{{font:600 26px {_CARD_MONO};white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.bars i{{display:block;height:26px;background:#4a7ab5;border-radius:0 4px 4px 0}}
.bars span{{font:700 28px {_CARD_MONO};text-align:right}}
.sub.clamp{{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.bars.ranks{{gap:10px}}
.bars.ranks div{{grid-template-columns:300px 1fr 160px}}
.bars.ranks b{{font-size:23px;font-weight:500;color:#716b6b}}
.bars.ranks i{{height:20px}}
.bars.ranks span{{font-size:24px;white-space:nowrap}}
.facts{{display:grid;gap:34px;margin:14px 0 0}}
.facts div{{display:grid;grid-template-columns:200px 1fr;align-items:center;gap:28px}}
.facts b{{font:700 60px/1 {_CARD_MONO};color:#4a7ab5;white-space:nowrap}}
.facts span{{font-size:27px;line-height:1.32;display:-webkit-box;-webkit-line-clamp:3;
-webkit-box-orient:vertical;overflow:hidden}}
.facts.n3{{gap:24px;margin-top:8px}}
.facts.n3 b{{font-size:50px}}
.facts.n3 span{{font-size:23px;-webkit-line-clamp:2}}
footer{{margin-top:auto;display:flex;justify-content:space-between;color:#716b6b;
font:20px {_CARD_MONO}}}
"""


def share_meta_html(title: str, description: str, site_url: str, page: str, image: str) -> str:
    """The tags a page is previewed by where a link to it is shared (Open
    Graph, and X's own). ``image`` is the card's file name next to the page,
    or "" for none; places that show a link want absolute addresses, so
    without ``site_url`` there is neither an address nor an image."""
    tags = [
        ("name", "description", description),
        ("property", "og:type", "website"),
        ("property", "og:site_name", "GitStats"),
        ("property", "og:title", title),
        ("property", "og:description", description),
    ]
    picture = site_url + image if site_url and image else ""
    if site_url:
        tags.append(("property", "og:url", site_url + ("" if page == "index.html" else page)))
    if picture:
        tags += [
            ("property", "og:image", picture),
            ("property", "og:image:width", str(SHARE_CARD_WIDTH)),
            ("property", "og:image:height", str(SHARE_CARD_HEIGHT)),
            ("property", "og:image:alt", title),
        ]
    tags.append(("name", "twitter:card", "summary_large_image" if picture else "summary"))
    tags += [("name", "twitter:title", title), ("name", "twitter:description", description)]
    if picture:
        tags.append(("name", "twitter:image", picture))
    return "\n\t".join(
        f'<meta {attribute}="{key}" content="{html.escape(value, quote=True)}">'
        for attribute, key, value in tags
        if value
    )


def share_card_page(title: str, body: str, footer: str = "made with gitstats") -> str:
    """A share card: ``body`` on a page of the card's size, with the footer
    every card has."""
    return (
        f'<!DOCTYPE html>\n<html lang="en"><head><meta charset="UTF-8">'
        f"<title>{html.escape(title)}</title><style>{SHARE_CARD_CSS}</style></head>"
        f"<body><main>{body}<footer><span>{footer}</span>"
        "<span>github.com/shenxianpeng/gitstats</span></footer></main></body></html>\n"
    )


def _last_twelve_months(data: Any) -> tuple[int, int]:
    """(commits that name an AI coding assistant, all commits) in the twelve
    months that end with the last commit."""
    by_month = getattr(data, "commits_by_month", None)
    if not isinstance(by_month, dict) or not by_month:
        return 0, 0
    since = months_back(max(by_month), 11)
    assisted = getattr(data, "ai_assisted_by_month", None)
    return (
        sum_since(assisted, since) if isinstance(assisted, dict) else 0,
        sum_since(by_month, since),
    )


def report_share_description(data: Any) -> str:
    """One sentence about the repository, for the pages' share tags."""
    commits, authors = data.get_total_commits(), data.get_total_authors()
    first, last = data.get_first_commit_date(), data.get_last_commit_date()
    text = f"{data.project_name}: {plural(commits, 'commit')} by {plural(authors, 'author')}"
    if isinstance(first, datetime.datetime) and isinstance(last, datetime.datetime):
        text += f", {first.year}" + (f" to {last.year}" if last.year != first.year else "")
    return text + ". A report made with gitstats."


def report_share_card_html(data: Any) -> str:
    """The report's share card: the repository, its years, four numbers, and
    the share of its recent commits that name an AI coding assistant."""
    first, last = data.get_first_commit_date(), data.get_last_commit_date()
    span = ""
    if isinstance(first, datetime.datetime) and isinstance(last, datetime.datetime):
        span = f"{first.strftime('%Y-%m-%d')} &rarr; {last.strftime('%Y-%m-%d')}"
    tiles = "".join(
        f"<div><dt>{label}</dt><dd>{format_int(value)}</dd></div>"
        for label, value in (
            ("Commits", data.get_total_commits()),
            ("Authors", data.get_total_authors()),
            ("Lines of code", data.get_total_loc()),
            ("Files", data.get_total_files()),
        )
    )
    history = _share_card_history(data)
    assisted, recent = _last_twelve_months(data)
    note = (
        f'<p class="note"><strong>{share_text(assisted, recent)}</strong> of the commits of the '
        "last 12 months name an AI coding assistant.</p>"
        if assisted
        else ""
    )
    name = html.escape(data.project_name)
    return share_card_page(
        f"{data.project_name}: GitStats",
        f'<div class="brand">// GitStats report</div><h1>{name}</h1>'
        f'<p class="sub">{span}</p><dl class="tiles">{tiles}</dl>{history}{note}',
    )


def _share_card_history(data: Any) -> str:
    """Commits per year as a row of columns, or per month for a history of
    less than three years; nothing without commits to show."""
    by_year = getattr(data, "commits_by_year", None)
    by_month = getattr(data, "commits_by_month", None)
    if isinstance(by_year, dict) and by_year and max(by_year) - min(by_year) >= 2:
        keys: list[Any] = list(range(min(by_year), max(by_year) + 1))
        counts, unit = [int(by_year.get(year, 0)) for year in keys], "year"
    elif isinstance(by_month, dict) and by_month:
        keys = month_range(by_month)
        counts, unit = [int(by_month.get(month, 0)) for month in keys], "month"
    else:
        return ""
    top = max(counts) or 1
    columns = "".join(f'<i style="height:{100 * count / top:.1f}%"></i>' for count in counts)
    return (
        f'<div class="history"><div class="columns">{columns}</div><div class="axis">'
        f"<span>{keys[0]}</span><span>commits per {unit}</span><span>{keys[-1]}</span>"
        "</div></div>"
    )
