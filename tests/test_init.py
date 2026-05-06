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
    assert isinstance(DEFAULT_CONFIG["ai_enabled"], bool)
    assert isinstance(DEFAULT_CONFIG["processes"], int)
    assert isinstance(DEFAULT_CONFIG["ai_language"], str)


# ── load_config ──────────────────────────────────────────────────────────


def test_load_config_defaults():
    """Without a config file, load_config should return defaults."""
    cfg = load_config("nonexistent_file.conf")
    assert cfg["max_authors"] == 20
    assert cfg["ai_enabled"] is False


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
