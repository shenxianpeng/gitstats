"""Tests for gitstats.ai_summarizer – AISummarizer prompt prep, caching, and provider glue."""

import json
import os
from unittest.mock import Mock, patch

import pytest

from gitstats.ai_summarizer import AISummarizer


def make_summarizer(**config_overrides):
    """Create an AISummarizer with AI disabled by default (no provider init)."""
    config = {"ai_enabled": False, "ai_cache_enabled": True}
    config.update(config_overrides)
    return AISummarizer(config)


# ── __init__ ──────────────────────────────────────────────────────────────


def test_init_without_ai_enabled_has_no_provider():
    summarizer = make_summarizer()
    assert summarizer.provider is None
    assert summarizer.cache_dir is None
    assert summarizer.cache_enabled is True


def test_init_with_ai_enabled_creates_provider():
    with patch("gitstats.ai_summarizer.AIProviderFactory.create") as mock_create:
        mock_provider = Mock()
        mock_create.return_value = mock_provider

        config = {
            "ai_enabled": True,
            "ai_provider": "openai",
            "ai_api_key": "sk-test",
            "ai_model": "gpt-4",
        }
        summarizer = AISummarizer(config)

        assert summarizer.provider is mock_provider
        mock_create.assert_called_once()
        provider_name, provider_config = mock_create.call_args[0]
        assert provider_name == "openai"
        assert provider_config["api_key"] == "sk-test"
        assert provider_config["model"] == "gpt-4"


def test_init_with_ai_enabled_provider_error_propagates():
    with patch("gitstats.ai_summarizer.AIProviderFactory.create") as mock_create:
        mock_create.side_effect = ValueError("boom")
        with pytest.raises(ValueError, match="boom"):
            AISummarizer({"ai_enabled": True, "ai_provider": "openai"})


def test_init_cache_enabled_defaults_true():
    summarizer = AISummarizer({})
    assert summarizer.cache_enabled is True


def test_init_cache_enabled_can_be_disabled():
    summarizer = make_summarizer(ai_cache_enabled=False)
    assert summarizer.cache_enabled is False


# ── _is_bot_account ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "author_name",
    [
        "dependabot[bot]",
        "github-actions[bot]",
        "pre-commit-ci[bot]",
        "renovate[bot]",
        "some-bot@users.noreply.github.com",
        "Greenkeeper",
        "snyk-bot",
        "codecov-commenter",
        "travis-ci",
        "jenkins-deploy",
    ],
)
def test_is_bot_account_matches_bot_patterns(author_name):
    summarizer = make_summarizer()
    assert summarizer._is_bot_account(author_name) is True


@pytest.mark.parametrize(
    "author_name",
    [
        "Alice Smith",
        "Bob Jones",
        "hoxu",
        "Xianpeng Shen",
        "robert",  # contains "bot" only as a substring check false-positive guard
    ],
)
def test_is_bot_account_does_not_match_humans(author_name):
    summarizer = make_summarizer()
    assert summarizer._is_bot_account(author_name) is False


def test_is_bot_account_case_insensitive():
    summarizer = make_summarizer()
    assert summarizer._is_bot_account("DEPENDABOT[BOT]") is True
    assert summarizer._is_bot_account("Github-Actions[Bot]") is True


# ── _filter_human_authors ─────────────────────────────────────────────────


def test_filter_human_authors_removes_bots():
    summarizer = make_summarizer()
    authors = {
        "Alice Smith": {"commits": 10},
        "dependabot[bot]": {"commits": 5},
        "Bob Jones": {"commits": 3},
        "pre-commit-ci[bot]": {"commits": 2},
    }
    result = summarizer._filter_human_authors(authors)
    assert result == {
        "Alice Smith": {"commits": 10},
        "Bob Jones": {"commits": 3},
    }


def test_filter_human_authors_empty_dict():
    summarizer = make_summarizer()
    assert summarizer._filter_human_authors({}) == {}


def test_filter_human_authors_all_bots():
    summarizer = make_summarizer()
    authors = {"dependabot[bot]": {"commits": 1}, "renovate[bot]": {"commits": 2}}
    assert summarizer._filter_human_authors(authors) == {}


def test_filter_human_authors_all_human():
    summarizer = make_summarizer()
    authors = {"Alice": {"commits": 1}, "Bob": {"commits": 2}}
    assert summarizer._filter_human_authors(authors) == authors


# ── _get_lines_of_code ────────────────────────────────────────────────────


def test_get_lines_of_code_prefers_total_lines_of_code():
    summarizer = make_summarizer()
    data = {"total_lines_of_code": 500, "total_lines": 100}
    assert summarizer._get_lines_of_code(data) == 500


