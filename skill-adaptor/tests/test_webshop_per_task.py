"""WebShop per-task skill injection tests."""

from __future__ import annotations
from core.types import Skill
from adapters.webshop_adapter.llm_policy import SkillAugmentedLLMPolicy

def test_begin_episode_caches_skills(monkeypatch) -> None:
    skill = Skill(id='s1', title='Search products', description='Use search before click', body='## Procedure\nsearch first\n')
    policy = SkillAugmentedLLMPolicy({'api_key': 'x', 'base_url': 'http://test', 'model': 'gpt-4.1'}, skill_bank={'s1': skill}, top_k_skills=1)
    calls = {'n': 0}

    def fake_retrieve(text: str) -> list:
        calls['n'] += 1
        return [skill]

    monkeypatch.setattr(policy, '_retrieve_skills_for_task', fake_retrieve)
    policy.begin_episode('find red shoes under $50')
    policy._call_llm = lambda *a, **k: 'search[shoes]'
    policy.forward('page 2 of results', {'clickables': []}, recent_actions=[])
    policy.forward('page 3 of results', {'clickables': []}, recent_actions=[])
    assert calls['n'] == 1
