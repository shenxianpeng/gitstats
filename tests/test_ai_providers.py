"""Tests for gitstats.ai_providers – provider setup, retries and API calls.

The SDKs are optional (the ``ai`` extra), so each test installs a stand-in
module in ``sys.modules``; nothing here talks to a network service.
"""

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from gitstats.ai_providers import (
    AIProvider,
    AIProviderError,
    AIProviderFactory,
    ClaudeProvider,
    GeminiProvider,
    OllamaProvider,
    OpenAIProvider,
    _get_model_with_fallback,
)


@pytest.fixture
def fake_module(monkeypatch):
    """Install a stand-in module under ``name`` for the duration of a test."""

    def install(name, **attrs):
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        monkeypatch.setitem(sys.modules, name, module)
        return module

    return install


@pytest.fixture
def missing_module(monkeypatch):
    """Make ``import name`` fail as if the package were not installed."""

    def remove(name):
        monkeypatch.setitem(sys.modules, name, None)

    return remove


@pytest.fixture(autouse=True)
def no_api_keys(monkeypatch):
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(name, raising=False)


# ── _get_model_with_fallback ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "config,expected",
    [
        ({}, "default-model"),
        ({"model": None}, "default-model"),
        ({"model": ""}, "default-model"),
        ({"model": "   "}, "default-model"),
        ({"model": " custom-model "}, "custom-model"),
    ],
)
def test_get_model_with_fallback(config, expected):
    assert _get_model_with_fallback(config, "default-model") == expected


# ── AIProvider retries ───────────────────────────────────────────────────


class _EchoProvider(AIProvider):
    def generate_summary(self, data, prompt):
        return prompt


def test_provider_is_abstract():
    with pytest.raises(TypeError):
        AIProvider({})


def test_provider_retry_settings_default():
    provider = _EchoProvider({})
    assert (provider.max_retries, provider.retry_delay) == (3, 1)
    assert provider.generate_summary({}, "prompt") == "prompt"


def test_retry_returns_the_first_success():
    provider = _EchoProvider({"max_retries": 3, "retry_delay": 1})
    func = MagicMock(return_value="ok")
    with patch("gitstats.ai_providers.time.sleep") as sleep:
        assert provider._retry_with_backoff(func, 1, key="value") == "ok"
    func.assert_called_once_with(1, key="value")
    sleep.assert_not_called()


def test_retry_backs_off_exponentially(caplog):
    provider = _EchoProvider({"max_retries": 3, "retry_delay": 2})
    func = MagicMock(side_effect=[RuntimeError("busy"), RuntimeError("busy"), "ok"])
    with patch("gitstats.ai_providers.time.sleep") as sleep:
        assert provider._retry_with_backoff(func) == "ok"
    assert [call.args[0] for call in sleep.call_args_list] == [2, 4]
    assert "Attempt 1 failed, retrying in 2s: busy" in caplog.text


def test_retry_gives_up_after_the_last_attempt():
    provider = _EchoProvider({"max_retries": 2, "retry_delay": 0})
    func = MagicMock(side_effect=RuntimeError("service down"))
    with (
        patch("gitstats.ai_providers.time.sleep"),
        pytest.raises(AIProviderError, match="Failed after 2 attempts: service down") as error,
    ):
        provider._retry_with_backoff(func)
    assert func.call_count == 2
    assert isinstance(error.value.__cause__, RuntimeError)


# ── OpenAI ───────────────────────────────────────────────────────────────


class TestOpenAIProvider:
    def test_requires_the_package(self, missing_module):
        missing_module("openai")
        with pytest.raises(AIProviderError, match="openai package not installed"):
            OpenAIProvider({"api_key": "test-key"})

    def test_requires_an_api_key(self, fake_module):
        fake_module("openai", OpenAI=MagicMock())
        with pytest.raises(AIProviderError, match="OpenAI API key not found"):
            OpenAIProvider({})

    def test_reads_the_key_from_the_environment(self, fake_module, monkeypatch):
        openai = fake_module("openai", OpenAI=MagicMock())
        monkeypatch.setenv("OPENAI_API_KEY", "env-test-key")
        OpenAIProvider({})
        openai.OpenAI.assert_called_once_with(api_key="env-test-key")

    def test_generate_summary(self, fake_module):
        client = MagicMock()
        choice = MagicMock()
        choice.message.content = "A busy project."
        client.chat.completions.create.return_value.choices = [choice]
        fake_module("openai", OpenAI=MagicMock(return_value=client))

        provider = OpenAIProvider({"api_key": "test-key", "model": "test-model"})
        assert provider.generate_summary({}, "the prompt") == "A busy project."

        request = client.chat.completions.create.call_args.kwargs
        assert request["model"] == "test-model"
        assert request["messages"][0]["role"] == "system"
        assert request["messages"][-1] == {"role": "user", "content": "the prompt"}
        assert request["max_tokens"] == 2000


