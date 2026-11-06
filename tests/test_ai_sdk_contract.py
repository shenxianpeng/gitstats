"""The AI SDKs' surface, as ``gitstats.ai_providers`` reaches for it.

``tests/test_ai_providers.py`` puts stand-in modules in ``sys.modules``, so it
passes whatever the installed packages happen to look like. These tests run
against the packages the ``ai`` extra installs, and fail when one of them
renames or drops something the providers use. That is how the Claude provider
came to be broken against current SDKs (#357), and Dependabot moves these pins
in ``uv.lock`` every week, so something has to read them.

Nothing here reaches a network: the clients are only built, and the request and
response surfaces are read off the SDKs themselves. Every test is skipped where
the ``ai`` extra is not installed, which is every job in
``.github/workflows/test.yml`` but ``ai-sdk-contract``.
"""

import inspect

import pytest

from gitstats.ai_providers import CLAUDE_DEFAULT_MODEL, AIProviderFactory

# The providers read a key from the config before they build a client; no
# request is ever made with it.
KEY = "not-a-real-key"
TIMEOUT = 7


def assert_takes(call, *names):
    """Fail unless ``call`` accepts each of ``names`` as a keyword argument."""
    parameters = inspect.signature(call).parameters
    if any(p.kind is p.VAR_KEYWORD for p in parameters.values()):
        return  # it takes **kwargs, so it accepts whatever it is given
    missing = [name for name in names if name not in parameters]
    assert not missing, f"{call.__qualname__} no longer takes {', '.join(missing)}"


def assert_has_fields(model, *names):
    """Fail unless the pydantic ``model`` still carries each of ``names``."""
    missing = [name for name in names if name not in model.model_fields]
    assert not missing, f"{model.__name__} no longer has {', '.join(missing)}"


class TestOpenAI:
    """``OpenAIProvider`` against the installed ``openai``."""

    def test_the_client_takes_our_retry_and_timeout_settings(self):
        pytest.importorskip("openai")
        provider = AIProviderFactory.create("openai", {"api_key": KEY, "timeout": TIMEOUT})
        # gitstats retries itself, so the SDK must be able to stand down
        assert provider.client.max_retries == 0
        assert provider.client.timeout == TIMEOUT

    def test_the_completions_call_takes_what_the_provider_passes(self):
        pytest.importorskip("openai")
        provider = AIProviderFactory.create("openai", {"api_key": KEY})
        assert_takes(
            provider.client.chat.completions.create,
            "model",
            "messages",
            "temperature",
            "max_tokens",
        )

    def test_the_answer_is_still_read_the_same_way(self):
        chat = pytest.importorskip("openai.types.chat")
        completion = pytest.importorskip("openai.types.chat.chat_completion")
        # response.choices[0].message.content
        assert_has_fields(chat.ChatCompletion, "choices")
        assert_has_fields(completion.Choice, "message")
        assert_has_fields(chat.ChatCompletionMessage, "content")


class TestClaude:
    """``ClaudeProvider`` against the installed ``anthropic``."""

    def test_the_client_takes_our_retry_and_timeout_settings(self):
        pytest.importorskip("anthropic")
        provider = AIProviderFactory.create("claude", {"api_key": KEY, "timeout": TIMEOUT})
        assert provider.client.max_retries == 0
        assert provider.client.timeout == TIMEOUT

    def test_the_messages_call_takes_what_the_provider_passes(self):
        pytest.importorskip("anthropic")
        provider = AIProviderFactory.create("claude", {"api_key": KEY})
        assert_takes(provider.client.messages.create, "model", "max_tokens", "messages")

    def test_the_beta_call_still_takes_the_server_side_fallback(self):
        pytest.importorskip("anthropic")
        provider = AIProviderFactory.create(
            "claude", {"api_key": KEY, "model": CLAUDE_DEFAULT_MODEL}
        )
        # the default model asks the API to hand a declined request on
        assert_takes(
            provider.client.beta.messages.create,
            "model",
            "max_tokens",
            "messages",
            "betas",
            "fallbacks",
        )

    def test_the_answer_is_still_read_the_same_way(self):
        types = pytest.importorskip("anthropic.types")
        # response.stop_reason, and the text blocks of response.content
        assert_has_fields(types.Message, "stop_reason", "content")
        assert_has_fields(types.TextBlock, "type", "text")


class TestGemini:
    """``GeminiProvider`` against the installed ``google-generativeai``."""

    def test_the_model_is_configured_and_built_the_same_way(self):
        pytest.importorskip("google.generativeai")
        provider = AIProviderFactory.create("gemini", {"api_key": KEY})
        assert provider.model is not None

    def test_the_generate_call_takes_the_request_options(self):
        pytest.importorskip("google.generativeai")
        provider = AIProviderFactory.create("gemini", {"api_key": KEY})
        # the timeout rides in request_options, not as a keyword of its own
        assert_takes(provider.model.generate_content, "request_options")

    def test_the_answer_is_still_read_the_same_way(self):
        types = pytest.importorskip("google.generativeai.types")
        # response.text
        assert isinstance(getattr(types.GenerateContentResponse, "text", None), property)


class TestOllama:
    """``OllamaProvider`` against the installed ``requests``."""

    def test_the_post_takes_what_the_provider_passes(self):
        pytest.importorskip("requests")
        provider = AIProviderFactory.create("ollama", {})
        assert_takes(provider.requests.post, "json", "timeout")

    def test_the_answer_is_still_read_the_same_way(self):
        requests = pytest.importorskip("requests")
        response = requests.Response()
        # response.json() and response.raise_for_status()
        assert callable(response.json)
        assert callable(response.raise_for_status)


def test_every_provider_the_factory_lists_is_covered_here():
    """A fifth provider should arrive with its own contract tests."""
    covered = {"openai", "claude", "gemini", "ollama"}
    assert set(AIProviderFactory.list_providers()) == covered
