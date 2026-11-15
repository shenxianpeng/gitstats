# Copyright (c) 2007-2014 Heikki Hokkanen <hoxu@users.sf.net> & others contributors
# GPLv2 / GPLv3
# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
"""Months, years and the quiet periods between them: the arithmetic of the
report's time axes, and how a chart shades a long quiet period and cuts it
down to a short break.
"""

import datetime
from typing import Any


def longest_zero_run(values: list[int]) -> tuple[int, int] | None:
    """Index range (inclusive) of the longest run of zeros, or None if there is none."""
    best: tuple[int, int] | None = None
    start: int | None = None
    for i, value in enumerate(values):
        if value:
            start = None
            continue
        if start is None:
            start = i
        if best is None or i - start > best[1] - best[0]:
            best = (start, i)
    return best


def gap_annotations(labels: list[Any], values: list[int], min_gap: int) -> dict[str, Any]:
    """Chart annotations for the longest stretch without commits.

    When the longest run of empty buckets is at least ``min_gap`` long, it is
    shaded ("No commits 2016 – 2023") and the busiest bucket on each side of
    it is labelled ("2007 · 107"). Otherwise there is nothing to annotate.
    """
    gap = longest_zero_run(values)
    if gap is None or gap[1] - gap[0] + 1 < min_gap:
        return {}
    start, end = gap
    peaks = []
    for lo, hi in ((0, start), (end + 1, len(values))):
        segment = values[lo:hi]
        if segment and max(segment) > 0:
            i = lo + segment.index(max(segment))
            peaks.append({"index": i, "text": f"{labels[i]} \u00b7 {values[i]}"})
    return {
        "bands": [
            {
                "from": start,
                "to": end,
                "text": f"No commits {labels[start]} \u2013 {labels[end]}",
                "short": "no commits",
            }
        ],
        "peaks": peaks,
    }


# A stretch without commits that takes up at least this share of a time axis
# is cut out of it, and drawn as a break this share of what is left of the
# axis wide. Under the first, a stretch is only shaded and keeps its width.
GAP_COLLAPSE_MIN_SHARE = 0.25
GAP_BREAK_SHARE = 0.05


def collapsed_width(total: float, gap: float) -> float | None:
    """How wide a quiet stretch ``gap`` long is drawn on an axis ``total`` long.

    None when it is left alone: it covers less than GAP_COLLAPSE_MIN_SHARE
    of the axis, so the years around it are not short of room. Otherwise
    GAP_BREAK_SHARE of the rest of the axis, in the units of ``total``: a
    repository silent for nine of its twenty years gives those nine the
    width of half a year, and the eleven with commits almost all of the plot.
    """
    if total <= 0 or gap < GAP_COLLAPSE_MIN_SHARE * total:
        return None
    return GAP_BREAK_SHARE * (total - gap)


def collapsed_slots(total: int, gap: int) -> int | None:
    """collapsed_width() for an axis of categories: whole slots, at least one.

    None too when the stretch is no longer than the slots it would be given.
    """
    width = collapsed_width(total, gap)
    if width is None:
        return None
    slots = max(1, round(width))
    return slots if gap > slots else None


def year_span(first: Any, last: Any) -> str:
    """The years from ``first`` to ``last`` as a short axis label: "2016\u201324".

    Each is a year or anything that starts with one, such as "2016-01".
    """
    a, b = str(first)[:4], str(last)[:4]
    if a == b:
        return a
    return f"{a}\u2013{b[2:] if a[:2] == b[:2] else b}"


def collapse_gap_categories(
    labels: list[Any], datasets: list[dict[str, Any]], annotations: dict[str, Any]
) -> tuple[list[Any], list[dict[str, Any]], dict[str, Any]]:
    """Cut a long shaded stretch out of a category axis.

    When the one band in ``annotations`` is long enough (collapsed_slots()),
    its categories are replaced by a few slots named after the whole stretch
    ("2016 \u2013 2023"), which keep the values the stretch began with: zeros
    on a bar chart, the level a cumulative line stays at. The band is narrowed
    to those slots and flagged ``collapsed``, with the ``axis`` label the
    chart draws under it, and the peaks after it move up. Everything is
    returned unchanged when there is nothing to collapse.
    """
    bands = annotations.get("bands") or []
    if len(bands) != 1:
        return labels, datasets, annotations
    band = bands[0]
    start, end = band["from"], band["to"]
    gap = end - start + 1
    slots = collapsed_slots(len(labels), gap)
    if slots is None:
        return labels, datasets, annotations
    cut = gap - slots

    name = f"{labels[start]} \u2013 {labels[end]}"
    new_labels = [*labels[:start], *([name] * slots), *labels[end + 1 :]]
    new_datasets = []
    for dataset in datasets:
        entry = dict(dataset)
        for key in ("data", "notes"):
            if isinstance(entry.get(key), list):
                entry[key] = entry[key][: start + slots] + entry[key][end + 1 :]
        new_datasets.append(entry)
    new_annotations = {
        **annotations,
        "bands": [
            {
                **band,
                "to": start + slots - 1,
                "collapsed": True,
                "axis": year_span(labels[start], labels[end]),
            }
        ],
    }
    if "peaks" in annotations:
        new_annotations["peaks"] = [
            {**peak, "index": peak["index"] - cut} if peak["index"] > end else peak
            for peak in annotations["peaks"]
        ]
    return new_labels, new_datasets, new_annotations


