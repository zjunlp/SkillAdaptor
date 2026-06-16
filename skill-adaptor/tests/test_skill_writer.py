"""Skill writer tests."""

from __future__ import annotations
from pathlib import Path
from core.types import Skill
from runtime.skill_writer import promote_candidate, write_skill_folder

def test_write_candidate_and_promote(tmp_path: Path) -> None:
    skill = Skill(id='gen_task_x_1', title='Spreadsheet reconcile', description='Recompute totals before export', body='## Procedure\n1. Load sheet\n2. Sum column\n', when_to_apply='tabular deliverable tasks')
    root = tmp_path / 'skills'
    path = write_skill_folder(root, skill, status='candidate')
    assert path.exists()
    assert '_candidates' in str(path)
    assert promote_candidate(root, skill.id)
    assert (root / skill.id / 'SKILL.md').exists()
    assert not (root / '_candidates' / skill.id).exists()
