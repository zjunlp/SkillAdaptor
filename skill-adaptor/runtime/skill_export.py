"""Export adopted skills from JSON bank to plugin workspace SKILL.md files."""

from __future__ import annotations
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict

def claude_skill_name(skill_id: str) -> str:
    slug = re.sub('[^a-z0-9]+', '-', skill_id.lower()).strip('-')
    return slug or 'skill'

def _fold_yaml(value: str, width: int=240) -> str:
    text = ' '.join(value.split())
    if len(text) <= width:
        return text
    return text[:width - 3].rstrip() + '...'

def _strip_existing_frontmatter(body: str) -> tuple[Dict[str, str], str]:
    text = body.lstrip()
    if not text.startswith('---'):
        return ({}, body)
    parts = text.split('---', 2)
    if len(parts) < 3:
        return ({}, body)
    meta: Dict[str, str] = {}
    for line in parts[1].strip().splitlines():
        if ':' in line:
            k, v = line.split(':', 1)
            meta[k.strip()] = v.strip()
    return (meta, parts[2].lstrip('\n'))

def build_frontmatter(skill_id: str, description: str, when: str='') -> str:
    name = claude_skill_name(skill_id)
    desc_parts = [p for p in (description.strip(), when.strip()) if p]
    desc = _fold_yaml(' — '.join(desc_parts) if desc_parts else description or skill_id)
    return f'---\nname: {name}\ndescription: {desc}\n---\n\n'

def format_skill_markdown(skill_id: str, row: Dict[str, Any], *, claude_compat: bool=True) -> str:
    body = (row.get('body') or '').strip()
    title = str(row.get('title') or skill_id).strip()
    description = str(row.get('description') or '').strip()
    when = str(row.get('when_to_apply') or '').strip()
    if body.startswith('---'):
        _, inner = _strip_existing_frontmatter(body)
        body = inner
    if body and (body.startswith('# ') or body.startswith(f'# {title}')):
        content = body.rstrip() + '\n'
    else:
        parts: list[str] = [f'# {title}', '']
        if description:
            parts.extend([f'## Description\n{description}', ''])
        if when:
            parts.extend([f'## When to Apply\n{when}', ''])
        if body:
            parts.append(body.rstrip())
            parts.append('')
        content = '\n'.join(parts).rstrip() + '\n'
    if not claude_compat:
        return content
    fm = build_frontmatter(skill_id, description, when)
    if content.startswith('---'):
        return content
    return fm + content

def export_skills_to_workspace(skill_bank_path: Path, skills_dir: Path, *, layout: str='folder', claude_compat: bool=True) -> int:
    if not skill_bank_path.exists():
        return 0
    data = json.loads(skill_bank_path.read_text(encoding='utf-8'))
    skills: Dict[str, Any] = data.get('skills') or {}
    if not skills:
        return 0
    skills_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for sid, row in skills.items():
        if not isinstance(row, dict):
            continue
        md = format_skill_markdown(sid, row, claude_compat=claude_compat)
        if layout == 'flat':
            out = skills_dir / f'{sid}.md'
            out.write_text(md, encoding='utf-8')
        else:
            skill_dir = skills_dir / sid
            skill_dir.mkdir(parents=True, exist_ok=True)
            out = skill_dir / 'SKILL.md'
            out.write_text(md, encoding='utf-8')
        count += 1
    readme = skills_dir / 'README.md'
    if not readme.exists():
        readme.write_text('# Evolved Skills\n\nAuto-exported from SkillAdaptor runs (`run_plugin.py`).\n\nLayout: `skills/<skill_id>/SKILL.md` (YAML frontmatter + markdown body).\nClaude Code mirror: `.claude/skills/<skill_id>/SKILL.md`\n', encoding='utf-8')
    return count

def sync_workspace_skills_to_claude(workspace_skills_dir: Path, project_root: Path, *, exclude_candidates: bool=True) -> int:
    if not workspace_skills_dir.exists():
        return 0
    dest_root = Path(project_root) / '.claude' / 'skills'
    dest_root.mkdir(parents=True, exist_ok=True)
    count = 0
    for skill_dir in sorted(workspace_skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        if exclude_candidates and skill_dir.name.startswith('_'):
            continue
        src = skill_dir / 'SKILL.md'
        if not src.exists():
            continue
        dst_dir = dest_root / skill_dir.name
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst_dir / 'SKILL.md')
        count += 1
    return count

def _codex_home() -> Path:
    return Path(os.environ.get('CODEX_HOME', Path.home() / '.codex'))

def _hermes_home() -> Path:
    return Path(os.environ.get('HERMES_HOME', Path.home() / '.hermes'))


def sync_workspace_skills_to_hermes(
    workspace_skills_dir: Path,
    project_root: Path,
    *,
    category: str = 'skill-adaptor',
    exclude_candidates: bool = True,
) -> int:
    """Mirror workspace skills to Hermes category layout under HERMES_HOME and workspace/.hermes/."""
    if not workspace_skills_dir.exists():
        return 0
    dest_roots = [
        _hermes_home() / 'skills' / category,
        Path(project_root) / '.hermes' / 'skills' / category,
    ]
    count = 0
    for skill_dir in sorted(workspace_skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        if exclude_candidates and skill_dir.name.startswith('_'):
            continue
        src = skill_dir / 'SKILL.md'
        if not src.exists():
            continue
        for dest_root in dest_roots:
            dest_root.mkdir(parents=True, exist_ok=True)
            dst_dir = dest_root / skill_dir.name
            dst_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst_dir / 'SKILL.md')
        count += 1
    return count


def sync_workspace_skills_to_codex(workspace_skills_dir: Path, project_root: Path, *, exclude_candidates: bool=True) -> int:
    """Mirror workspace skills to Codex global + repo-local discovery paths (EvoSkill-style)."""
    if not workspace_skills_dir.exists():
        return 0
    dest_roots = [_codex_home() / 'skills', Path(project_root) / '.agents' / 'skills']
    count = 0
    for skill_dir in sorted(workspace_skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        if exclude_candidates and skill_dir.name.startswith('_'):
            continue
        src = skill_dir / 'SKILL.md'
        if not src.exists():
            continue
        for dest_root in dest_roots:
            dest_root.mkdir(parents=True, exist_ok=True)
            dst_dir = dest_root / skill_dir.name
            dst_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst_dir / 'SKILL.md')
        count += 1
    return count

def list_adopted_skill_ids(skill_bank_path: Path) -> list[str]:
    if not skill_bank_path.exists():
        return []
    data = json.loads(skill_bank_path.read_text(encoding='utf-8'))
    skills = data.get('skills') or {}
    return sorted(skills.keys())
