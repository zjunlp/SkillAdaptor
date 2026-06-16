"""Write skills directly to workspace folders (agentskills.io layout)."""

from __future__ import annotations
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from runtime.skill_export import format_skill_markdown
if TYPE_CHECKING:
    from core.types import Skill
Status = Literal['candidate', 'adopted']

def skill_to_export_row(skill: 'Skill') -> dict:
    return {'title': skill.title, 'description': skill.description, 'when_to_apply': skill.when_to_apply, 'body': skill.body}

def write_skill_folder(skills_root: Path, skill: 'Skill', *, status: Status='adopted') -> Path:
    skills_root.mkdir(parents=True, exist_ok=True)
    if status == 'candidate':
        base = skills_root / '_candidates' / skill.id
    else:
        base = skills_root / skill.id
    base.mkdir(parents=True, exist_ok=True)
    out = base / 'SKILL.md'
    md = format_skill_markdown(skill.id, skill_to_export_row(skill))
    out.write_text(md, encoding='utf-8')
    return out

def promote_candidate(skills_root: Path, skill_id: str) -> bool:
    src = skills_root / '_candidates' / skill_id
    dst = skills_root / skill_id
    if not src.exists():
        return False
    if dst.exists():
        shutil.rmtree(dst)
    shutil.move(str(src), str(dst))
    return True

def remove_candidate(skills_root: Path, skill_id: str) -> None:
    path = skills_root / '_candidates' / skill_id
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
