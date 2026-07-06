"""Claude Code harness — .claude/skills layout (optional claude-agent-sdk at execute time)."""

from __future__ import annotations
from pathlib import Path
from typing import Optional
from runtime.skill_export import sync_workspace_skills_to_claude
EVOLVED_SKILL_DIR = 'skill-adaptor-evolved'

class ClaudeCodeHarness:
    name = 'claude-code'

    def __init__(self, project_root: Optional[Path]=None):
        self.project_root = Path(project_root or Path.cwd())

    def _workspace_skills_dir(self) -> Path:
        return self.project_root / 'skills'

    def prepare_runtime(self, *, model: str, api_key: str | None = None, base_url: str | None = None) -> None:
        skills_root = self.project_root / '.claude' / 'skills'
        skills_root.mkdir(parents=True, exist_ok=True)
        sync_workspace_skills_to_claude(self._workspace_skills_dir(), self.project_root)

    def _merged_skill_md(self) -> Path:
        return self.project_root / '.claude' / 'skills' / EVOLVED_SKILL_DIR / 'SKILL.md'

    def inject_skill_text(self, skill_text: str, *, benchmark_root: Path, task_id: Optional[str]=None) -> None:
        if not skill_text:
            return
        repo_skill_dir = benchmark_root / '.skill'
        repo_skill_dir.mkdir(parents=True, exist_ok=True)
        (repo_skill_dir / 'SKILL.md').write_text(skill_text, encoding='utf-8')
        out = self._merged_skill_md()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(skill_text, encoding='utf-8')
        sync_workspace_skills_to_claude(self._workspace_skills_dir(), self.project_root)

    def clear_skill_injection(self, *, benchmark_root: Path, task_id: Optional[str]=None) -> None:
        for skill_file in (benchmark_root / '.skill' / 'SKILL.md', self._merged_skill_md()):
            if skill_file.exists():
                try:
                    skill_file.unlink()
                except OSError:
                    pass

    def purge_all_injections(self, *, benchmark_root: Path) -> None:
        self.clear_skill_injection(benchmark_root=benchmark_root)