def collapse_gap_time(
    stamps: list[int], annotations: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, int] | None]:
    """Cut a long shaded stretch out of a time axis.

    ``stamps`` are the chart's x values in milliseconds, in order. When the
    one band in ``annotations`` is long enough (collapsed_width()), returns
    the annotations with that band narrowed to the break and flagged
    ``collapsed``, and the gap ``{"from", "to", "width"}`` the chart's
    squeezeTime() needs. Otherwise the annotations as they were, and None.
    """
    bands = annotations.get("bands") or []
    if len(bands) != 1 or len(stamps) < 2:
        return annotations, None
    band = bands[0]
    if band["from"] < stamps[0] or band["to"] > stamps[-1]:
        return annotations, None  # not a stretch between two of the chart's points
    width = collapsed_width(stamps[-1] - stamps[0], band["to"] - band["from"])
    if width is None:
        return annotations, None
    gap = {"from": band["from"], "to": band["to"], "width": round(width)}
    first = datetime.datetime.fromtimestamp(band["from"] / 1000)
    # the band ends on the first day after its last quiet month
    last = datetime.datetime.fromtimestamp(band["to"] / 1000) - datetime.timedelta(days=1)
    collapsed = {
        **band,
        "to": band["from"] + gap["width"],
        "collapsed": True,
        "axis": year_span(first.year, last.year),
    }
    return {**annotations, "bands": [collapsed]}, gap


def quiet_months(data: Any, min_months: int = 12) -> tuple[str, str] | None:
    """First and last "YYYY-MM" of the longest stretch without commits, when it
    lasts at least ``min_months`` (the monthly chart's threshold), else None."""
    by_month = getattr(data, "commits_by_month", None)
    if not isinstance(by_month, dict) or not by_month:
        return None
    months = month_range(by_month)
    gap = longest_zero_run([by_month.get(m, 0) for m in months])
    if gap is None or gap[1] - gap[0] + 1 < min_months:
        return None
    return months[gap[0]], months[gap[1]]


def quiet_band(first: str, last: str, start: Any, end: Any) -> dict[str, Any]:
    """A gsAnnotations band from ``start`` to ``end`` captioned with the quiet months."""
    return {
        "from": start,
        "to": end,
        "text": f"No commits {first} \u2013 {last}",
        "short": "no commits",
    }


def time_gap_annotations(data: Any) -> dict[str, Any]:
    """Annotations for a time-axis chart: the longest stretch without commits,
    shaded from its first month's first day to the day after its last month
    (timestamps in milliseconds, like the chart's x values)."""
    quiet = quiet_months(data)
    if quiet is None:
        return {}
    first, last = quiet
    year, month = map(int, first.split("-"))
    start = datetime.datetime(year, month, 1)
    year, month = map(int, last.split("-"))
    end = datetime.datetime(year + month // 12, month % 12 + 1, 1)
    return {
        "bands": [
            quiet_band(first, last, int(start.timestamp() * 1000), int(end.timestamp() * 1000))
        ]
    }


def month_range(months: Any) -> list[str]:
    """Return every ``"YYYY-MM"`` month from the earliest to the latest in ``months``.

    Monthly charts use a category axis, so months without commits must be
    present (as zeros) or a long quiet period collapses to nothing.
    """
    keys = sorted(months)
    if not keys:
        return []
    year, month = map(int, keys[0].split("-"))
    last = tuple(map(int, keys[-1].split("-")))
    result = []
    while (year, month) <= last:
        result.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return result


def months_back(month: str, count: int) -> str:
    """The "YYYY-MM" month ``count`` months before ``month``."""
    year, number = map(int, month.split("-"))
    year, number = divmod(year * 12 + number - 1 - count, 12)
    return f"{year:04d}-{number + 1:02d}"


def sum_since(by_month: dict[str, int], month: str) -> int:
    """What ``by_month`` ("YYYY-MM" -> count) adds up to from ``month`` on."""
    return sum(count for key, count in by_month.items() if key >= month)
