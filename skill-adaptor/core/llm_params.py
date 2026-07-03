"""Model-aware LLM request parameters (OpenAI-compatible APIs)."""

from __future__ import annotations


def chat_temperature(model_name: str, preferred: float) -> float:
    """Some models (kimi/glm) only accept temperature=1."""
    m = (model_name or '').lower()
    if 'kimi' in m or 'glm' in m:
        return 1.0
    return preferred