def test_get_lines_of_code_falls_back_to_total_lines():
    summarizer = make_summarizer()
    data = {"total_lines": 250}
    assert summarizer._get_lines_of_code(data) == 250


def test_get_lines_of_code_missing_keys_returns_zero():
    summarizer = make_summarizer()
    assert summarizer._get_lines_of_code({}) == 0


def test_get_lines_of_code_zero_is_not_treated_as_missing():
    summarizer = make_summarizer()
    data = {"total_lines_of_code": 0, "total_lines": 999}
    assert summarizer._get_lines_of_code(data) == 0


def test_get_lines_of_code_non_dict_object():
    summarizer = make_summarizer()
    obj = Mock(spec=["total_lines"])
    obj.total_lines = 42
    assert summarizer._get_lines_of_code(obj) == 42


def test_get_lines_of_code_non_dict_object_missing_attr():
    class Empty:
        pass

    summarizer = make_summarizer()
    assert summarizer._get_lines_of_code(Empty()) == 0


# ── _normalize_active_days ────────────────────────────────────────────────


def test_normalize_active_days_from_set():
    summarizer = make_summarizer()
    assert summarizer._normalize_active_days({"2023-01-01", "2023-01-02"}) == 2


def test_normalize_active_days_from_list():
    summarizer = make_summarizer()
    assert summarizer._normalize_active_days(["a", "b", "c"]) == 3


def test_normalize_active_days_from_tuple():
    summarizer = make_summarizer()
    assert summarizer._normalize_active_days(("a", "b")) == 2


def test_normalize_active_days_from_int():
    summarizer = make_summarizer()
    assert summarizer._normalize_active_days(7) == 7


def test_normalize_active_days_from_numeric_string():
    summarizer = make_summarizer()
    assert summarizer._normalize_active_days("15") == 15


def test_normalize_active_days_invalid_value_returns_zero():
    summarizer = make_summarizer()
    assert summarizer._normalize_active_days("not-a-number") == 0
    assert summarizer._normalize_active_days(None) == 0
    assert summarizer._normalize_active_days(object()) == 0


def test_normalize_active_days_empty_collection():
    summarizer = make_summarizer()
    assert summarizer._normalize_active_days([]) == 0
    assert summarizer._normalize_active_days(set()) == 0


# ── _format_top_authors ───────────────────────────────────────────────────


def test_format_top_authors_orders_by_commits_desc():
    summarizer = make_summarizer()
    authors = {
        "Alice": {"commits": 10},
        "Bob": {"commits": 30},
        "Charlie": {"commits": 20},
    }
    result = summarizer._format_top_authors(authors)
    lines = result.split("\n")
    assert lines[0] == "  - Bob: 30 commits"
    assert lines[1] == "  - Charlie: 20 commits"
    assert lines[2] == "  - Alice: 10 commits"


def test_format_top_authors_respects_limit():
    summarizer = make_summarizer()
    authors = {f"Author{i}": {"commits": i} for i in range(10)}
    result = summarizer._format_top_authors(authors, limit=3)
    assert len(result.split("\n")) == 3


def test_format_top_authors_default_limit_is_five():
    summarizer = make_summarizer()
    authors = {f"Author{i}": {"commits": i} for i in range(10)}
    result = summarizer._format_top_authors(authors)
    assert len(result.split("\n")) == 5


def test_format_top_authors_empty_dict():
    summarizer = make_summarizer()
    assert summarizer._format_top_authors({}) == ""


def test_format_top_authors_missing_commits_key_defaults_zero():
    summarizer = make_summarizer()
    authors = {"Alice": {}, "Bob": {"commits": 5}}
    result = summarizer._format_top_authors(authors)
    assert "Bob: 5 commits" in result
    assert "Alice: 0 commits" in result


# ── prepare_index_data ────────────────────────────────────────────────────


def test_prepare_index_data_basic():
    summarizer = make_summarizer()
    data = {
        "total_commits": 100,
        "total_files": 20,
        "total_lines_of_code": 5000,
        "first_commit_date": "2023-01-01",
        "last_commit_date": "2023-12-31",
        "active_days": {"2023-01-01", "2023-06-01"},
        "authors": {
            "Alice": {"commits": 60},
            "Bob": {"commits": 40},
            "dependabot[bot]": {"commits": 5},
        },
    }
    result = summarizer.prepare_index_data(data)

    assert "Total Human Authors: 2" in result
    assert "Bot Accounts: 1" in result
    assert "Total Commits: 100" in result
    assert "Total Files: 20" in result
    assert "Total Lines of Code: 5,000" in result
    assert "First Commit: 2023-01-01" in result
    assert "Last Commit: 2023-12-31" in result
    assert "Active Days: 2" in result
    assert "Alice: 60 commits" in result
    assert "Bob: 40 commits" in result
    assert "dependabot[bot]:" not in result


