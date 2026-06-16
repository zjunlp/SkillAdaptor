"""Unified LLM provider profiles for SkillAdaptor plugin and CLI runners."""

from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Optional
from core.embedding_config import PRIMARY_EMBEDDING_MODEL
OPENROUTER_DEFAULT_BASE = 'https://openrouter.ai/api/v1'
DEEPSEEK_DEFAULT_BASE = 'https://api.deepseek.com'
DEEPSEEK_OPENAI_COMPAT_BASE = 'https://api.deepseek.com/v1'

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
        os.environ['SkillEvolve_API_KEY'] = self.api_key
        os.environ['SkillEvolve_BASE_URL'] = self.base_url
        os.environ['SkillEvolve_MODEL'] = self.model
        os.environ['OPENAI_API_KEY'] = self.api_key
        os.environ['OPENAI_API_BASE_URL'] = self.base_url
        if self.embedding_api_key:
            os.environ['SkillEvolve_EMBEDDING_API_KEY'] = self.embedding_api_key
        if self.embedding_base_url:
            os.environ['SkillEvolve_EMBEDDING_BASE_URL'] = self.embedding_base_url
        if self.embedding_model:
            os.environ['SkillEvolve_EMBEDDING_MODEL'] = self.embedding_model

def _first_non_empty(*values: Optional[str]) -> str:
    for value in values:
        if value and str(value).strip():
            return str(value).strip()
    return ''

def resolve_provider(name: str='relay-gpt41') -> ProviderProfile:
    key = name.lower().strip()
    if key in {'relay', 'relay-gpt41', 'gpt41', 'gpt-4.1'}:
        api_key = _first_non_empty(os.environ.get('OPENAI_API_KEY'), os.environ.get('SkillEvolve_API_KEY'))
        base_url = _first_non_empty(os.environ.get('OPENAI_API_BASE_URL'), os.environ.get('SkillEvolve_BASE_URL'))
        model = _first_non_empty(os.environ.get('SkillEvolve_MODEL'), os.environ.get('OPENAI_MODEL'), 'gpt-4.1')
        emb_key = _first_non_empty(os.environ.get('SkillEvolve_EMBEDDING_API_KEY'), api_key)
        emb_base = _first_non_empty(os.environ.get('SkillEvolve_EMBEDDING_BASE_URL'), base_url)
        emb_model = _first_non_empty(os.environ.get('SkillEvolve_EMBEDDING_MODEL'), PRIMARY_EMBEDDING_MODEL)
        return ProviderProfile(name='relay-gpt41', api_key=api_key, base_url=base_url, model=model, embedding_api_key=emb_key, embedding_base_url=emb_base, embedding_model=emb_model)
    if key == 'deepseek':
        api_key = _first_non_empty(os.environ.get('DEEPSEEK_API_KEY'))
        base_url = _first_non_empty(os.environ.get('DEEPSEEK_API_BASE_URL'), DEEPSEEK_OPENAI_COMPAT_BASE)
        if not base_url.endswith('/v1'):
            base_url = base_url.rstrip('/') + '/v1'
        model = _first_non_empty(os.environ.get('DEEPSEEK_MODEL'), 'deepseek-v4-flash')
        return ProviderProfile(name='deepseek', api_key=api_key, base_url=base_url, model=model, embedding_api_key=api_key, embedding_base_url=base_url, embedding_model='text-embedding-3-small')
    if key == 'openrouter':
        api_key = _first_non_empty(os.environ.get('OPENROUTER_API_KEY'))
        base_url = _first_non_empty(os.environ.get('OPENROUTER_API_BASE_URL'), OPENROUTER_DEFAULT_BASE)
        model = _first_non_empty(os.environ.get('OPENROUTER_MODEL'), os.environ.get('SkillEvolve_MODEL'), 'openai/gpt-4.1')
        return ProviderProfile(name='openrouter', api_key=api_key, base_url=base_url, model=model, embedding_api_key=api_key, embedding_base_url=base_url, embedding_model='openai/text-embedding-3-small')
    if key == 'custom':
        return ProviderProfile(name='custom', api_key=_first_non_empty(os.environ.get('SkillEvolve_API_KEY')), base_url=_first_non_empty(os.environ.get('SkillEvolve_BASE_URL')), model=_first_non_empty(os.environ.get('SkillEvolve_MODEL')), embedding_api_key=_first_non_empty(os.environ.get('SkillEvolve_EMBEDDING_API_KEY')), embedding_base_url=_first_non_empty(os.environ.get('SkillEvolve_EMBEDDING_BASE_URL')), embedding_model=_first_non_empty(os.environ.get('SkillEvolve_EMBEDDING_MODEL'), PRIMARY_EMBEDDING_MODEL))
    raise ValueError(f"Unknown provider '{name}'. Use relay-gpt41, deepseek, openrouter, or custom.")

def validate_profile(profile: ProviderProfile) -> list[str]:
    issues: list[str] = []
    if not profile.api_key:
        issues.append(f'{profile.name}: missing API key')
    if not profile.base_url:
        issues.append(f'{profile.name}: missing base URL')
    if not profile.model:
        issues.append(f'{profile.name}: missing model id')
    if profile.name == 'openrouter' and profile.api_key and (not profile.api_key.startswith('sk-or-')):
        issues.append('openrouter: key should start with sk-or-v1- (DeepSeek sk- is not valid here)')
    return issues
