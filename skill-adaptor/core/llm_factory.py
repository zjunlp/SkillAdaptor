"""Build OpenAI-compatible client for orchestrator LLM stages."""

from __future__ import annotations
from types import SimpleNamespace
from typing import Any
from .config import SkillEvolveConfig
from .llm_retry import call_with_retries

class _RetryingChatCompletions:

    def __init__(self, inner: Any, max_retries: int) -> None:
        self._inner = inner
        self._max_retries = max_retries

    def create(self, **kwargs: Any) -> Any:
        return call_with_retries(lambda: self._inner.create(**kwargs), max_retries=self._max_retries, context='LLM chat.completions')

class _RetryingChat:

    def __init__(self, inner: Any, max_retries: int) -> None:
        self.completions = _RetryingChatCompletions(inner.completions, max_retries)

class RetryingOpenAIClient:

    def __init__(self, client: Any, max_retries: int=5) -> None:
        self._client = client
        self.chat = _RetryingChat(client.chat, max_retries)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)

def build_openai_client(config: SkillEvolveConfig) -> Any:
    import openai
    if not config.api_key:
        raise ValueError('SkillEvolve API key is required for evolution pipeline')
    if not config.base_url:
        raise ValueError('SkillEvolve BASE_URL is required for evolution pipeline')
    raw = openai.OpenAI(api_key=config.api_key, base_url=config.base_url)
    return RetryingOpenAIClient(raw, max_retries=config.max_retries)
