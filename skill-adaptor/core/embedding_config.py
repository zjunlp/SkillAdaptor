"""Embedding model configuration — primary Qwen3, no runtime auto-failover."""

from __future__ import annotations

from core.api_env import (
    EMBEDDING_BASE_URL_VAR,
    EMBEDDING_MODEL_VAR,
    embedding_model_envs,
    first_env,
)

PRIMARY_EMBEDDING_MODEL = 'Qwen3-Embedding-8B'
BACKUP_EMBEDDING_MODEL = 'text-embedding-3-small'
# OpenRouter gateway model id when chat and embedding share OPENROUTER_API_* only.
OPENROUTER_EMBEDDING_FALLBACK = 'openai/text-embedding-3-small'


def resolve_embedding_model(explicit: str | None = None) -> str:
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    return first_env(*embedding_model_envs()) or PRIMARY_EMBEDDING_MODEL


def resolve_openrouter_embedding_model() -> str:
    """Embedding model for OpenRouter profile when no separate embedding API is configured."""
    import os
    explicit = first_env(EMBEDDING_MODEL_VAR)
    if explicit:
        return explicit
    if os.environ.get(EMBEDDING_BASE_URL_VAR, '').strip():
        return PRIMARY_EMBEDDING_MODEL
    return OPENROUTER_EMBEDDING_FALLBACK


def format_embedding_error(model: str, cause: Exception) -> str:
    msg = f'Embedding API request failed (model={model!r}): {cause}'
    if model == PRIMARY_EMBEDDING_MODEL:
        msg += f' Manual backup only (no auto-fallback): set {EMBEDDING_MODEL_VAR}={BACKUP_EMBEDDING_MODEL!r} in secrets/.env.'
    return msg


def is_backup_embedding_model(model: str) -> bool:
    return (model or '').strip() == BACKUP_EMBEDDING_MODEL
