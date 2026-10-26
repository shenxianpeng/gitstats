# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
"""Make the HTML an AI model writes safe to put in a report page.

The model is asked for a few paragraphs and lists in HTML, about data that
holds author names and commit subjects: whoever commits to the repository
can steer what it answers. Its answer keeps the paragraphs, lists and
emphasis it was asked for and nothing else: no other element, no attribute
(``href``, ``style``, ``onclick``...), no comment, and the text of a
``<script>`` or ``<style>`` is dropped with it. All other text is escaped.
"""

from __future__ import annotations

import html
from html.parser import HTMLParser

# what the prompt asks the model to use, and <ol> and <code>
ALLOWED_TAGS = frozenset({"p", "ul", "ol", "li", "strong", "em", "code"})
# elements whose content is code or markup, not text to show
_DROPPED_WITH_CONTENT = frozenset({"script", "style"})


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        # the allowed elements open at this point, innermost last
        self.open: list[str] = []
        # inside a <script> or <style>: how many are open
        self.dropping = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _DROPPED_WITH_CONTENT:
            self.dropping += 1
        elif not self.dropping and tag in ALLOWED_TAGS:
            self.out.append(f"<{tag}>")
            self.open.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # <p/> and <script/> open nothing
        pass

    def handle_endtag(self, tag: str) -> None:
        if tag in _DROPPED_WITH_CONTENT:
            self.dropping = max(self.dropping - 1, 0)
        elif not self.dropping and tag in self.open:
            # close what is still open inside it, then the element
            start = len(self.open) - 1 - self.open[::-1].index(tag)
            self.out.extend(f"</{inner}>" for inner in reversed(self.open[start:]))
            del self.open[start:]

    def handle_data(self, data: str) -> None:
        if not self.dropping:
            self.out.append(html.escape(data, quote=False))


def sanitize_ai_html(text: str) -> str:
    """Keep the ``<p>``, ``<ul>``, ``<ol>``, ``<li>``, ``<strong>``, ``<em>``
    and ``<code>`` of ``text``, without attributes, and escape the rest of it.

    ``<script>`` and ``<style>`` go with their content; other elements and
    comments go, their text stays. Every element left open is closed, so
    the answer cannot change the page around it.
    """
    parser = _Sanitizer()
    parser.feed(text)
    parser.close()
    parser.out.extend(f"</{tag}>" for tag in reversed(parser.open))
    return "".join(parser.out)
