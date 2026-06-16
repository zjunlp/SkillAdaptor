"""Embedding model constants and error hints."""

from __future__ import annotations
from core.embedding_config import BACKUP_EMBEDDING_MODEL, PRIMARY_EMBEDDING_MODEL, format_embedding_error, is_backup_embedding_model, resolve_embedding_model

def test_primary_model_default():
    assert PRIMARY_EMBEDDING_MODEL == 'Qwen3-Embedding-8B'
    assert BACKUP_EMBEDDING_MODEL == 'text-embedding-3-small'

def test_resolve_embedding_model_no_auto_backup(monkeypatch):
    monkeypatch.delenv('SkillEvolve_EMBEDDING_MODEL', raising=False)
    assert resolve_embedding_model(None) == PRIMARY_EMBEDDING_MODEL

def test_format_embedding_error_mentions_backup():
    msg = format_embedding_error(PRIMARY_EMBEDDING_MODEL, RuntimeError('503'))
    assert 'Manual backup only' in msg
    assert BACKUP_EMBEDDING_MODEL in msg
    assert 'no auto-fallback' in msg

def test_backup_is_explicit_opt_in():
    assert is_backup_embedding_model(BACKUP_EMBEDDING_MODEL)
    assert not is_backup_embedding_model(PRIMARY_EMBEDDING_MODEL)
