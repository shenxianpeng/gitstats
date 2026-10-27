"""Tests for gitstats.ai_providers – provider setup, retries and API calls.

The SDKs are optional (the ``ai`` extra), so each test installs a stand-in
module in ``sys.modules``; nothing here talks to a network service.
"""

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from gitstats.ai_providers import (
    CLAUDE_DEFAULT_MODEL,
    AIProvider,
    AIProviderError,
    AIProviderFactory,
    AIProviderUnavailableError,
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


class _HTTPError(Exception):
    """An SDK's error for an HTTP status, as openai and anthropic raise them."""

    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


class APITimeoutError(Exception):
    """Named as the SDKs name theirs."""


class APIConnectionError(Exception):
    """Named as the SDKs name theirs."""


def test_provider_retry_settings_default():
    provider = _EchoProvider({})
    assert (provider.max_retries, provider.retry_delay, provider.timeout) == (3, 1, 120)
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
    func = MagicMock(side_effect=[_HTTPError(429), _HTTPError(503), "ok"])
    with patch("gitstats.ai_providers.time.sleep") as sleep:
        assert provider._retry_with_backoff(func) == "ok"
    assert [call.args[0] for call in sleep.call_args_list] == [2, 4]
    assert "Attempt 1 failed, retrying in 2s: HTTP 429" in caplog.text


def test_retry_gives_up_after_the_last_attempt():
    provider = _EchoProvider({"max_retries": 2, "retry_delay": 0})
    func = MagicMock(side_effect=_HTTPError(500))
    with (
        patch("gitstats.ai_providers.time.sleep"),
        pytest.raises(AIProviderError, match="Failed after 2 attempts: HTTP 500") as error,
    ):
        provider._retry_with_backoff(func)
    assert func.call_count == 2
    assert not isinstance(error.value, AIProviderUnavailableError)
    assert isinstance(error.value.__cause__, _HTTPError)


@pytest.mark.parametrize(
    "error",
    [
        _HTTPError(401),  # a wrong key
        _HTTPError(404),  # a wrong model
        TypeError("unexpected keyword argument 'temperature'"),  # a mistake in the call
        ValueError("Expecting value: line 1 column 1 (char 0)"),  # an answer not JSON
        AIProviderError("declined"),
    ],
    ids=["401", "404", "TypeError", "ValueError", "AIProviderError"],
)
def test_a_refused_request_is_not_retried(error):
    provider = _EchoProvider({"max_retries": 3, "retry_delay": 0})
    func = MagicMock(side_effect=error)
    with (
        patch("gitstats.ai_providers.time.sleep") as sleep,
        pytest.raises(AIProviderError) as raised,
    ):
        provider._retry_with_backoff(func)
    assert func.call_count == 1
    sleep.assert_not_called()
    assert str(raised.value) == str(error)  # no "Failed after 1 attempts"
    assert not isinstance(raised.value, AIProviderUnavailableError)


@pytest.mark.parametrize(
    "error", [APITimeoutError("Request timed out."), TimeoutError("timed out")]
)
def test_a_timeout_is_not_retried_and_says_the_service_is_unavailable(error):
    provider = _EchoProvider({"max_retries": 3, "retry_delay": 0, "timeout": 30})
    func = MagicMock(side_effect=error)
    with (
        patch("gitstats.ai_providers.time.sleep") as sleep,
        pytest.raises(AIProviderUnavailableError, match="No answer within 30 seconds"),
    ):
        provider._retry_with_backoff(func)
    assert func.call_count == 1
    sleep.assert_not_called()


@pytest.mark.parametrize(
    "error", [APIConnectionError("Connection error."), ConnectionRefusedError("refused")]
)
def test_a_connection_error_is_retried_then_says_the_service_is_unavailable(error):
    provider = _EchoProvider({"max_retries": 2, "retry_delay": 0})
    func = MagicMock(side_effect=error)
    with (
        patch("gitstats.ai_providers.time.sleep"),
        pytest.raises(AIProviderUnavailableError, match="Failed after 2 attempts"),
    ):
        provider._retry_with_backoff(func)
    assert func.call_count == 2


def test_the_status_of_an_error_comes_from_its_response():
    """requests' HTTPError carries the status on its response, google's
    errors in ``code``; a ``code`` that is a string (openai) is no status."""
    from gitstats.ai_providers import _status_of

    with_response = Exception("503 Server Error")
    with_response.response = types.SimpleNamespace(status_code=503)
    with_code = Exception("quota")
    with_code.code = 429
    with_text_code = Exception("bad key")
    with_text_code.code = "invalid_api_key"
    assert [_status_of(e) for e in (with_response, with_code, with_text_code)] == [503, 429, None]


def test_retry_with_no_attempts_never_calls_the_function():
    """``max_retries`` counts the attempts: with none, the function is not
    called at all and nothing comes back."""
    provider = _EchoProvider({"max_retries": 0, "retry_delay": 0})
    func = MagicMock(return_value="ok")
    with patch("gitstats.ai_providers.time.sleep") as sleep:
        assert provider._retry_with_backoff(func) is None
    func.assert_not_called()
    sleep.assert_not_called()


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
        # gitstats retries, not the SDK as well
        openai.OpenAI.assert_called_once_with(api_key="env-test-key", max_retries=0, timeout=120)

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
        provider = ClaudeProvider({"timeout": 60})
        anthropic.Anthropic.assert_called_once_with(
            api_key="env-test-key", max_retries=0, timeout=60
        )
        assert provider.model == CLAUDE_DEFAULT_MODEL == "claude-opus-5-5"

    @staticmethod
    def _answer(*blocks, stop_reason="end_turn"):
        return types.SimpleNamespace(
            content=[types.SimpleNamespace(type=kind, text=text) for kind, text in blocks],
            stop_reason=stop_reason,
        )

    def test_generate_summary(self, fake_module):
        """The text of the answer, without its thinking; no temperature, which
        anthropic 1.0 and later refuse."""
        client = MagicMock()
        client.messages.create.return_value = self._answer(
            ("thinking", ""), ("text", "A steady "), ("text", "project.")
        )
        fake_module("anthropic", Anthropic=MagicMock(return_value=client))

        provider = ClaudeProvider({"api_key": "test-key", "model": "test-model"})
        assert provider.generate_summary({}, "the prompt") == "A steady project."

        client.beta.messages.create.assert_not_called()  # a model without fallbacks
        request = client.messages.create.call_args.kwargs
        assert request == {
            "model": "test-model",
            "max_tokens": 16000,
            "messages": [{"role": "user", "content": "the prompt"}],
        }

    def test_the_default_model_asks_for_a_fallback(self, fake_module):
        client = MagicMock()
        client.beta.messages.create.return_value = self._answer(("text", "Fine."))
        fake_module("anthropic", Anthropic=MagicMock(return_value=client))

        assert ClaudeProvider({"api_key": "test-key"}).generate_summary({}, "p") == "Fine."
        request = client.beta.messages.create.call_args.kwargs
        assert request["model"] == "claude-opus-5-5"
        assert request["betas"] == ["server-side-fallback-2026-07-01"]
        assert request["fallbacks"] == "default"
        assert "temperature" not in request

    @pytest.mark.parametrize(
        "answer,message",
        [
            ((("text", "No."),), "declined to write this summary"),
            ((("thinking", ""),), "gave no text \\(stop reason: max_tokens\\)"),
        ],
    )
    def test_a_refusal_or_an_empty_answer_fails_once(self, fake_module, answer, message):
        client = MagicMock()
        stop = "refusal" if "declined" in message else "max_tokens"
        client.messages.create.return_value = self._answer(*answer, stop_reason=stop)
        fake_module("anthropic", Anthropic=MagicMock(return_value=client))

        provider = ClaudeProvider({"api_key": "test-key", "model": "test-model"})
        with pytest.raises(AIProviderError, match=message):
            provider.generate_summary({}, "p")
        assert client.messages.create.call_count == 1


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
        model.generate_content.assert_called_once_with(
            "the prompt", request_options={"timeout": 120}
        )


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

        provider = OllamaProvider(
            {"base_url": "http://ollama.test:11434", "model": "test-model", "timeout": 300}
        )
        assert provider.generate_summary({}, "the prompt") == "A local summary."

        requests.post.assert_called_once_with(
            "http://ollama.test:11434/api/generate",
            json={"model": "test-model", "prompt": "the prompt", "stream": False},
            timeout=300,
        )
        response.raise_for_status.assert_called_once_with()

    @staticmethod
    def _failing(status, answer):
        error = Exception(f"{status} Error")
        error.response = types.SimpleNamespace(status_code=status)
        response = MagicMock()
        response.raise_for_status.side_effect = error
        response.json.return_value = answer
        return response

    def test_http_errors_are_retried_then_reported(self, fake_module):
        response = self._failing(500, {})
        requests = fake_module("requests", post=MagicMock(return_value=response))

        provider = OllamaProvider({"max_retries": 2, "retry_delay": 0})
        assert provider.base_url == "http://localhost:11434"
        with (
            patch("gitstats.ai_providers.time.sleep"),
            pytest.raises(AIProviderError, match="Failed after 2 attempts: 500 Error"),
        ):
            provider.generate_summary({}, "the prompt")
        assert requests.post.call_count == 2

    def test_a_model_not_pulled_says_so_and_is_not_retried(self, fake_module):
        response = self._failing(404, {"error": "model 'llama2' not found, try pulling it first"})
        requests = fake_module("requests", post=MagicMock(return_value=response))

        provider = OllamaProvider({"max_retries": 3, "retry_delay": 0})
        with pytest.raises(
            AIProviderError,
            match=r"^Ollama: model 'llama2' not found, try pulling it first \(404 Error\)$",
        ):
            provider.generate_summary({}, "the prompt")
        assert requests.post.call_count == 1

    @pytest.mark.parametrize(
        "answer,message",
        [
            ({"error": "out of memory"}, "^Ollama: out of memory$"),
            ({"model": "x"}, "did not answer as Ollama does"),
            (ValueError("Expecting value"), "did not answer as Ollama does"),  # an HTML page
        ],
        ids=["error", "no response", "not JSON"],
    )
    def test_an_answer_without_a_summary(self, fake_module, answer, message):
        response = MagicMock()
        if isinstance(answer, Exception):
            response.json.side_effect = answer
        else:
            response.json.return_value = answer
        requests = fake_module("requests", post=MagicMock(return_value=response))

        with pytest.raises(AIProviderError, match=message):
            OllamaProvider({"max_retries": 3}).generate_summary({}, "the prompt")
        assert requests.post.call_count == 1


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
