# Copyright (c) 2007-2014 Heikki Hokkanen <hoxu@users.sf.net> & others contributors
# GPLv2 / GPLv3
# Copyright (c) 2024-present Xianpeng Shen <xianpeng.shen@gmail.com>.
# GPLv2 / GPLv3
"""The Badges page: every badge, ready to copy into a README, and the Repo
Wrapped card when the report has one.
"""

import html
import json
from typing import Any

from gitstats import load_config
from gitstats.badge import AI_ASSISTED_LABEL, STYLE_NAMES, ai_assisted_share
from gitstats.markup import _COPY_ICONS, html_header
from gitstats.pages.base import PageWriter

# The Badges page: its sections, and each badge's name and what it shows
BADGES_PAGE_SECTIONS = (
    (
        "At a glance",
        "Several numbers, or the pace of the last year, in one badge.",
        (
            ("summary", "Commits, authors and lines in one badge"),
            ("activity", "Commits per month over the last year"),
            ("health", "Active, quiet or dormant, by the age of the last commit"),
            (
                "ai-assisted",
                "Share of the last 12 months' commits that name an AI coding assistant",
            ),
        ),
    ),
    (
        "Metrics",
        "One number each.",
        (
            ("commits", "Total commits"),
            ("authors", "People who committed"),
            ("lines", "Lines of code"),
            ("files", "Files in the repository"),
            ("last-commit", "Month of the latest commit"),
            ("release", "Newest tag and the tag count"),
            ("active-days", "Days with at least one commit"),
        ),
    ),
)

# Where a snippet points until the report's address is known
BADGES_PLACEHOLDER_URL = "https://<your-report-url>/"


