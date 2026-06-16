"""Reviser path: skill_wrong with attribution should revise (not generate)."""

from __future__ import annotations
from types import SimpleNamespace
from unittest.mock import MagicMock
from core.reviser import Reviser
from core.types import FaultType, LocalizedFault, Skill, SkillAttribution

def _mock_llm_revision_json() -> str:
    return '{\n  "revision_type": "targeted",\n  "revision_summary": "Add nginx log path precondition",\n  "targeted_changes": {\n    "when_to_apply": "When parsing nginx access logs",\n    "body_append": "## Preconditions\\n- Confirm log path exists before tail"\n  },\n  "impact_assessment": {\n    "severity_prevention": "high",\n    "generalization_risk": "low"\n  }\n}'

def test_reviser_increments_version_on_skill_wrong() -> None:
    skill = Skill(id='seed_log_parser', title='Log parser', description='Parse logs', body='## Steps\n1. tail the log', when_to_apply='log tasks', created_from='task_log_nginx_errors', version=1)
    fault = LocalizedFault(task_id='task_log_nginx_errors', step_index=2, fault_type=FaultType.SKILL_WRONG, observation='ENOENT: /var/log/nginx/access.log', wrong_action='tail /var/log/nginx/access.log', skills_at_fault=['seed_log_parser'], improvement_principle='Verify log path before tail')
    attr = SkillAttribution(skill_id='seed_log_parser', weight=0.9, reason='skill guided wrong path')
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=_mock_llm_revision_json()))])
    reviser = Reviser(llm_client=mock_client, model_name='test-model')
    revised = reviser.revise(skill, fault, attr)
    assert revised is not None
    assert revised.id == skill.id
    assert revised.version == 2
    assert 'Revision Note' in revised.body or 'targeted' in revised.body
    mock_client.chat.completions.create.assert_called_once()

def test_generate_candidates_prefers_revise_when_attributed() -> None:
    from core.orchestrator import SkillEvolveOrchestrator
    from core.types import Step, Trajectory
    skill = Skill(id='seed_git', title='Git rescue', description='Recover repo', body='git reset --hard', when_to_apply='git failures', created_from='task_git_rescue_recovery', version=1)
    traj = Trajectory(task_id='task_git_rescue_recovery', task_description='recover lost commits', success=False, steps=[Step(index=0, action='git reset --hard', observation='lost commits', skills_used=['seed_git'])])
    fault = LocalizedFault(task_id='task_git_rescue_recovery', step_index=0, fault_type=FaultType.SKILL_WRONG, observation='lost commits', wrong_action='git reset --hard', skills_at_fault=['seed_git'], improvement_principle='prefer reflog recovery')
    orch = SkillEvolveOrchestrator.__new__(SkillEvolveOrchestrator)
    orch.config = SimpleNamespace(attribution_weight_threshold=0.5)
    orch.llm_client = MagicMock()
    orch._skill_matcher = None
    orch.skill_bank = MagicMock()
    orch.skill_bank.list_skills.return_value = [skill]
    orch.skill_bank.deduplicate.side_effect = lambda xs: xs
    orch._get_rejection_summaries_for_prompt = lambda: []
    orch._is_similar_to_rejected = lambda _: False
    orch._on_skill_generated = MagicMock()
    revised_skill = skill.copy_with_revision()
    revised_skill.body = 'git reflog + cherry-pick'
    orch.linker = MagicMock()
    orch.linker.attribute.return_value = [SkillAttribution(skill_id='seed_git', weight=0.95, reason='destructive reset')]
    orch.linker.filter_high_confidence.side_effect = lambda attrs, _: attrs
    orch.reviser = MagicMock()
    orch.reviser.revise.return_value = revised_skill
    orch.generator = MagicMock()
    revised, new = orch._generate_candidates_for_fault(traj, fault)
    assert len(revised) == 1
    assert revised[0].version == 2
    assert new == []
    orch.reviser.revise.assert_called_once()
    orch.generator.generate.assert_not_called()
