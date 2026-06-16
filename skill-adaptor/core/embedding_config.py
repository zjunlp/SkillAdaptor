"""Embedding model configuration — primary Qwen3, no runtime auto-failover."""

from __future__ import annotations
PRIMARY_EMBEDDING_MODEL = 'Qwen3-Embedding-8B'

def resolve_embedding_model(explicit: str | None=None) -> str:
    import os
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    return os.environ.get('SkillEvolve_EMBEDDING_MODEL', '').strip() or PRIMARY_EMBEDDING_MODEL

def format_embedding_error(model: str, cause: Exception) -> str:
    msg = f'Embedding API request failed (model={model!r}): {cause}'
    if model == PRIMARY_EMBEDDING_MODEL:
        msg += f' Manual backup only (no auto-fallback): set SkillEvolve_EMBEDDING_MODEL={BACKUP_EMBEDDING_MODEL!r} in secrets/.env.'
    return msg
BACKUP_EMBEDDING_MODEL = 'text-embedding-3-small'

def is_backup_embedding_model(model: str) -> bool:
    return (model or '').strip() == BACKUP_EMBEDDING_MODEL
