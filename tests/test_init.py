"""Tests for gitstats.__init__ – config loading, i18n, constants."""

import os
import tempfile

import pytest

from gitstats import (
    DEFAULT_CONFIG,
    ON_LINUX,
    WEEKDAYS,
    get_i18n_text,
    load_config,
)

# ── Constants ────────────────────────────────────────────────────────────


def test_weekdays():
    assert list(WEEKDAYS) == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def test_on_linux_is_bool():
    assert isinstance(ON_LINUX, bool)


# ── DEFAULT_CONFIG ───────────────────────────────────────────────────────


def test_default_config_keys():
    """Verify all expected keys exist in DEFAULT_CONFIG."""
    expected_keys = {
        "max_domains",
        "max_ext_length",
        "style",
        "max_authors",
        "max_tags_authors",
        "max_authors_list",
        "authors_top",
        "commit_begin",
        "commit_end",
        "linear_linestats",
        "project_name",
        "processes",
        "start_date",
        "end_date",
        "authors",
        "exclude_exts",
        "badge_metric",
        "badge_label",
        "badge_color",
        "badge_style",
        "site_url",
        "share_card",
        "ai_enabled",
        "ai_provider",
        "ai_api_key",
        "ai_model",
        "ai_language",
        "ai_cache_enabled",
        "ai_max_retries",
        "ai_retry_delay",
        "ollama_base_url",
    }
    assert set(DEFAULT_CONFIG.keys()) == expected_keys


def test_default_config_types():
    """Verify config values have correct types."""
    assert isinstance(DEFAULT_CONFIG["max_domains"], int)
    assert isinstance(DEFAULT_CONFIG["max_authors"], int)
    assert isinstance(DEFAULT_CONFIG["max_authors_list"], int)
    assert isinstance(DEFAULT_CONFIG["ai_enabled"], bool)
    assert isinstance(DEFAULT_CONFIG["processes"], int)
    assert isinstance(DEFAULT_CONFIG["ai_language"], str)


# ── load_config ──────────────────────────────────────────────────────────


def test_load_config_defaults():
    """Without a config file, load_config should return defaults."""
    cfg = load_config("nonexistent_file.conf")
    assert cfg["max_authors"] == 20
    assert cfg["ai_enabled"] is False


def test_load_config_without_a_file_starts_from_the_defaults(tmp_path):
    """A first load with no config file on disk caches a copy of the defaults."""
    import gitstats

    gitstats._config = None
    cfg = load_config(str(tmp_path / "missing.conf"))
    assert cfg == gitstats.DEFAULT_CONFIG
    assert cfg is not gitstats.DEFAULT_CONFIG
    assert load_config() is cfg


def test_load_config_from_file():
    """Load config from a temporary file."""
    content = """[gitstats]
max_authors = 10
ai_enabled = true
project_name = test-project
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
        f.write(content)
        path = f.name

    try:
        # Reset config cache
        import gitstats

        gitstats._config = None

        cfg = load_config(path)
        assert cfg["max_authors"] == 10
        assert cfg["ai_enabled"] is True
        assert cfg["project_name"] == "test-project"
        # defaults still present
        assert cfg["max_domains"] == 10
    finally:
        gitstats._config = None
        os.unlink(path)


def test_load_config_type_coercion():
    """Numeric and boolean strings should be coerced."""
    content = """[gitstats]
max_authors = 5
processes = 16
linear_linestats = 0
ai_enabled = true
ai_cache_enabled = false
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
        f.write(content)
        path = f.name

    try:
        import gitstats

        gitstats._config = None

        cfg = load_config(path)
        assert cfg["max_authors"] == 5
        assert isinstance(cfg["max_authors"], int)
        assert cfg["processes"] == 16
        assert isinstance(cfg["processes"], int)
        assert cfg["ai_enabled"] is True
        assert cfg["ai_cache_enabled"] is False
    finally:
        gitstats._config = None
        os.unlink(path)


