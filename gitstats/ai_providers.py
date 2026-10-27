"""
AI Provider abstraction layer for GitStats.

Supports multiple AI services: OpenAI, Claude, Gemini, and Ollama (local LLM).
"""

import logging
import os
import time
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger("gitstats")


def _get_model_with_fallback(config: dict[str, Any], default: str) -> str:
    """
    Get model from config, treating empty/whitespace-only values as unset.

    Args:
        config: Configuration dictionary
        default: Default model name to use if config value is empty/whitespace

    Returns:
        Model name from config or default if config value is empty/whitespace
    """
    model = config.get("model", default)
    # Treat empty or whitespace-only strings as unset
    return model.strip() if model and model.strip() else default


class AIProviderError(Exception):
    """Base exception for AI provider errors."""

    pass


class AIProviderUnavailableError(AIProviderError):
    """The service did not answer in time, or could not be reached: asking it
    for the next summary would most likely wait as long again."""


def _status_of(error: Exception) -> int | None:
    """The HTTP status of a failed call, from the SDKs' errors (``status_code``,
    ``code``) or from requests' (``response.status_code``)."""
    for status in (
        getattr(error, "status_code", None),
        getattr(error, "code", None),
        getattr(getattr(error, "response", None), "status_code", None),
    ):
        if isinstance(status, int) and not isinstance(status, bool):
            return status
    return None


def _is_timeout(error: Exception) -> bool:
    return "Timeout" in type(error).__name__ or isinstance(error, TimeoutError)


def _is_retryable(error: Exception) -> bool:
    """Worth asking again: the service is busy (429), failed on its side (5xx)
    or the connection failed. Not a timeout, which would only wait as long
    again, and not a request it refused (a wrong key or model, 4xx), an
    answer that could not be read or a mistake in the call."""
    if isinstance(error, AIProviderError) or _is_timeout(error):
        return False
    status = _status_of(error)
    if status is not None:
        return status == 429 or status >= 500
    return isinstance(error, ConnectionError) or "Connection" in type(error).__name__


CLAUDE_DEFAULT_MODEL = "claude-opus-5-5"
# the models the API can hand a declined request to another model for
# ("server-side fallback"); with any other model the request goes as it is
CLAUDE_MODELS_WITH_FALLBACKS = frozenset(
    {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}
)


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    def __init__(self, config: dict[str, Any]):
        """
        Initialize the AI provider.

        Args:
            config: Configuration dictionary containing API keys, model names, etc.
        """
        self.config = config
        self.max_retries = config.get("max_retries", 3)
        self.retry_delay = config.get("retry_delay", 1)
        # seconds to wait for one answer
        self.timeout = config.get("timeout", 120)

    @abstractmethod
    def generate_summary(self, data: dict[str, Any], prompt: str) -> str:
        """
        Generate a summary using the AI service.

        Args:
            data: Data dictionary to be analyzed
            prompt: Prompt template with instructions

        Returns:
            Generated summary text

        Raises:
            AIProviderError: If the generation fails
        """
        pass

    def _retry_with_backoff(self, func, *args, **kwargs):
        """Call ``func``, and again with exponential backoff while it fails in a
        way worth retrying (see ``_is_retryable``), ``max_retries`` calls in
        all. The SDKs are told not to retry on their own, so these are all
        the calls made.

        Raises AIProviderUnavailableError when the service timed out or could not
        be reached, AIProviderError for any other failure.
        """
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last = attempt == self.max_retries - 1
                if _is_retryable(e) and not last:
                    delay = self.retry_delay * (2**attempt)
                    logger.warning(f"Attempt {attempt + 1} failed, retrying in {delay}s: {e}")
                    time.sleep(delay)
                    continue
                message = f"Failed after {attempt + 1} attempts: {e}" if attempt else str(e)
                if _is_timeout(e):
                    raise AIProviderUnavailableError(
                        f"No answer within {self.timeout} seconds ({e})"
                    ) from e
                if isinstance(e, AIProviderError):
                    raise
                if _is_retryable(e) and _status_of(e) is None:
                    raise AIProviderUnavailableError(message) from e  # could not connect
                raise AIProviderError(message) from e


