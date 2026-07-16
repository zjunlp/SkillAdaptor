"""Hermes Agent harness — ~/.hermes/skills/<category>/<skill_id>/SKILL.md."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List, Optional

from runtime.skill_export import sync_workspace_skills_to_hermes
from runtime.skill_inject import (
    EVOLVED_SKILL_DIR,
    common_benchmark_skill_paths,
    ensure_skill_markdown,
    write_and_verify_skill_files,
)

HERMES_SKILL_CATEGORY = 'skill-adaptor'
ensure_hermes_skill_markdown = ensure_skill_markdown


def _hermes_home() -> Path:
    return Path(os.environ.get('HERMES_HOME', Path.home() / '.hermes'))


class HermesHarness:
    name = 'hermes'

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = Path(project_root or Path.cwd())

    def _workspace_skills_dir(self) -> Path:
        return self.project_root / 'skills'

    def _inject_targets(self, benchmark_root: Path, task_id: Optional[str]) -> List[Path]:
        root = Path(benchmark_root)
        proj = self.project_root
        targets = common_benchmark_skill_paths(root, task_id=task_id)
        for base in (root, proj, _hermes_home()):
            if base == _hermes_home():
                targets.append(
                    base / 'skills' / HERMES_SKILL_CATEGORY / EVOLVED_SKILL_DIR / 'SKILL.md'
                )
            else:
                targets.append(
                    base / '.hermes' / 'skills' / HERMES_SKILL_CATEGORY / EVOLVED_SKILL_DIR / 'SKILL.md'
                )
                targets.append(base / 'skills' / EVOLVED_SKILL_DIR / 'SKILL.md')
        seen = set()
        out: List[Path] = []
        for p in targets:
            key = str(p)
            if key in seen:
                continue
            seen.add(key)
            out.append(p)
        return out

    def prepare_runtime(self, *, model: str, api_key: str | None = None, base_url: str | None = None) -> None:
        (_hermes_home() / 'skills' / HERMES_SKILL_CATEGORY).mkdir(parents=True, exist_ok=True)
        (self.project_root / '.hermes' / 'skills' / HERMES_SKILL_CATEGORY).mkdir(parents=True, exist_ok=True)
        sync_workspace_skills_to_hermes(self._workspace_skills_dir(), self.project_root)

    def inject_skill_text(self, skill_text: str, *, benchmark_root: Path, task_id: Optional[str] = None) -> None:
        if not skill_text:
            return
        md = ensure_skill_markdown(skill_text)
        write_and_verify_skill_files(self._inject_targets(Path(benchmark_root), task_id), md)
        effective = Path(benchmark_root)
        sync_workspace_skills_to_hermes(effective / 'skills', effective)
        if self.project_root.resolve() != effective.resolve():
            sync_workspace_skills_to_hermes(self._workspace_skills_dir(), self.project_root)

    def clear_skill_injection(self, *, benchmark_root: Path, task_id: Optional[str] = None) -> None:
        for skill_file in self._inject_targets(Path(benchmark_root), task_id):
            if skill_file.exists():
                try:
                    skill_file.unlink()
                except OSError:
                    pass
        evolved_dir = _hermes_home() / 'skills' / HERMES_SKILL_CATEGORY / EVOLVED_SKILL_DIR
        if evolved_dir.exists() and not any(evolved_dir.iterdir()):
            try:
                evolved_dir.rmdir()
            except OSError:
                pass

    def purge_all_injections(self, *, benchmark_root: Path) -> None:
        self.clear_skill_injection(benchmark_root=benchmark_root)
        for base in (self.project_root, Path(benchmark_root)):
            ws_evolved = base / '.hermes' / 'skills' / HERMES_SKILL_CATEGORY / EVOLVED_SKILL_DIR
            if ws_evolved.exists():
                shutil.rmtree(ws_evolved, ignore_errors=True)