def test_load_config_negative_integer():
    """max_tags_authors = -1 is the documented way to show every tag author."""
    content = """[gitstats]
max_tags_authors = -1
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
        f.write(content)
        path = f.name

    try:
        import gitstats

        gitstats._config = None

        cfg = load_config(path)
        assert cfg["max_tags_authors"] == -1
        assert isinstance(cfg["max_tags_authors"], int)
    finally:
        gitstats._config = None
        os.unlink(path)


@pytest.mark.parametrize(
    "value, expected",
    [
        ("5", 5),
        ("-1", -1),
        ("0", 0),
        ("true", True),
        ("False", False),
        ("HEAD", "HEAD"),
        ("-", "-"),
        ("1.5", "1.5"),
        ("2024-01-01", "2024-01-01"),
    ],
)
def test_parse_config_value(value, expected):
    from gitstats import parse_config_value

    assert parse_config_value(value) == expected


@pytest.mark.parametrize(
    "key, value, expected",
    [
        # a string setting stays a string, digits and all: a short hash
        ("commit_end", "1103142", "1103142"),
        ("commit_begin", "10", "10"),
        ("project_name", "true", "true"),
        ("badge_label", "-1", "-1"),
        # an integer setting is an integer
        ("processes", "4", 4),
        ("max_tags_authors", "-1", -1),
        ("linear_linestats", "0", 0),
        # a boolean one, as ConfigParser.getboolean() reads it
        ("ai_enabled", "true", True),
        ("ai_enabled", "Yes", True),
        ("share_card", "on", True),
        ("share_card", "1", True),
        ("ai_cache_enabled", "false", False),
        ("ai_cache_enabled", "no", False),
        ("ai_cache_enabled", "off", False),
        ("ai_cache_enabled", "0", False),
        # a key gitstats does not know is guessed at, as before
        ("unknown", "5", 5),
        ("unknown", "true", True),
        ("unknown", "abc", "abc"),
    ],
)
def test_parse_config_value_takes_the_type_of_the_default(key, value, expected):
    from gitstats import parse_config_value

    parsed = parse_config_value(value, key)
    assert parsed == expected
    assert type(parsed) is type(expected)


@pytest.mark.parametrize(
    "key, value, message",
    [
        ("processes", "abc", "processes must be a whole number, not 'abc'"),
        ("max_authors", "1.5", "max_authors must be a whole number, not '1.5'"),
        ("ai_enabled", "maybe", "ai_enabled must be true or false, not 'maybe'"),
    ],
)
def test_parse_config_value_of_the_wrong_type(key, value, message):
    from gitstats import parse_config_value

    with pytest.raises(ValueError, match=message):
        parse_config_value(value, key)


def _load(tmp_path, text):
    import gitstats

    path = tmp_path / "gitstats.conf"
    path.write_text(text, encoding="utf-8")
    gitstats._config = None
    try:
        return load_config(str(path)), list(gitstats.config_errors), str(path)
    finally:
        gitstats._config = None


def test_load_config_takes_a_percent_sign_as_it_is(tmp_path):
    cfg, errors, _ = _load(tmp_path, "[gitstats]\nbadge_label = 100% done\nproject_name = %(x)s\n")
    assert cfg["badge_label"] == "100% done"
    assert cfg["project_name"] == "%(x)s"
    assert errors == []


@pytest.mark.parametrize("text", ["[other]\nkey = value\n", "processes = 2\n", ""])
def test_load_config_without_a_gitstats_section(tmp_path, caplog, text):
    """The defaults, and a warning: no KeyError when gitstats is imported."""
    with caplog.at_level("WARNING", logger="gitstats"):
        cfg, errors, path = _load(tmp_path, text)
    assert cfg == DEFAULT_CONFIG
    assert errors == []
    assert f"{path} has no [gitstats] section" in caplog.text


def test_load_config_keeps_the_default_of_a_value_of_the_wrong_type(tmp_path):
    cfg, errors, path = _load(tmp_path, "[gitstats]\nprocesses = abc\nmax_authors = 7\n")
    assert cfg["processes"] == DEFAULT_CONFIG["processes"]
    assert cfg["max_authors"] == 7
    assert errors == [f"{path}: processes must be a whole number, not 'abc'"]


@pytest.mark.parametrize(
    "text",
    ["[gitstats]\nprocesses = 2\nprocesses = 3\n", "[gitstats]\nnot a setting\n"],
)
def test_load_config_of_a_malformed_file(tmp_path, text):
    cfg, errors, path = _load(tmp_path, text)
    assert cfg == DEFAULT_CONFIG
    assert len(errors) == 1 and errors[0].startswith(f"{path}: ")


def test_load_config_that_is_not_utf8(tmp_path):
    import gitstats

    path = tmp_path / "gitstats.conf"
    path.write_bytes(b"[gitstats]\nproject_name = \xff\n")
    gitstats._config = None
    try:
        assert load_config(str(path)) == DEFAULT_CONFIG
        assert gitstats.config_errors[0].startswith(f"{path}: ")
    finally:
        gitstats._config = None


# ── get_i18n_text ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "lang,key",
    [
        ("en", "ai_insights_title"),
        ("zh", "ai_insights_title"),
        ("ja", "ai_insights_title"),
        ("ko", "ai_insights_title"),
        ("es", "ai_insights_title"),
        ("fr", "ai_insights_title"),
        ("de", "ai_insights_title"),
    ],
)
def test_get_i18n_text_all_languages(lang, key):
    """Every supported language should return a non-empty string."""
    result = get_i18n_text(key, lang)
    assert result
    assert isinstance(result, str)


def test_get_i18n_text_unknown_language_fallsback_to_en():
    result = get_i18n_text("ai_insights_title", "xx")
    assert result == get_i18n_text("ai_insights_title", "en")


def test_get_i18n_text_unknown_key_fallsback():
    result = get_i18n_text("nonexistent_key", "en")
    assert result == "nonexistent_key"  # key itself is fallback


def test_get_i18n_text_chinese_variant():
    """zh-TW, zh-CN should all map to zh."""
    result_cn = get_i18n_text("ai_insights_title", "zh-CN")
    result_tw = get_i18n_text("ai_insights_title", "zh-TW")
    result_zh = get_i18n_text("ai_insights_title", "zh")
    assert result_cn == result_zh
    assert result_tw == result_zh


def test_get_i18n_text_bot_note():
    result = get_i18n_text("bot_note", "en")
    assert "dependabot" in result
    assert "<strong>" in result
