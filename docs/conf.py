# Read the Docs configuration file
#
# See https://docs.readthedocs.io/en/stable/config-file/v2.html for details
import requests
from datetime import datetime
from pathlib import Path
from sphinx.application import Sphinx

# Required
project = "GitStats"
author = "Xianpeng Shen"
copyright = f"{datetime.now().year}, Xianpeng Shen"
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
    URL = f"https://api.github.com/repos/shenxianpeng/gitstats/releases"

    response = requests.get(URL)
    print("===============")
    print(response)
    print("===============")
    releases = response.json()

    news_doc = Path(app.srcdir, "CHANGELOG.md")

    with open(news_doc, "w") as f:
        f.write("# Changelog\n\n")
        for release in releases:
            print(release)  
            f.write(f"## [{release['tag_name']}] - {release['published_at'][:10]}\n")
            f.write(f"{release['body']}\n\n")
            f.write(f"[{release['tag_name']}]: {release['html_url']}\n\n")
