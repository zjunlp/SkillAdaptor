"""Codex CLI harness — ~/.codex/skills and repo-local .agents/skills (EvoSkill-compatible)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

from runtime.skill_export import build_frontmatter, sync_workspace_skills_to_codex

EVOLVED_SKILL_DIR = 'skill-adaptor-evolved'


def _codex_home() -> Path:
    return Path(os.environ.get('CODEX_HOME', Path.home() / '.codex'))


def ensure_codex_skill_markdown(skill_text: str, *, skill_id: str = EVOLVED_SKILL_DIR) -> str:
    """Codex requires YAML frontmatter (name + description) on every SKILL.md."""
    if skill_text.lstrip().startswith('---'):
        return skill_text
    fm = build_frontmatter(
        skill_id,
        'Evolved agent skill from SkillAdaptor',
        'Apply when the task matches the failure pattern this skill was adapted for.',
    )
    body = skill_text.strip()
    if body:
        return fm + body + '\n'
    return fm + f'# {skill_id}\n\nEvolved by SkillAdaptor.\n'


class CodexHarness:
    name = 'codex'

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = Path(project_root or Path.cwd())

    def _workspace_skills_dir(self) -> Path:
        return self.project_root / 'skills'

    def _codex_evolved_path(self) -> Path:
        return _codex_home() / 'skills' / EVOLVED_SKILL_DIR / 'SKILL.md'

    def _agents_evolved_path(self) -> Path:
        return self.project_root / '.agents' / 'skills' / EVOLVED_SKILL_DIR / 'SKILL.md'

    def prepare_runtime(self, *, model: str, api_key: str | None = None, base_url: str | None = None) -> None:
        (_codex_home() / 'skills').mkdir(parents=True, exist_ok=True)
        (self.project_root / '.agents' / 'skills').mkdir(parents=True, exist_ok=True)
        sync_workspace_skills_to_codex(self._workspace_skills_dir(), self.project_root)

    def inject_skill_text(self, skill_text: str, *, benchmark_root: Path, task_id: Optional[str] = None) -> None:
        if not skill_text:
            return
        md = ensure_codex_skill_markdown(skill_text)
        repo_skill_dir = benchmark_root / '.skill'
        repo_skill_dir.mkdir(parents=True, exist_ok=True)
        (repo_skill_dir / 'SKILL.md').write_text(md, encoding='utf-8')
        for target in (self._codex_evolved_path(), self._agents_evolved_path()):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(md, encoding='utf-8')
        sync_workspace_skills_to_codex(self._workspace_skills_dir(), self.project_root)

    def clear_skill_injection(self, *, benchmark_root: Path, task_id: Optional[str] = None) -> None:
        for skill_file in (
            benchmark_root / '.skill' / 'SKILL.md',
            self._codex_evolved_path(),
            self._agents_evolved_path(),
        ):
            if skill_file.exists():
                try:
                    skill_file.unlink()
                except OSError:
                    pass
        evolved_dir = _codex_home() / 'skills' / EVOLVED_SKILL_DIR
        if evolved_dir.exists() and not any(evolved_dir.iterdir()):
            try:
                evolved_dir.rmdir()
            except OSError:
                pass

    def purge_all_injections(self, *, benchmark_root: Path) -> None:
        self.clear_skill_injection(benchmark_root=benchmark_root)
        agents_evolved = self.project_root / '.agents' / 'skills' / EVOLVED_SKILL_DIR
        if agents_evolved.exists():
            shutil.rmtree(agents_evolved, ignore_errors=True)