def test_prepare_index_data_empty_data_uses_defaults():
    summarizer = make_summarizer()
    result = summarizer.prepare_index_data({})

    assert "Total Human Authors: 0" in result
    assert "Total Commits: 0" in result
    assert "Total Files: 0" in result
    assert "Total Lines of Code: 0" in result
    assert "First Commit: Unknown" in result
    assert "Last Commit: Unknown" in result
    assert "Active Days: 0" in result


# ── prepare_activity_data ─────────────────────────────────────────────────


def test_prepare_activity_data_basic():
    summarizer = make_summarizer()
    data = {
        "commits_by_year": {2022: 40, 2023: 60},
        "activity_by_hour_of_day": {9: 10, 14: 25, 20: 5},
        "activity_by_day_of_week": {0: 8, 1: 15, 2: 5},
        "commits_by_timezone": {"+0000": 50, "-0500": 50},
    }
    result = summarizer.prepare_activity_data(data)

    assert "2022: 40 commits" in result
    assert "2023: 60 commits" in result
    assert "Hour 14: 25 commits" in result
    assert "Tuesday: 15 commits" in result
    assert "Timezone Distribution: 2 different timezones" in result


def test_prepare_activity_data_empty_data():
    summarizer = make_summarizer()
    result = summarizer.prepare_activity_data({})

    assert "Peak Hour: N/A" in result
    assert "Peak Day: N/A" in result
    assert "Timezone Distribution: 0 different timezones" in result


# ── prepare_authors_data ──────────────────────────────────────────────────


def test_prepare_authors_data_basic():
    summarizer = make_summarizer()
    data = {
        "authors": {
            "Alice": {"commits": 70, "lines_added": 500, "lines_removed": 100},
            "Bob": {"commits": 30, "lines_added": 200, "lines_removed": 50},
            "github-actions[bot]": {"commits": 15, "lines_added": 10, "lines_removed": 0},
        }
    }
    result = summarizer.prepare_authors_data(data)

    assert "Total Human Authors: 2" in result
    assert "Bot Accounts Excluded: 1" in result
    assert "Total Human Commits: 100" in result
    assert "Top contributor: 70.0% of commits" in result
    assert "Alice: 70 commits, +500/-100 lines" in result
    assert "github-actions" not in result


def test_prepare_authors_data_no_authors():
    summarizer = make_summarizer()
    result = summarizer.prepare_authors_data({"authors": {}})

    assert "Total Human Authors: 0" in result
    assert "Total Human Commits: 0" in result
    assert "Top contributor: 0.0% of commits" in result


def test_prepare_authors_data_missing_authors_key():
    summarizer = make_summarizer()
    result = summarizer.prepare_authors_data({})
    assert "Total Human Authors: 0" in result


# ── prepare_lines_data ────────────────────────────────────────────────────


def test_prepare_lines_data_basic():
    summarizer = make_summarizer()
    data = {
        "total_lines": 1000,
        "total_lines_added": 1500,
        "total_lines_removed": 500,
        "lines_by_date": {"2023-01-01": 100, "2023-06-01": 1000},
        "authors": {
            "Alice": {"lines_added": 800, "lines_removed": 200},
            "Bob": {"lines_added": 700, "lines_removed": 300},
        },
    }
    result = summarizer.prepare_lines_data(data)

    assert "Total Lines of Code: 1,000" in result
    assert "Total Lines Added: 1,500" in result
    assert "Total Lines Removed: 500" in result
    assert "Net Change: +1,000" in result
    assert "Growth from 100 to 1,000 lines" in result
    assert "Alice: +800/-200 (net: +600)" in result


def test_prepare_lines_data_single_date_uses_current_total():
    summarizer = make_summarizer()
    data = {
        "total_lines": 500,
        "total_lines_added": 500,
        "total_lines_removed": 0,
        "lines_by_date": {"2023-01-01": 500},
        "authors": {},
    }
    result = summarizer.prepare_lines_data(data)
    assert "Current: 500 lines" in result


def test_prepare_lines_data_no_dates():
    summarizer = make_summarizer()
    data = {
        "total_lines": 0,
        "total_lines_added": 0,
        "total_lines_removed": 0,
        "lines_by_date": {},
        "authors": {},
    }
    result = summarizer.prepare_lines_data(data)
    assert "Current: 0 lines" in result


