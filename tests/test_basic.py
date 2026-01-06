from gitstats import load_config
from gitstats.utils import get_version


def test_load_config_returns_dict():
    cfg = load_config()
    assert isinstance(cfg, dict)


def test_get_version_returns_string():
    # If package is installed, this should return a string; if not,
    # the function may raise PackageNotFoundError when run in some
    # environments, but in CI we'll install the package before tests.
    v = get_version()
    assert isinstance(v, str)
    assert len(v) > 0
