"""Tests for runtime.skill_export."""

from __future__ import annotations
import json
from pathlib import Path
from runtime.skill_export import build_frontmatter, export_skills_to_workspace, format_skill_markdown, list_adopted_skill_ids, sync_workspace_skills_to_claude

def test_format_skill_markdown_claude_frontmatter() -> None:
    row = {'title': 'Git Skill', 'description': 'Do git things', 'when_to_apply': 'On git failure', 'body': '## Procedure\n1. reflog\n'}
    md = format_skill_markdown('gen_task_git_1', row)
    assert md.startswith('---\nname: gen-task-git-1\n')
    assert 'description:' in md.split('---')[1]
    assert '# Git Skill' in md
    assert '## Procedure' in md

def test_format_skill_markdown_dedupes_body() -> None:
    row = {'title': 'Git Skill', 'description': 'Do git things', 'when_to_apply': 'On git failure', 'body': '# Git Skill\n\n## Description\nDo git things\n\n## Procedure\n1. reflog\n'}
    md = format_skill_markdown('git_1', row)
    assert md.startswith('---')
    assert md.count('## Description') == 1

def test_export_folder_layout(tmp_path: Path) -> None:
    bank = tmp_path / 'bank.json'
    bank.write_text(json.dumps({'skills': {'skill_a': {'id': 'skill_a', 'title': 'Skill A', 'description': 'Helps with A', 'body': '## Procedure\n1. Do A\n'}}}), encoding='utf-8')
    out_dir = tmp_path / 'skills'
    n = export_skills_to_workspace(bank, out_dir, layout='folder')
    assert n == 1
    text = (out_dir / 'skill_a' / 'SKILL.md').read_text(encoding='utf-8')
    assert text.startswith('---')
    assert list_adopted_skill_ids(bank) == ['skill_a']

def test_sync_workspace_skills_to_claude(tmp_path: Path) -> None:
    ws_skills = tmp_path / 'skills'
    skill_dir = ws_skills / 'gen_task_x_1'
    skill_dir.mkdir(parents=True)
    (skill_dir / 'SKILL.md').write_text(build_frontmatter('gen_task_x_1', 'Test skill') + '# Test\n', encoding='utf-8')
    project = tmp_path / 'workspace'
    project.mkdir()
    n = sync_workspace_skills_to_claude(ws_skills, project)
    assert n == 1
    assert (project / '.claude' / 'skills' / 'gen_task_x_1' / 'SKILL.md').exists()
