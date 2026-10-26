"""Tests for gitstats.safe_html – what is left of the HTML an AI model writes."""

import pytest

from gitstats.safe_html import sanitize_ai_html


@pytest.mark.parametrize(
    "text, expected",
    [
        # what the prompt asks for comes through
        (
            "<ul><li><strong>Key</strong>: <em>42%</em> in <code>src/</code></li></ul><p>ok</p>",
            "<ul><li><strong>Key</strong>: <em>42%</em> in <code>src/</code></li></ul><p>ok</p>",
        ),
        ("<ol><li>one</li></ol>", "<ol><li>one</li></ol>"),
        # a script or a style goes, and what it holds
        ("<p>ok</p><script src=https://evil.example/x.js></script>", "<p>ok</p>"),
        ("<SCRIPT>alert(1)</SCRIPT>after", "after"),
        ("<style>body{display:none}</style><p>ok</p>", "<p>ok</p>"),
        ("<script>never closed <p>x</p>", ""),
        ("<script/>ok", "ok"),
        ("</script>ok", "ok"),
        # attributes go, other elements go and leave their text
        ('<p onclick="steal()" style="x">hi</p>', "<p>hi</p>"),
        ('<a href="javascript:steal()">link</a>', "link"),
        ("<img src=x onerror=alert(1)>", ""),
        ("<iframe src=https://evil.example></iframe>text", "text"),
        ("<p>x<br/>y</p>", "<p>xy</p>"),
        ("<!-- note --><p>ok</p>", "<p>ok</p>"),
        # text is escaped, entities stay what they say
        ("a < b & c", "a &lt; b &amp; c"),
        ("&lt;script&gt;", "&lt;script&gt;"),
        # what is left open is closed; a stray end tag goes
        ("<p>open <em>em", "<p>open <em>em</em></p>"),
        ("<ul><li>a</ul></li>", "<ul><li>a</li></ul>"),
        ("</p>stray", "stray"),
        ("", ""),
    ],
)
def test_sanitize_ai_html(text, expected):
    assert sanitize_ai_html(text) == expected
