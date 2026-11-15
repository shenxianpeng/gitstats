"""What is installed is what is here.

The tests run from a checkout, where every folder of ``gitstats/`` imports. An
installed gitstats has only the packages ``pyproject.toml`` lists: one left
out there passes every test and is missing from the wheel.
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _listed_packages():
    with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as f:
        listed = re.search(r"^packages = \[(.*?)\]", f.read(), re.M | re.S)
    assert listed, "pyproject.toml no longer lists its packages under [tool.setuptools]"
    return set(re.findall(r'"([^"]+)"', listed.group(1)))


def _packages_here():
    found = set()
    for folder, _, files in os.walk(os.path.join(ROOT, "gitstats")):
        if "__init__.py" in files:
            found.add(os.path.relpath(folder, ROOT).replace(os.sep, "."))
    return found


def test_every_package_is_listed_for_the_build():
    assert _listed_packages() == _packages_here()
