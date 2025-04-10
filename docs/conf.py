# Read the Docs configuration file
#
# See https://docs.readthedocs.io/en/stable/config-file/v2.html for details
import os
import requests
from datetime import datetime
from pathlib import Path
from sphinx.application import Sphinx

# Required
project = "GitStats"
author = "Xianpeng Shen"
copyright = f"2008 - {datetime.now().year}, Xianpeng Shen"
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
    url = "https://api.github.com/repos/shenxianpeng/gitstats/releases"

    token = os.getenv("GITHUB_TOKEN")
    headers = {"Authorization": f"token {token}"} if token else {}

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Failed to fetch releases: {response.status_code}")
    releases = response.json()

    news_doc = Path(app.srcdir, "changelog.md")

    with open(news_doc, "w") as f:
        f.write("# Changelog\n\n")
        for release in releases:
            f.write(f"## [{release['tag_name']}] - {release['published_at'][:10]}\n")
            f.write(f"{release['body']}\n\n")
            f.write(f"[{release['tag_name']}]: {release['html_url']}\n\n")
