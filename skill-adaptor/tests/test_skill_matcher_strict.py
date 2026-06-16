"""Embedding API must fail loudly — no lexical or rule-based fallback."""

from __future__ import annotations
from unittest.mock import MagicMock, patch
import pytest
from core.skill_matcher import SemanticSkillMatcher

def test_encode_raises_when_api_fails() -> None:
    matcher = SemanticSkillMatcher(api_key='test-key', base_url='https://example.com/v1', model_name='Qwen3-Embedding-8B')
    with patch.object(matcher, '_embed_via_api', side_effect=ConnectionError('503 Service Unavailable')):
        with pytest.raises(RuntimeError, match='Manual backup only'):
            matcher.encode(['hello'])

def test_encode_raises_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('SkillEvolve_EMBEDDING_API_KEY', raising=False)
    monkeypatch.delenv('SkillEvolve_EMBEDDING_BASE_URL', raising=False)
    matcher = SemanticSkillMatcher(api_key='', base_url='')
    with pytest.raises(RuntimeError, match='Embedding API not configured'):
        matcher.encode(['hello'])

def test_match_skills_propagates_embedding_error() -> None:
    from core.types import Skill
    matcher = SemanticSkillMatcher(api_key='k', base_url='https://example.com/v1')
    skills = {'s1': Skill(id='s1', title='T', description='D', body='body', when_to_apply='when', created_from='task_a')}
    with patch.object(matcher, '_embed_via_api', side_effect=OSError('connection reset')):
        with pytest.raises(RuntimeError, match='Embedding API request failed'):
            matcher.match_skills_to_task(skills, 'task query', top_k=1)
