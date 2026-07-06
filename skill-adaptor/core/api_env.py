"""Canonical API env var names — chat + embedding (no vendor-specific prefixes)."""

from __future__ import annotations

import os
from typing import Dict, Optional

CHAT_API_KEY_VAR = 'SkillEvolve_API_KEY'
CHAT_BASE_URL_VAR = 'SkillEvolve_BASE_URL'
CHAT_MODEL_VAR = 'SkillEvolve_MODEL'

EMBEDDING_API_KEY_VAR = 'SkillEvolve_EMBEDDING_API_KEY'
EMBEDDING_BASE_URL_VAR = 'SkillEvolve_EMBEDDING_BASE_URL'
EMBEDDING_MODEL_VAR = 'SkillEvolve_EMBEDDING_MODEL'

# Read-only legacy aliases (older .env files); not written by apply_chat_credentials.
_LEGACY_CHAT_KEY_VARS = ('OPENAI_API_KEY',)
_LEGACY_CHAT_URL_VARS = ('OPENAI_API_BASE_URL', 'OPENAI_BASE_URL')
_LEGACY_CHAT_MODEL_VARS = ('OPENAI_MODEL',)


def first_env(*names: str) -> str:
    for name in names:
        val = os.environ.get(name, '').strip()
        if val:
            return val
    return ''


def chat_key_envs() -> tuple[str, ...]:
    return (CHAT_API_KEY_VAR,) + _LEGACY_CHAT_KEY_VARS


def chat_url_envs() -> tuple[str, ...]:
    return (CHAT_BASE_URL_VAR,) + _LEGACY_CHAT_URL_VARS


def chat_model_envs() -> tuple[str, ...]:
    return (CHAT_MODEL_VAR, 'MODEL') + _LEGACY_CHAT_MODEL_VARS


def embedding_key_envs() -> tuple[str, ...]:
    return (EMBEDDING_API_KEY_VAR,) + chat_key_envs()


def embedding_url_envs() -> tuple[str, ...]:
    return (EMBEDDING_BASE_URL_VAR,) + chat_url_envs()


def apply_chat_credentials(*, api_key: str, base_url: str, model: str) -> None:
    os.environ[CHAT_API_KEY_VAR] = api_key
    os.environ[CHAT_BASE_URL_VAR] = base_url
    os.environ[CHAT_MODEL_VAR] = model
    os.environ['MODEL'] = model


def apply_embedding_credentials(*, api_key: str, base_url: str, model: str) -> None:
    os.environ[EMBEDDING_API_KEY_VAR] = api_key
    os.environ[EMBEDDING_BASE_URL_VAR] = base_url
    os.environ[EMBEDDING_MODEL_VAR] = model


def inject_benchmark_child_env(
    env: Dict[str, str],
    *,
    api_key: str,
    base_url: str,
    model: Optional[str] = None,
) -> None:
    """PinchBench / Claw-Eval child processes may still read legacy OPENAI_* — set both."""
    if api_key:
        env[CHAT_API_KEY_VAR] = api_key
        env['OPENAI_API_KEY'] = api_key
        env['ANTHROPIC_API_KEY'] = api_key
    if base_url:
        env[CHAT_BASE_URL_VAR] = base_url
        env['OPENAI_BASE_URL'] = base_url
        env['BASE_URL'] = base_url
    if model:
        env[CHAT_MODEL_VAR] = model
        env['MODEL'] = model
