"""Validator adoption gates and policy adapter with retrieval mocks."""

from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock
from core.types import Skill, ValidationResult
from core.validator import Validator, ValidationConfig
from adapters.pinchbench_adapter.policy_adapter import PinchBenchPolicyAdapter
from runtime.retrieval_index import RetrievalIndex, TaskRetrievalLabel
from core.skill_retrieval import RetrievalPolicy

def _result(**kwargs) -> ValidationResult:
    defaults = dict(skill_id='s1', delta_success=0.0, delta_avg_score=0.0, regression_detected=False, sample_size=5, baseline_metrics={}, revised_metrics={})
    defaults.update(kwargs)
    return ValidationResult(**defaults)

def test_source_task_adopts_on_any_strict_positive_delta():
    v = Validator(ValidationConfig(success_delta_threshold=0.005, avg_score_delta_threshold=0.005))
    skill = Skill(id='s1', title='t', description='d', body='b', created_from='task_git', domain_category='coding')
    full = _result(delta_success=0.0, delta_avg_score=0.0)
    source = _result(delta_success=0.0, delta_avg_score=0.001, sample_size=1)
    cat = _result(delta_success=0.0, delta_avg_score=0.0, sample_size=2)
    assert v.should_adopt_with_gates(full, source, cat, skill)

def test_source_task_rejects_zero_delta():
    v = Validator(ValidationConfig(success_delta_threshold=0.005, avg_score_delta_threshold=0.005))
    skill = Skill(id='s1', title='t', description='d', body='b', created_from='task_git', domain_category='coding')
    full = _result(delta_success=0.0, delta_avg_score=0.0)
    source = _result(delta_success=0.0, delta_avg_score=0.0, sample_size=1)
    assert not v.should_adopt_with_source_gate(full, source, skill)

def test_should_adopt_with_gates_category_hold():
    v = Validator(ValidationConfig(success_delta_threshold=0.005, avg_score_delta_threshold=0.005))
    skill = Skill(id='s1', title='t', description='d', body='b', created_from='task_git', domain_category='coding')
    full = _result(delta_avg_score=0.02)
    source = _result(delta_success=0.2, delta_avg_score=0.1, sample_size=1)
    cat = _result(delta_success=0.0, delta_avg_score=0.0, sample_size=2)
    assert v.should_adopt_with_gates(full, source, cat, skill)

def test_map_tasks_to_skills_no_global_inject_for_single_skill(tmp_path: Path):
    tasks_dir = tmp_path / 'tasks'
    tasks_dir.mkdir()
    (tasks_dir / 'task_git_rescue_recovery.md').write_text('category: coding\n', encoding='utf-8')
    (tasks_dir / 'task_log_nginx_errors.md').write_text('category: log_analysis\n', encoding='utf-8')
    adapter = PinchBenchPolicyAdapter(artifact_dir=tmp_path)
    adapter.matcher = MagicMock()
    adapter.matcher.build_task_description.return_value = 'nginx'
    git_skill = Skill(id='gen_git', title='Git', description='git', body='body', created_from='task_git_rescue_recovery', domain_category='coding')
    adapter.matcher.rank_skills_for_task.return_value = [(git_skill, 0.99)]
    mapped = adapter.map_tasks_to_skills(['task_log_nginx_errors'], {git_skill.id: git_skill}, tasks_dir=tasks_dir)
    assert mapped['task_log_nginx_errors'] == []

def test_policy_adapter_category_blocks_cross(tmp_path: Path):
    index = RetrievalIndex(labels={'task_git_rescue_recovery': TaskRetrievalLabel(category='coding'), 'task_log_nginx_errors': TaskRetrievalLabel(category='log_analysis')}, policy=RetrievalPolicy(require_category_match=True))
    adapter = PinchBenchPolicyAdapter(artifact_dir=tmp_path, retrieval_index=index)
    adapter.matcher = MagicMock()
    adapter.matcher.build_task_description.return_value = 'nginx logs'
    git_skill = Skill(id='gen_git', title='Git Recovery', description='recover repo', body='steps', created_from='task_git_rescue_recovery', domain_category='coding')
    adapter.matcher.rank_skills_for_task.return_value = [(git_skill, 0.62)]
    mapped = adapter.map_tasks_to_skills(['task_log_nginx_errors'], {git_skill.id: git_skill}, tasks_dir=tmp_path)
    assert mapped['task_log_nginx_errors'] == []
