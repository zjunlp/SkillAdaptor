"""Unified LLM provider — one compatible chat API + separate embedding API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, List, Optional

from core.api_env import (
    CHAT_API_KEY_VAR,
    CHAT_BASE_URL_VAR,
    CHAT_MODEL_VAR,
    EMBEDDING_API_KEY_VAR,
    EMBEDDING_BASE_URL_VAR,
    EMBEDDING_MODEL_VAR,
    apply_chat_credentials,
    apply_embedding_credentials,
    chat_key_envs,
    chat_model_envs,
    chat_url_envs,
    embedding_key_envs,
    embedding_model_envs,
    embedding_url_envs,
    first_env,
)
from core.embedding_config import PRIMARY_EMBEDDING_MODEL, resolve_openrouter_embedding_model

OPENROUTER_DEFAULT_BASE = 'https://openrouter.ai/api/v1'
DEEPSEEK_DEFAULT_BASE = 'https://api.deepseek.com/v1'

_PROVIDER_ALIASES: dict[str, str] = {
    '': 'auto',
    'auto': 'auto',
    'openai': 'auto',
    'openai-compatible': 'auto',
    'gpt': 'auto',
    'glm': 'auto',
    'kimi': 'auto',
    'relay': 'auto',
    'relay-gpt41': 'auto',
    'relay-kimi': 'auto',
    'relay-glm': 'auto',
    'gpt41': 'auto',
    'gpt-4.1': 'auto',
    'deepseek': 'deepseek',
    'openrouter': 'openrouter',
    'custom': 'custom',
}


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    api_key: str
    base_url: str
    model: str
    embedding_api_key: str = ''
    embedding_base_url: str = ''
    embedding_model: str = PRIMARY_EMBEDDING_MODEL

    def apply_to_environ(self) -> None:
        os.environ['SkillAdaptor_LLM_APPLIED'] = '1'
        os.environ['SkillAdaptor_ACTIVE_PROVIDER'] = self.name
        apply_chat_credentials(api_key=self.api_key, base_url=self.base_url, model=self.model)
        emb_key = self.embedding_api_key or self.api_key
        emb_base = self.embedding_base_url or self.base_url
        apply_embedding_credentials(api_key=emb_key, base_url=emb_base, model=self.embedding_model)


def _first_non_empty(*values: Optional[str]) -> str:
    for value in values:
        if value and str(value).strip():
            return str(value).strip()
    return ''


def normalize_provider_name(name: Optional[str]) -> str:
    key = (name or '').strip().lower()
    return _PROVIDER_ALIASES.get(key, key or 'auto')


def _api_pair(
    key_envs: tuple[str, ...],
    url_envs: tuple[str, ...],
    *,
    default_url: str = '',
) -> tuple[str, str]:
    key = _first_non_empty(*(os.environ.get(name) for name in key_envs))
    url_values: list[Optional[str]] = [os.environ.get(name) for name in url_envs]
    if default_url:
        url_values.append(default_url)
    base_url = _first_non_empty(*url_values)
    return key, base_url


def _embedding_credentials() -> tuple[str, str, str]:
    emb_key, emb_base = _api_pair(embedding_key_envs(), embedding_url_envs())
    emb_model = _first_non_empty(
        *(os.environ.get(name) for name in embedding_model_envs()),
        PRIMARY_EMBEDDING_MODEL,
    )
    return emb_key, emb_base, emb_model


def _llm_credentials() -> tuple[str, str]:
    return _api_pair(chat_key_envs(), chat_url_envs())


def _default_model(model_hint: Optional[str]) -> str:
    return _first_non_empty(model_hint, first_env(*chat_model_envs()), 'gpt-4.1')


def _profile_auto(model: Optional[str]) -> ProviderProfile:
    api_key, base_url = _llm_credentials()
    emb_key, emb_base, emb_model = _embedding_credentials()
    return ProviderProfile(
        name='auto',
        api_key=api_key,
        base_url=base_url,
        model=_default_model(model),
        embedding_api_key=emb_key,
        embedding_base_url=emb_base,
        embedding_model=emb_model,
    )


def _profile_deepseek(model: Optional[str]) -> ProviderProfile:
    api_key, base_url = _api_pair(
        ('DEEPSEEK_API_KEY',) + chat_key_envs(),
        ('DEEPSEEK_API_BASE_URL',) + chat_url_envs(),
        default_url=DEEPSEEK_DEFAULT_BASE,
    )
    if base_url and not base_url.endswith('/v1'):
        base_url = base_url.rstrip('/') + '/v1'
    emb_key, emb_base, emb_model = _embedding_credentials()
    return ProviderProfile(
        name='deepseek',
        api_key=api_key,
        base_url=base_url,
        model=_first_non_empty(model, os.environ.get('DEEPSEEK_MODEL'), 'deepseek-chat'),
        embedding_api_key=emb_key or api_key,
        embedding_base_url=emb_base or base_url,
        embedding_model=emb_model,
    )


def _profile_openrouter(model: Optional[str]) -> ProviderProfile:
    api_key, base_url = _api_pair(
        ('OPENROUTER_API_KEY',) + chat_key_envs(),
        ('OPENROUTER_API_BASE_URL',) + chat_url_envs(),
        default_url=OPENROUTER_DEFAULT_BASE,
    )
    emb_key, emb_base, emb_model = _embedding_credentials()
    separate_embedding = bool(
        os.environ.get(EMBEDDING_API_KEY_VAR, '').strip()
        or os.environ.get(EMBEDDING_BASE_URL_VAR, '').strip()
    )
    if separate_embedding:
        final_emb_key = emb_key
        final_emb_base = emb_base
        final_emb_model = emb_model
    else:
        final_emb_key = api_key
        final_emb_base = base_url
        final_emb_model = resolve_openrouter_embedding_model()
    return ProviderProfile(
        name='openrouter',
        api_key=api_key,
        base_url=base_url,
        model=_first_non_empty(model, os.environ.get('OPENROUTER_MODEL'), 'openai/gpt-4.1'),
        embedding_api_key=final_emb_key,
        embedding_base_url=final_emb_base,
        embedding_model=final_emb_model,
    )


def _profile_custom(model: Optional[str]) -> ProviderProfile:
    api_key, base_url = _llm_credentials()
    emb_key, emb_base, emb_model = _embedding_credentials()
    return ProviderProfile(
        name='custom',
        api_key=api_key,
        base_url=base_url,
        model=_default_model(model),
        embedding_api_key=_first_non_empty(os.environ.get(EMBEDDING_API_KEY_VAR), emb_key),
        embedding_base_url=_first_non_empty(os.environ.get(EMBEDDING_BASE_URL_VAR), emb_base),
        embedding_model=emb_model,
    )


def resolve_provider(name: str = 'auto', *, model: Optional[str] = None) -> ProviderProfile:
    canonical = normalize_provider_name(name)
    model = _first_non_empty(model, os.environ.get(CHAT_MODEL_VAR), os.environ.get('SkillAdaptor_MODEL'))

    if canonical == 'deepseek':
        return _profile_deepseek(model)
    if canonical == 'openrouter':
        return _profile_openrouter(model)
    if canonical == 'custom':
        return _profile_custom(model)
    return _profile_auto(model)


def resolve_and_apply(provider: Optional[str] = None, model: Optional[str] = None) -> ProviderProfile:
    prov = normalize_provider_name(
        provider or os.environ.get('SkillAdaptor_PROVIDER') or 'auto'
    )
    profile = resolve_provider(prov, model=model)
    issues = validate_profile(profile)
    if issues:
        raise ValueError('LLM provider config invalid: ' + '; '.join(issues))
    profile.apply_to_environ()
    return profile


def sync_config_from_profile(config: Any, profile: ProviderProfile) -> None:
    config.api_key = profile.api_key
    config.base_url = profile.base_url
    config.model = profile.model
    config.embedding_api_key = profile.embedding_api_key or profile.api_key
    config.embedding_base_url = profile.embedding_base_url or profile.base_url
    config.embedding_model = profile.embedding_model


def validate_profile(profile: ProviderProfile) -> List[str]:
    issues: List[str] = []
    if not profile.api_key:
        if profile.name == 'deepseek':
            issues.append(f'deepseek: missing API key (set DEEPSEEK_API_KEY or {CHAT_API_KEY_VAR})')
        elif profile.name == 'openrouter':
            issues.append(f'openrouter: missing API key (set OPENROUTER_API_KEY or {CHAT_API_KEY_VAR})')
        else:
            issues.append(f'{profile.name}: missing API key (set {CHAT_API_KEY_VAR})')
    if not profile.base_url:
        if profile.name == 'deepseek':
            issues.append(f'deepseek: missing base URL (set DEEPSEEK_API_BASE_URL or {CHAT_BASE_URL_VAR})')
        elif profile.name == 'openrouter':
            issues.append(f'openrouter: missing base URL (set OPENROUTER_API_BASE_URL or {CHAT_BASE_URL_VAR})')
        else:
            issues.append(f'{profile.name}: missing base URL (set {CHAT_BASE_URL_VAR})')
    if not profile.model:
        issues.append(f'{profile.name}: missing model id')
    return issues


def describe_profile(profile: ProviderProfile) -> str:
    base = profile.base_url.rstrip('/')
    if len(base) > 48:
        base = base[:45] + '...'
    return f'{profile.name} model={profile.model} base={base}'