# Keeps the snippets on the Badges page in step with the report URL, style and
# format controls, and copies them. Page data comes from #badge-data.
BADGES_SCRIPT = r"""<script>
(function() {
	const data = JSON.parse(document.getElementById('badge-data').textContent);
	const input = document.getElementById('badge-url');
	const status = document.getElementById('badge-url-status');
	const hints = document.querySelectorAll('[data-url-hint]');
	const live = document.getElementById('badge-live');
	const rows = document.querySelectorAll('.badge-row');
	const formats = { md: 'Markdown', rst: 'reStructuredText', html: 'HTML' };
	const key = 'gitstats-badge-url:' + location.pathname.replace(/[^/]*$/, '');
	let style = data.style;
	let format = 'md';

	// The report's own address: --site-url, else this page's directory when
	// served over http(s); a page opened from a file can't know it.
	const detected = /^https?:$/.test(location.protocol)
		? location.href.replace(/[?#].*$/, '').replace(/[^/]*$/, '')
		: '';
	const auto = data.siteUrl || detected;
	// A full http(s) address, with no second "://" from text pasted onto
	// the end of another address
	function looksValid(url) {
		return /^https?:\/\/[^\/\s?#]+(\/[^\s?#]*)?$/.test(url) && url.indexOf('://') === url.lastIndexOf('://');
	}

	let saved = null;
	try {
		saved = localStorage.getItem(key);
		if (saved !== null && !looksValid(saved)) {
			localStorage.removeItem(key);
			saved = null;
		}
	} catch (e) {}
	input.value = saved !== null ? saved : auto;

	function base() {
		const url = input.value.trim();
		return url ? url.replace(/\/*$/, '/') : data.placeholder;
	}

	// `width` is for the Wrapped card, which is 1080px wide: reStructuredText
	// and HTML can show it smaller, Markdown has no way to say so
	function snippet(image, link, alt, width) {
		if (format === 'rst') {
			return '.. image:: ' + image + '\n   :target: ' + link + '\n   :alt: ' + alt
				+ (width ? '\n   :width: ' + width : '');
		}
		if (format === 'html') {
			return '<a href="' + link + '"><img src="' + image + '" alt="' + alt + '"'
				+ (width ? ' width="' + width + '"' : '') + '></a>';
		}
		return '[![' + alt + '](' + image + ')](' + link + ')';
	}

	function showStatus() {
		const url = input.value.trim();
		let state = 'detected';
		if (!url) state = auto ? 'cleared' : 'missing';
		else if (!looksValid(url)) state = 'invalid';
		else if (url !== auto) state = 'entered';
		else if (data.siteUrl) state = 'site';
		status.textContent = { detected: 'detected', site: '--site-url', entered: 'entered', missing: 'not set', cleared: 'not set', invalid: 'invalid' }[state];
		const warn = state === 'missing' || state === 'cleared' || state === 'invalid';
		status.className = 'badge-url-status' + (warn ? ' is-missing' : state === 'site' ? '' : ' is-ok');
		hints.forEach(function(hint) { hint.hidden = hint.getAttribute('data-url-hint') !== state; });
	}

	function render() {
		const link = base();
		rows.forEach(function(row) {
			const name = row.getAttribute('data-badge');
			const kind = row.getAttribute('data-kind');
			let path = 'badges/' + style + '/' + name + '.svg';
			let alt = 'GitStats ' + name;
			if (kind === 'default') { path = 'badge.svg'; alt = 'GitStats'; }
			if (kind === 'card') { path = name; alt = row.getAttribute('data-alt'); }
			const image = kind === 'endpoint'
				? 'https://img.shields.io/endpoint?url=' + link + 'badges/' + name + '.json'
				: link + path;
			const img = row.querySelector('img');
			if (img && kind === 'style') img.src = path;
			row.querySelector('.badge-code').textContent = snippet(image, link, alt, kind === 'card' ? 480 : 0);
			row.querySelector('.badge-copy').setAttribute('aria-label', 'Copy ' + formats[format] + ' for ' + row.getAttribute('data-title'));
		});
		showStatus();
	}

	function pick(attr, value) {
		document.querySelectorAll('[' + attr + ']').forEach(function(button) {
			button.setAttribute('aria-pressed', String(button.getAttribute(attr) === value));
		});
	}

	document.querySelectorAll('[data-style]').forEach(function(button) {
		button.addEventListener('click', function() {
			style = button.getAttribute('data-style');
			pick('data-style', style);
			render();
		});
	});
	document.querySelectorAll('[data-format]').forEach(function(button) {
		button.addEventListener('click', function() {
			format = button.getAttribute('data-format');
			pick('data-format', format);
			render();
		});
	});

	input.addEventListener('input', render);

	// Once the reader is done typing (the field loses focus, or Enter), a
	// valid address is kept in this browser, so half-typed ones never are.
	// Emptying the field, or typing the detected address again, forgets it
	// and goes back to the detected address.
	input.addEventListener('change', function() {
		const url = input.value.trim();
		try {
			if (!url || url === auto || !looksValid(url)) localStorage.removeItem(key);
			else localStorage.setItem(key, url);
		} catch (e) {}
		if (!url && auto) input.value = auto;
		render();
	});

	// Pages opened from a file have no clipboard API, and a browser may refuse
	// it anyway: fall back to the older copy command
	function legacyCopy(text) {
		const area = document.createElement('textarea');
		area.value = text;
		area.setAttribute('readonly', '');
		area.style.position = 'fixed';
		area.style.opacity = '0';
		document.body.appendChild(area);
		area.select();
		let ok = false;
		try { ok = document.execCommand('copy'); } catch (e) {}
		document.body.removeChild(area);
		return ok;
	}

	function copyText(text) {
		if (navigator.clipboard && window.isSecureContext) {
			return navigator.clipboard.writeText(text).catch(function() {
				if (!legacyCopy(text)) throw new Error('copy failed');
			});
		}
		return legacyCopy(text) ? Promise.resolve() : Promise.reject(new Error('copy failed'));
	}

	rows.forEach(function(row) {
		const button = row.querySelector('.badge-copy');
		const label = button.querySelector('span');
		const code = row.querySelector('.badge-code');
		let timer;
		button.addEventListener('click', function() {
			copyText(code.textContent).then(function() {
				button.classList.add('is-copied');
				label.textContent = 'Copied';
				live.textContent = 'Copied ' + formats[format] + ' for ' + row.getAttribute('data-title');
				clearTimeout(timer);
				timer = setTimeout(function() {
					button.classList.remove('is-copied');
					label.textContent = 'Copy';
				}, 1600);
			}, function() {
				// No clipboard access: select the snippet for a manual copy
				const range = document.createRange();
				range.selectNodeContents(code);
				const selection = window.getSelection();
				selection.removeAllRanges();
				selection.addRange(range);
				live.textContent = 'Snippet selected, press Ctrl+C or Cmd+C to copy';
			});
		});
	});

	render();
})();
</script>"""


