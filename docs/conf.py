# Read the Docs configuration file
#
# See https://docs.readthedocs.io/en/stable/config-file/v2.html for details
import requests
from pathlib import Path
from sphinx.application import Sphinx

# Required
project = "GitStats"
author = "Xianpeng Shen"
copyright = "2024, Xianpeng Shen"
extensions = [
    "myst_parser",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

html_theme = "sphinx_rtd_theme"
html_title = "gitstats"


def setup(app: Sphinx) -> None:
    OWNER = "shenxianpeng"
    REPO = "gitstats"
    URL = f"https://api.github.com/repos/{OWNER}/{REPO}/releases"

    response = requests.get(URL)
    releases = response.json()

    news_doc = Path(app.srcdir, "CHANGELOG.md")

    with open(news_doc, "w") as f:
        f.write("# Changelog\n\n")
        for release in releases:
            f.write(f"## [{release['tag_name']}] - {release['published_at'][:10]}\n")
            f.write(f"{release['body']}\n\n")
            f.write(f"[{release['tag_name']}]: {release['html_url']}\n\n")