class OpenAIProvider(AIProvider):
    """OpenAI GPT provider."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        try:
            import openai

            self.openai = openai
        except ImportError:
            raise AIProviderError(
                "openai package not installed. Install with: pip install openai"
            ) from None

        # Get API key from config or environment
        self.api_key = config.get("api_key") or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise AIProviderError(
                "OpenAI API key not found. Set OPENAI_API_KEY environment variable or configure it."
            )

        self.model = _get_model_with_fallback(config, "gpt-4")
        # gitstats retries itself (see _retry_with_backoff)
        self.client = openai.OpenAI(api_key=self.api_key, max_retries=0, timeout=self.timeout)

    def generate_summary(self, data: dict[str, Any], prompt: str) -> str:
        """Generate summary using OpenAI API."""

        def _call_api():
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert software development analyst who provides insightful analysis of git repository statistics.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=2000,
            )
            return response.choices[0].message.content

        return self._retry_with_backoff(_call_api)


class ClaudeProvider(AIProvider):
    """Anthropic Claude provider."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        try:
            import anthropic

            self.anthropic = anthropic
        except ImportError:
            raise AIProviderError(
                "anthropic package not installed. Install with: pip install anthropic"
            ) from None

        self.api_key = config.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise AIProviderError(
                "Claude API key not found. Set ANTHROPIC_API_KEY environment variable or configure it."
            )

        self.model = _get_model_with_fallback(config, CLAUDE_DEFAULT_MODEL)
        # gitstats retries itself (see _retry_with_backoff)
        self.client = self.anthropic.Anthropic(
            api_key=self.api_key, max_retries=0, timeout=self.timeout
        )

    def generate_summary(self, data: dict[str, Any], prompt: str) -> str:
        """Generate summary using Claude API."""

        def _call_api():
            # No temperature: current models and SDKs (anthropic 1.0 on) refuse it.
            # The answer is a few paragraphs; the room above that is for thinking.
            request = {
                "model": self.model,
                "max_tokens": 16000,
                "messages": [{"role": "user", "content": prompt}],
            }
            if self.model in CLAUDE_MODELS_WITH_FALLBACKS:
                # if the model declines, the API asks another one in the same call
                response = self.client.beta.messages.create(
                    **request, betas=["server-side-fallback-2026-07-01"], fallbacks="default"
                )
            else:
                response = self.client.messages.create(**request)
            if response.stop_reason == "refusal":
                raise AIProviderError(f"{self.model} declined to write this summary")
            # the answer's text, without the thinking blocks before it
            text = "".join(
                block.text for block in response.content if getattr(block, "type", "") == "text"
            ).strip()
            if not text:
                raise AIProviderError(
                    f"{self.model} gave no text (stop reason: {response.stop_reason})"
                )
            return text

        return self._retry_with_backoff(_call_api)


class GeminiProvider(AIProvider):
    """Google Gemini provider."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        try:
            import google.generativeai as genai

            self.genai = genai
        except ImportError:
            raise AIProviderError(
                "google-generativeai package not installed. Install with: pip install google-generativeai"
            ) from None

        self.api_key = config.get("api_key") or os.environ.get("GOOGLE_API_KEY")
        if not self.api_key:
            raise AIProviderError(
                "Gemini API key not found. Set GOOGLE_API_KEY environment variable or configure it."
            )

        self.model_name = _get_model_with_fallback(config, "gemini-2.5-flash")
        self.genai.configure(api_key=self.api_key)
        self.model = self.genai.GenerativeModel(self.model_name)

    def generate_summary(self, data: dict[str, Any], prompt: str) -> str:
        """Generate summary using Gemini API."""

        def _call_api():
            response = self.model.generate_content(
                prompt, request_options={"timeout": self.timeout}
            )
            return response.text

        return self._retry_with_backoff(_call_api)


class _OllamaError(Exception):
    """An HTTP error from Ollama, with the reason it gave."""

    def __init__(self, message: str, status_code: int | None):
        super().__init__(message)
        self.status_code = status_code


class OllamaProvider(AIProvider):
    """Ollama local LLM provider."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        try:
            import requests

            self.requests = requests
        except ImportError:
            raise AIProviderError(
                "requests package not installed. Install with: pip install requests"
            ) from None

        self.base_url = config.get("base_url", "http://localhost:11434")
        self.model = _get_model_with_fallback(config, "llama2")

    def generate_summary(self, data: dict[str, Any], prompt: str) -> str:
        """Generate summary using Ollama API."""

        def _call_api():
            url = f"{self.base_url}/api/generate"
            response = self.requests.post(
                url,
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=self.timeout,
            )
            try:
                answer = response.json()
            except ValueError:
                answer = None
            # Ollama says what went wrong in "error", e.g. a model not pulled yet
            error = answer.get("error") if isinstance(answer, dict) else None
            try:
                response.raise_for_status()
            except Exception as e:
                if error:
                    raise _OllamaError(f"Ollama: {error} ({e})", _status_of(e)) from e
                raise
            if error:
                raise AIProviderError(f"Ollama: {error}")
            if not isinstance(answer, dict) or not isinstance(answer.get("response"), str):
                raise AIProviderError(f"{url} did not answer as Ollama does")
            return answer["response"]

        return self._retry_with_backoff(_call_api)


class AIProviderFactory:
    """Factory for creating AI provider instances."""

    _providers: dict[str, type[AIProvider]] = {
        "openai": OpenAIProvider,
        "claude": ClaudeProvider,
        "gemini": GeminiProvider,
        "ollama": OllamaProvider,
    }

    @classmethod
    def create(cls, provider_name: str, config: dict[str, Any]) -> AIProvider:
        """
        Create an AI provider instance.

        Args:
            provider_name: Name of the provider (openai, claude, gemini, ollama)
            config: Configuration dictionary

        Returns:
            AIProvider instance

        Raises:
            AIProviderError: If provider not found
        """
        provider_name = provider_name.lower()
        if provider_name not in cls._providers:
            supported = ", ".join(cls._providers.keys())
            raise AIProviderError(
                f"Unknown AI provider: {provider_name}. Supported providers: {supported}"
            )

        provider_class = cls._providers[provider_name]
        return provider_class(config)

    @classmethod
    def list_providers(cls) -> list:
        """Get list of supported provider names."""
        return list(cls._providers.keys())