class BadgesPage(PageWriter):
    """Writes badges.html."""

    def create_badges_html(self, data: Any, path: str) -> None:
        """Create the Badges page: every badge, ready to copy into a README.

        The snippets need the report's public address, which the report
        cannot know when it is generated. The page's script reads it from
        the address the page is served from, and lets the reader type it in
        (remembered in their browser) when the page is opened from a file.
        """
        conf = load_config()
        style = str(conf.get("badge_style", "") or "flat")
        if style not in STYLE_NAMES:
            style = "flat"
        names = [name for _, _, badges in BADGES_PAGE_SECTIONS for name, _ in badges]
        metric = str(conf.get("badge_metric", "") or "commits")
        if metric not in names:
            metric = "commits"
        link = self.site_url or BADGES_PLACEHOLDER_URL

        def option_buttons(attr: str, options: list[tuple[str, str]], current: str) -> str:
            return "".join(
                f'<button type="button" {attr}="{value}" '
                f'aria-pressed="{"true" if value == current else "false"}">{label}</button>'
                for value, label in options
            )

        def row(kind: str, name: str, title: str, desc: str, image: str, alt: str) -> str:
            if kind == "endpoint":
                preview = f'<span class="badge-json">badges/{name}.json</span>'
            else:
                preview = f'<img src="{image}" alt="{html.escape(alt)}">'
            code = f"[![{alt}]({link}{image})]({link})"
            if kind == "endpoint":
                code = f"[![{alt}](https://img.shields.io/endpoint?url={link}{image})]({link})"
            return (
                f'<div class="badge-row" data-kind="{kind}" data-badge="{name}" '
                f'data-title="{html.escape(title)}">'
                f'<div class="badge-info"><div class="badge-name"><code>{html.escape(title)}</code>'
                f"<span>{html.escape(desc)}</span></div>{preview}</div>"
                f'<pre class="badge-code">{html.escape(code)}</pre>'
                f'<button type="button" class="badge-copy" '
                f'aria-label="Copy Markdown for {html.escape(title)}">{_COPY_ICONS}'
                "<span>Copy</span></button></div>"
            )

        f = self._open_report_file(path, "badges.html")
        self.print_header(f, "badges.html")
        self.print_nav(f, "badges.html")
        f.write("<h1>Badges</h1>")
        f.write(
            '<p class="section-note">Live badges for this report. Pick a style and a format, '
            "then copy a snippet into a README or wiki page: the badge links back here and "
            "updates every time the report is regenerated.</p>"
        )

        f.write(
            '<div class="badge-url"><label for="badge-url">Report URL</label>'
            '<div class="badge-url-field">'
            '<input id="badge-url" type="url" placeholder="https://reports.example.com/my-repo/" '
            f'value="{html.escape(self.site_url)}" spellcheck="false" autocomplete="off">'
            '<span id="badge-url-status" class="badge-url-status is-missing">not set</span></div>'
            '<p class="badge-url-hint" data-url-hint="detected" hidden>Read from this page\'s '
            "address. Change it if the report is also served from another URL.</p>"
            '<p class="badge-url-hint" data-url-hint="site" hidden>Set with '
            "<code>--site-url</code> when the report was generated.</p>"
            '<p class="badge-url-hint" data-url-hint="entered" hidden>Remembered in this '
            "browser.</p>"
            '<p class="badge-url-hint" data-url-hint="cleared" hidden>Enter the address the '
            "report is published at, or leave it empty to use this page's address.</p>"
            '<p class="badge-url-hint" data-url-hint="invalid" hidden>That doesn\'t look like a '
            "web address: use the report's full address, starting with https://. It won't "
            "be remembered.</p>"
            '<p class="badge-url-hint" data-url-hint="missing">This page was opened from a file, '
            "so it can't tell where the report lives. Enter the address it's published at, or "
            "generate the report with <code>--site-url</code> to fill it in.</p></div>"
        )

        f.write(
            '<div class="badge-controls">'
            '<div class="badge-options" role="group" aria-labelledby="badge-style-label">'
            '<span id="badge-style-label" class="badge-options-label">Style</span>'
            '<div class="badge-option-list">'
            + option_buttons("data-style", [(name, name) for name in STYLE_NAMES], style)
            + "</div></div>"
            '<div class="badge-options" role="group" aria-labelledby="badge-format-label">'
            '<span id="badge-format-label" class="badge-options-label">Format</span>'
            '<div class="badge-option-list">'
            + option_buttons(
                "data-format",
                [("md", "Markdown"), ("rst", "reStructuredText"), ("html", "HTML")],
                "md",
            )
            + "</div></div></div>"
        )

        for title, note, badges in BADGES_PAGE_SECTIONS:
            f.write(html_header(2, title))
            f.write(f'<p class="section-note">{note}</p><div class="badge-list">')
            for name, desc in badges:
                if name == "ai-assisted" and ai_assisted_share(data) is None:
                    continue  # data collected without counting them
                alt = AI_ASSISTED_LABEL if name == "ai-assisted" else f"GitStats {name}"
                f.write(row("style", name, name, desc, f"badges/{style}/{name}.svg", alt))
            f.write("</div>")

        f.write(html_header(2, "Other ways to use them"))
        f.write(
            '<p class="section-note">Every badge is a plain SVG file under '
            "<code>badges/&lt;style&gt;/</code>, rewritten each time the report is "
            'generated.</p><div class="badge-list">'
        )
        f.write(
            row(
                "default",
                metric,
                "badge.svg",
                f"The default badge: {metric} in {style}, set by badge_metric and badge_style",
                "badge.svg",
                "GitStats",
            )
        )
        f.write(
            row(
                "endpoint",
                metric,
                "shields.io endpoint",
                "The same numbers as JSON, for shields.io styles and logos",
                f"badges/{metric}.json",
                f"GitStats {metric}",
            )
        )
        f.write("</div>")

        # Badges :: Repo Wrapped, the card written by --wrapped
        f.write(html_header(2, "Repo Wrapped"))
        card = self.wrapped_card
        if card:
            name = html.escape(str(card["file"]))
            year = int(card["year"])
            project = str(getattr(data, "project_name", "") or "repository")
            alt = f"{project} in {year}"
            code = f"[![{alt}]({link}{card['file']})]({link})"
            f.write(
                '<p class="section-note">A card of one year in the repository, written by '
                '<code class="nowrap">--wrapped</code>: show it in a README, or save it and '
                "share it as "
                'an image.</p><div class="badge-list">'
                f'<div class="badge-row" data-kind="card" data-badge="{name}" '
                f'data-alt="{html.escape(alt)}" data-title="{name}">'
                f'<div class="badge-info"><div class="badge-name"><code>{name}</code>'
                f"<span>1080 &times; 1080, {html.escape(str(card.get('theme', '')))} theme</span>"
                f'</div><a class="wrapped-preview" href="{name}">'
                f'<img src="{name}" width="240" height="240" '
                f'alt="Repo Wrapped card for {html.escape(alt)}"></a></div>'
                f'<pre class="badge-code">{html.escape(code)}</pre>'
                f'<button type="button" class="badge-copy" '
                f'aria-label="Copy Markdown for {name}">{_COPY_ICONS}'
                "<span>Copy</span></button></div></div>"
                f'<p class="more-link"><a href="{name}" download>Download SVG &rarr;</a> '
                '&middot; <a href="wrapped.html">Its page, with a PNG to share &rarr;</a></p>'
            )
        else:
            f.write(
                '<p class="section-note">A card of one year in the repository, to show in a '
                "README or share as an image. There is none next to this report: generate it "
                'with <code class="nowrap">--wrapped</code> to get one.</p>'
            )
        f.write('<p id="badge-live" class="visually-hidden" aria-live="polite"></p>')

        page_data = {
            "style": style,
            "siteUrl": self.site_url,
            "placeholder": BADGES_PLACEHOLDER_URL,
        }
        f.write(
            '<script type="application/json" id="badge-data">'
            + json.dumps(page_data).replace("</", "<\\/")
            + "</script>"
        )
        f.write(BADGES_SCRIPT)

        self.print_footer(f)
        f.write("</body></html>")
        f.close()