def test_prepare_lines_data_missing_keys_defaults():
    summarizer = make_summarizer()
    result = summarizer.prepare_lines_data({})
    assert "Total Lines of Code: 0" in result
    assert "Total Lines Added: 0" in result


# ── caching round-trip ─────────────────────────────────────────────────────


def test_get_cached_summary_returns_none_without_cache_dir():
    summarizer = make_summarizer()
    assert summarizer._get_cached_summary("some_key") is None


def test_get_cached_summary_returns_none_when_cache_disabled(tmp_path):
    summarizer = make_summarizer(ai_cache_enabled=False)
    summarizer.set_cache_dir(str(tmp_path))
    summarizer._save_cached_summary("key1", "cached text")
    assert summarizer._get_cached_summary("key1") is None


def test_save_and_get_cached_summary_round_trip(tmp_path):
    summarizer = make_summarizer()
    summarizer.set_cache_dir(str(tmp_path))

    summarizer._save_cached_summary("my_cache_key", "<p>Hello world</p>")
    result = summarizer._get_cached_summary("my_cache_key")

    assert result == "<p>Hello world</p>"
    cache_file = tmp_path / "my_cache_key.json"
    assert cache_file.exists()
    with open(cache_file, encoding="utf-8") as f:
        payload = json.load(f)
    assert payload == {"summary": "<p>Hello world</p>"}


def test_get_cached_summary_missing_file_returns_none(tmp_path):
    summarizer = make_summarizer()
    summarizer.set_cache_dir(str(tmp_path))
    assert summarizer._get_cached_summary("does_not_exist") is None


def test_get_cached_summary_corrupted_file_returns_none(tmp_path):
    summarizer = make_summarizer()
    summarizer.set_cache_dir(str(tmp_path))

    bad_file = tmp_path / "corrupt_key.json"
    bad_file.write_text("{not valid json", encoding="utf-8")

    assert summarizer._get_cached_summary("corrupt_key") is None


def test_set_cache_dir_creates_directory(tmp_path):
    summarizer = make_summarizer()
    nested = tmp_path / "nested" / "cache"
    summarizer.set_cache_dir(str(nested))
    assert os.path.isdir(nested)


def test_get_cache_key_is_stable_for_same_config():
    summarizer = make_summarizer(ai_provider="openai", ai_model="gpt-4", ai_language="en")
    key1 = summarizer._get_cache_key("index", "abcd1234")
    key2 = summarizer._get_cache_key("index", "abcd1234")
    assert key1 == key2
    assert key1.startswith("index_abcd1234_")


def test_get_cache_key_differs_by_page_type():
    summarizer = make_summarizer()
    key_index = summarizer._get_cache_key("index", "samehash")
    key_lines = summarizer._get_cache_key("lines", "samehash")
    assert key_index != key_lines


# ── generate_summary (AI provider mocked) ─────────────────────────────────


def make_summarizer_with_mock_provider(**config_overrides):
    """Create an AISummarizer with a mocked AI provider, no real network calls."""
    with patch("gitstats.ai_summarizer.AIProviderFactory.create") as mock_create:
        mock_provider = Mock()
        mock_create.return_value = mock_provider
        config = {"ai_enabled": True, "ai_provider": "openai", "ai_api_key": "sk-test"}
        config.update(config_overrides)
        summarizer = AISummarizer(config)
    return summarizer, mock_provider


def test_generate_summary_without_provider_returns_error():
    summarizer = make_summarizer()  # ai_enabled=False -> no provider
    result = summarizer.generate_summary("index", {})
    assert result["error"] == "AI provider not initialized"
    assert result["summary"] == ""


def test_generate_summary_unknown_page_type_returns_error():
    summarizer, mock_provider = make_summarizer_with_mock_provider()
    result = summarizer.generate_summary("unknown_page", {})
    assert "Unknown page type" in result["error"]
    mock_provider.generate_summary.assert_not_called()


def test_generate_summary_calls_provider_and_returns_summary():
    summarizer, mock_provider = make_summarizer_with_mock_provider()
    mock_provider.generate_summary.return_value = "<p>Great progress this quarter.</p>"

    data = {"total_commits": 10, "total_files": 5, "authors": {}}
    result = summarizer.generate_summary("index", data)

    assert result["error"] is None
    assert result["summary"] == "<p>Great progress this quarter.</p>"
    mock_provider.generate_summary.assert_called_once()


