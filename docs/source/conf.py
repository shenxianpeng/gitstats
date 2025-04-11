# Read the Docs configuration file
#
# See https://docs.readthedocs.io/en/stable/config-file/v2.html for details
from datetime import datetime

# Required
project = "GitStats"
author = "Xianpeng Shen"
copyright = f"2008 - {datetime.now().year}, Xianpeng Shen"

source_suffix = {
    ".rst": "restructuredtext",
}

html_theme = "sphinx_rtd_theme"
html_title = "gitstats"
html_short_title = "gitstats"

exclude_patterns = ["source/TODO.md"]
