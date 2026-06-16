"""Harness registry tests."""

from __future__ import annotations
from runtime.harness import get_harness
from runtime.harness.claude_code import ClaudeCodeHarness
from runtime.harness.openclaw import OpenClawHarness

def test_default_harness_is_openclaw(monkeypatch) -> None:
    monkeypatch.delenv('SkillAdaptor_HARNESS', raising=False)
    h = get_harness()
    assert isinstance(h, OpenClawHarness)

def test_claude_harness_alias(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv('SkillAdaptor_HARNESS', 'claude')
    h = get_harness(project_root=tmp_path)
    assert isinstance(h, ClaudeCodeHarness)

def test_claude_harness_syncs_adopted_skills(monkeypatch, tmp_path) -> None:
    ws = tmp_path / 'workspace'
    skill_dir = ws / 'skills' / 'gen_a_1'
    skill_dir.mkdir(parents=True)
    (skill_dir / 'SKILL.md').write_text('---\nname: gen-a-1\ndescription: test\n---\n\n# A\n', encoding='utf-8')
    h = ClaudeCodeHarness(project_root=ws)
    h.prepare_runtime(model='gpt-4.1')
    assert (ws / '.claude' / 'skills' / 'gen_a_1' / 'SKILL.md').exists()
