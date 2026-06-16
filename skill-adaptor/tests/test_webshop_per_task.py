"""WebShop per-task skill injection tests."""

from __future__ import annotations
from core.types import Skill
from adapters.webshop_adapter.llm_policy import SkillAugmentedLLMPolicy

def test_begin_episode_caches_skills(monkeypatch) -> None:
    policy = SkillAugmentedLLMPolicy({'api_key': 'x', 'base_url': 'http://test', 'model': 'gpt-4.1'}, skill_bank={'s1': Skill(id='s1', title='Search products', description='Use search before click', body='## Procedure\nsearch first\n')}, top_k_skills=1)
    calls = {'n': 0}
    original = policy._retrieve_skills_for_task

    def counted(text: str):
        calls['n'] += 1
        return original(text)
    policy._retrieve_skills_for_task = counted
    policy.begin_episode('find red shoes under $50')
    policy._call_llm = lambda *a, **k: 'search[shoes]'
    policy.forward('page 2 of results', {'clickables': []}, recent_actions=[])
    policy.forward('page 3 of results', {'clickables': []}, recent_actions=[])
    assert calls['n'] == 1