def test_generate_summary_uses_cache_when_available(tmp_path):
    summarizer, mock_provider = make_summarizer_with_mock_provider()
    summarizer.set_cache_dir(str(tmp_path))
    mock_provider.generate_summary.return_value = "<p>Fresh summary</p>"

    data = {"total_commits": 10, "total_files": 5, "authors": {}}

    first = summarizer.generate_summary("index", data)
    assert first["summary"] == "<p>Fresh summary</p>"
    mock_provider.generate_summary.assert_called_once()

    mock_provider.generate_summary.reset_mock()
    second = summarizer.generate_summary("index", data)
    assert second["summary"] == "<p>Fresh summary</p>"
    mock_provider.generate_summary.assert_not_called()


def test_generate_summary_force_refresh_bypasses_cache(tmp_path):
    summarizer, mock_provider = make_summarizer_with_mock_provider()
    summarizer.set_cache_dir(str(tmp_path))
    mock_provider.generate_summary.return_value = "<p>Summary v1</p>"

    data = {"total_commits": 10, "total_files": 5, "authors": {}}
    summarizer.generate_summary("index", data)

    mock_provider.generate_summary.return_value = "<p>Summary v2</p>"
    result = summarizer.generate_summary("index", data, force_refresh=True)

    assert result["summary"] == "<p>Summary v2</p>"
    assert mock_provider.generate_summary.call_count == 2


def test_generate_summary_provider_error_is_captured():
    from gitstats.ai_providers import AIProviderError

    summarizer, mock_provider = make_summarizer_with_mock_provider()
    mock_provider.generate_summary.side_effect = AIProviderError("rate limited")

    result = summarizer.generate_summary("index", {"authors": {}})
    assert result["error"] == "rate limited"
    assert result["summary"] == ""


def test_generate_summary_unexpected_exception_is_captured():
    summarizer, mock_provider = make_summarizer_with_mock_provider()
    mock_provider.generate_summary.side_effect = RuntimeError("network exploded")

    result = summarizer.generate_summary("index", {"authors": {}})
    assert "Unexpected error" in result["error"]
    assert "network exploded" in result["error"]
    assert result["summary"] == ""


def test_generate_summary_activity_and_lines_page_types_supported():
    summarizer, mock_provider = make_summarizer_with_mock_provider()
    mock_provider.generate_summary.return_value = "<p>ok</p>"

    activity_result = summarizer.generate_summary(
        "activity", {"commits_by_year": {2023: 5}, "authors": {}}
    )
    lines_result = summarizer.generate_summary("lines", {"total_lines": 10, "authors": {}})

    assert activity_result["error"] is None
    assert lines_result["error"] is None


# ── generate_all_summaries (AI provider mocked) ───────────────────────────


def test_generate_all_summaries_covers_index_activity_lines():
    summarizer, mock_provider = make_summarizer_with_mock_provider()
    mock_provider.generate_summary.return_value = "<p>Looks good.</p>"

    data = {
        "total_commits": 10,
        "total_files": 5,
        "authors": {},
        "commits_by_year": {2023: 10},
        "total_lines": 100,
    }
    summaries = summarizer.generate_all_summaries(data)

    assert set(summaries.keys()) == {"index", "activity", "lines"}
    for page_type in ("index", "activity", "lines"):
        assert summaries[page_type]["error"] is None
        assert summaries[page_type]["summary"] == "<p>Looks good.</p>"
    assert mock_provider.generate_summary.call_count == 3


def test_generate_all_summaries_without_provider_all_error():
    summarizer = make_summarizer()
    data = {"total_commits": 10, "authors": {}}
    summaries = summarizer.generate_all_summaries(data)

    assert set(summaries.keys()) == {"index", "activity", "lines"}
    for page_type in summaries:
        assert summaries[page_type]["error"] == "AI provider not initialized"


def test_generate_all_summaries_force_refresh_propagated(tmp_path):
    summarizer, mock_provider = make_summarizer_with_mock_provider()
    summarizer.set_cache_dir(str(tmp_path))
    mock_provider.generate_summary.return_value = "<p>v1</p>"

    data = {"total_commits": 10, "authors": {}, "commits_by_year": {}, "total_lines": 0}
    summarizer.generate_all_summaries(data)
    assert mock_provider.generate_summary.call_count == 3

    mock_provider.generate_summary.return_value = "<p>v2</p>"
    summaries = summarizer.generate_all_summaries(data, force_refresh=True)
    assert mock_provider.generate_summary.call_count == 6
    for page_type in summaries:
        assert summaries[page_type]["summary"] == "<p>v2</p>"
