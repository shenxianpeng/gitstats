"""
AI Provider abstraction layer for GitStats.

Supports multiple AI services: OpenAI, Claude, Gemini, Ollama (local LLM), and GitHub Copilot.
"""

import os
import time
from abc import ABC, abstractmethod
from typing import Dict, Any
import logging

logger = logging.getLogger("gitstats")


class AIProviderError(Exception):
    """Base exception for AI provider errors."""

    pass


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the AI provider.

        Args:
            config: Configuration dictionary containing API keys, model names, etc.
        """
        self.config = config
        self.max_retries = config.get("max_retries", 3)
        self.retry_delay = config.get("retry_delay", 1)

    @abstractmethod
    def generate_summary(self, data: Dict[str, Any], prompt: str) -> str:
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
        """Execute a function with exponential backoff retry logic."""
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise AIProviderError(
                        f"Failed after {self.max_retries} attempts: {str(e)}"
                    )
                delay = self.retry_delay * (2**attempt)
                logger.warning(
                    f"Attempt {attempt + 1} failed, retrying in {delay}s: {str(e)}"
                )
                time.sleep(delay)


class OpenAIProvider(AIProvider):
    """OpenAI GPT provider."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        try:
            import openai

            self.openai = openai
        except ImportError:
            raise AIProviderError(
                "openai package not installed. Install with: pip install openai"
            )

        # Get API key from config or environment
        self.api_key = config.get("api_key") or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise AIProviderError(
                "OpenAI API key not found. Set OPENAI_API_KEY environment variable or configure it."
            )

        self.model = config.get("model", "gpt-4")
        self.client = openai.OpenAI(api_key=self.api_key)

    def generate_summary(self, data: Dict[str, Any], prompt: str) -> str:
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

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        try:
            import anthropic

            self.anthropic = anthropic
        except ImportError:
            raise AIProviderError(
                "anthropic package not installed. Install with: pip install anthropic"
            )

        self.api_key = config.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise AIProviderError(
                "Claude API key not found. Set ANTHROPIC_API_KEY environment variable or configure it."
            )

        self.model = config.get("model", "claude-3-5-sonnet-20241022")
        self.client = self.anthropic.Anthropic(api_key=self.api_key)

    def generate_summary(self, data: Dict[str, Any], prompt: str) -> str:
        """Generate summary using Claude API."""

        def _call_api():
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                temperature=0.7,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text

        return self._retry_with_backoff(_call_api)


class GeminiProvider(AIProvider):
    """Google Gemini provider."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        try:
            import google.generativeai as genai

            self.genai = genai
        except ImportError:
            raise AIProviderError(
                "google-generativeai package not installed. Install with: pip install google-generativeai"
            )

        self.api_key = config.get("api_key") or os.environ.get("GOOGLE_API_KEY")
        if not self.api_key:
            raise AIProviderError(
                "Gemini API key not found. Set GOOGLE_API_KEY environment variable or configure it."
            )

        self.model_name = config.get("model", "gemini-pro")
        self.genai.configure(api_key=self.api_key)
        self.model = self.genai.GenerativeModel(self.model_name)

    def generate_summary(self, data: Dict[str, Any], prompt: str) -> str:
        """Generate summary using Gemini API."""

        def _call_api():
            response = self.model.generate_content(prompt)
            return response.text

        return self._retry_with_backoff(_call_api)


class OllamaProvider(AIProvider):
    """Ollama local LLM provider."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        try:
            import requests

            self.requests = requests
        except ImportError:
            raise AIProviderError(
                "requests package not installed. Install with: pip install requests"
            )

        self.base_url = config.get("base_url", "http://localhost:11434")
        self.model = config.get("model", "llama2")

    def generate_summary(self, data: Dict[str, Any], prompt: str) -> str:
        """Generate summary using Ollama API."""

        def _call_api():
            response = self.requests.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=120,
            )
            response.raise_for_status()
            return response.json()["response"]

        return self._retry_with_backoff(_call_api)


class CopilotProvider(AIProvider):
    """GitHub Copilot provider (using OpenAI-compatible endpoint)."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        try:
            import openai

            self.openai = openai
        except ImportError:
            raise AIProviderError(
                "openai package not installed. Install with: pip install openai"
            )

        # GitHub Copilot uses a different endpoint
        self.api_key = config.get("api_key") or os.environ.get("GITHUB_TOKEN")
        if not self.api_key:
            raise AIProviderError(
                "GitHub token not found. Set GITHUB_TOKEN environment variable or configure it."
            )

        # Use gpt-4 for Copilot
        self.model = config.get("model", "gpt-4")

        # Note: This is a placeholder. GitHub Copilot's API might have different endpoints
        # For now, we'll use OpenAI's API structure, but this may need adjustment
        self.client = openai.OpenAI(api_key=self.api_key)

    def generate_summary(self, data: Dict[str, Any], prompt: str) -> str:
        """Generate summary using GitHub Copilot."""

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


class AIProviderFactory:
    """Factory for creating AI provider instances."""

    _providers = {
        "openai": OpenAIProvider,
        "claude": ClaudeProvider,
        "gemini": GeminiProvider,
        "ollama": OllamaProvider,
        "copilot": CopilotProvider,
    }

    @classmethod
    def create(cls, provider_name: str, config: Dict[str, Any]) -> AIProvider:
        """
        Create an AI provider instance.

        Args:
            provider_name: Name of the provider (openai, claude, gemini, ollama, copilot)
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
