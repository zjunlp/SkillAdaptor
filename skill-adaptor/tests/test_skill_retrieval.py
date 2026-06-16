"""Unified retrieval gate — category + embedding."""

from __future__ import annotations
from core.skill_retrieval import RetrievalPolicy, SkillRetrievalGate
from core.types import Skill

def _gate(categories: dict[str, str]) -> SkillRetrievalGate:
    return SkillRetrievalGate(task_category_fn=lambda tid: categories.get(tid, ''), policy=RetrievalPolicy(require_category_match=True, allow_cross_category=False, same_category_embed_min=0.5, cross_task_embed_min=0.55))

def test_cross_category_blocked_even_with_medium_embed():
    gate = _gate({'task_git_rescue_recovery': 'coding', 'task_log_nginx_errors': 'log_analysis'})
    skill = Skill(id='g1', title='Git', description='git', body='body', created_from='task_git_rescue_recovery', domain_category='coding')
    d = gate.evaluate('task_log_nginx_errors', skill, 0.6)
    assert not d.inject
    assert 'category' in d.reason

def test_same_category_requires_embed_threshold():
    gate = _gate({'task_shell_command_generator': 'coding', 'task_test_generation': 'coding'})
    skill = Skill(id='s1', title='Shell', description='bash', body='body', created_from='task_shell_command_generator', domain_category='coding')
    low = gate.evaluate('task_test_generation', skill, 0.4)
    high = gate.evaluate('task_test_generation', skill, 0.58)
    assert not low.inject
    assert high.inject

def test_provenance_always_injects():
    gate = _gate({'task_git_rescue_recovery': 'coding'})
    skill = Skill(id='g1', title='Git', description='d', body='b', created_from='task_git_rescue_recovery', domain_category='coding')
    d = gate.evaluate('task_git_rescue_recovery', skill, 0.0)
    assert d.inject
    assert d.reason == 'provenance'