# ── Claude ───────────────────────────────────────────────────────────────


class TestClaudeProvider:
    def test_requires_the_package(self, missing_module):
        missing_module("anthropic")
        with pytest.raises(AIProviderError, match="anthropic package not installed"):
            ClaudeProvider({"api_key": "test-key"})

    def test_requires_an_api_key(self, fake_module):
        fake_module("anthropic", Anthropic=MagicMock())
        with pytest.raises(AIProviderError, match="Claude API key not found"):
            ClaudeProvider({})

    def test_reads_the_key_from_the_environment(self, fake_module, monkeypatch):
        anthropic = fake_module("anthropic", Anthropic=MagicMock())
        monkeypatch.setenv("ANTHROPIC_API_KEY", "env-test-key")
        ClaudeProvider({})
        anthropic.Anthropic.assert_called_once_with(api_key="env-test-key")

    def test_generate_summary(self, fake_module):
        client = MagicMock()
        block = MagicMock()
        block.text = "A steady project."
        client.messages.create.return_value.content = [block]
        fake_module("anthropic", Anthropic=MagicMock(return_value=client))

        provider = ClaudeProvider({"api_key": "test-key", "model": "test-model"})
        assert provider.generate_summary({}, "the prompt") == "A steady project."

        request = client.messages.create.call_args.kwargs
        assert request["model"] == "test-model"
        assert request["max_tokens"] == 2000
        assert request["messages"] == [{"role": "user", "content": "the prompt"}]


# ── Gemini ───────────────────────────────────────────────────────────────


def _install_genai(fake_module, model):
    genai = fake_module(
        "google.generativeai",
        configure=MagicMock(),
        GenerativeModel=MagicMock(return_value=model),
    )
    fake_module("google", generativeai=genai)
    return genai


class TestGeminiProvider:
    def test_requires_the_package(self, missing_module):
        missing_module("google.generativeai")
        with pytest.raises(AIProviderError, match="google-generativeai package not installed"):
            GeminiProvider({"api_key": "test-key"})

    def test_requires_an_api_key(self, fake_module):
        _install_genai(fake_module, MagicMock())
        with pytest.raises(AIProviderError, match="Gemini API key not found"):
            GeminiProvider({})

    def test_generate_summary(self, fake_module, monkeypatch):
        model = MagicMock()
        model.generate_content.return_value.text = "A growing project."
        genai = _install_genai(fake_module, model)
        monkeypatch.setenv("GOOGLE_API_KEY", "env-test-key")

        provider = GeminiProvider({"model": "test-model"})
        assert provider.generate_summary({}, "the prompt") == "A growing project."

        genai.configure.assert_called_once_with(api_key="env-test-key")
        genai.GenerativeModel.assert_called_once_with("test-model")
        model.generate_content.assert_called_once_with("the prompt")


# ── Ollama ───────────────────────────────────────────────────────────────


class TestOllamaProvider:
    def test_requires_requests(self, missing_module):
        missing_module("requests")
        with pytest.raises(AIProviderError, match="requests package not installed"):
            OllamaProvider({})

    def test_generate_summary_posts_to_the_server(self, fake_module):
        response = MagicMock()
        response.json.return_value = {"response": "A local summary."}
        requests = fake_module("requests", post=MagicMock(return_value=response))

        provider = OllamaProvider({"base_url": "http://ollama.test:11434", "model": "test-model"})
        assert provider.generate_summary({}, "the prompt") == "A local summary."

        requests.post.assert_called_once_with(
            "http://ollama.test:11434/api/generate",
            json={"model": "test-model", "prompt": "the prompt", "stream": False},
            timeout=120,
        )
        response.raise_for_status.assert_called_once_with()

    def test_http_errors_are_retried_then_reported(self, fake_module):
        response = MagicMock()
        response.raise_for_status.side_effect = RuntimeError("500 Server Error")
        fake_module("requests", post=MagicMock(return_value=response))

        provider = OllamaProvider({"max_retries": 2, "retry_delay": 0})
        assert provider.base_url == "http://localhost:11434"
        with (
            patch("gitstats.ai_providers.time.sleep"),
            pytest.raises(AIProviderError, match="Failed after 2 attempts: 500 Server Error"),
        ):
            provider.generate_summary({}, "the prompt")


# ── AIProviderFactory ────────────────────────────────────────────────────


def test_factory_creates_providers_by_name(fake_module):
    fake_module("requests", post=MagicMock())
    assert isinstance(AIProviderFactory.create("Ollama", {}), OllamaProvider)


def test_factory_rejects_unknown_providers():
    with pytest.raises(AIProviderError, match="Unknown AI provider: mystery") as error:
        AIProviderFactory.create("mystery", {})
    assert "Supported providers: openai, claude, gemini, ollama" in str(error.value)


def test_factory_lists_providers():
    assert AIProviderFactory.list_providers() == ["openai", "claude", "gemini", "ollama"]
