"""Claude Code harness — .claude/skills layout (optional claude-agent-sdk at execute time)."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from runtime.skill_export import sync_workspace_skills_to_claude
from runtime.skill_inject import (
    EVOLVED_SKILL_DIR,
    common_benchmark_skill_paths,
    ensure_skill_markdown,
    write_and_verify_skill_files,
)


class ClaudeCodeHarness:
    name = 'claude-code'

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = Path(project_root or Path.cwd())

    def _workspace_skills_dir(self) -> Path:
        return self.project_root / 'skills'

    def prepare_runtime(self, *, model: str, api_key: str | None = None, base_url: str | None = None) -> None:
        skills_root = self.project_root / '.claude' / 'skills'
        skills_root.mkdir(parents=True, exist_ok=True)
        sync_workspace_skills_to_claude(self._workspace_skills_dir(), self.project_root)

    def _inject_targets(self, benchmark_root: Path, task_id: Optional[str]) -> List[Path]:
        root = Path(benchmark_root)
        proj = self.project_root
        targets = common_benchmark_skill_paths(root, task_id=task_id)
        targets.extend(
            [
                root / '.claude' / 'skills' / EVOLVED_SKILL_DIR / 'SKILL.md',
                proj / '.claude' / 'skills' / EVOLVED_SKILL_DIR / 'SKILL.md',
                proj / 'skills' / EVOLVED_SKILL_DIR / 'SKILL.md',
            ]
        )
        # Dedup
        seen = set()
        out: List[Path] = []
        for p in targets:
            key = str(p)
            if key in seen:
                continue
            seen.add(key)
            out.append(p)
        return out

    def inject_skill_text(self, skill_text: str, *, benchmark_root: Path, task_id: Optional[str] = None) -> None:
        if not skill_text:
            return
        md = ensure_skill_markdown(skill_text)
        write_and_verify_skill_files(self._inject_targets(Path(benchmark_root), task_id), md)
        # Keep project_root aligned with the live agent cwd when possible.
        effective = Path(benchmark_root)
        sync_workspace_skills_to_claude(effective / 'skills', effective)
        if self.project_root.resolve() != effective.resolve():
            sync_workspace_skills_to_claude(self._workspace_skills_dir(), self.project_root)

    def clear_skill_injection(self, *, benchmark_root: Path, task_id: Optional[str] = None) -> None:
        for skill_file in self._inject_targets(Path(benchmark_root), task_id):
            if skill_file.exists():
                try:
                    skill_file.unlink()
                except OSError:
                    pass

    def purge_all_injections(self, *, benchmark_root: Path) -> None:
        self.clear_skill_injection(benchmark_root=benchmark_root)
