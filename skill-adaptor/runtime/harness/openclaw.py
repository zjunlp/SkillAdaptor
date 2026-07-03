"""OpenClaw agent harness — gateway, workspace skills, PinchBench .skill mirror."""

from __future__ import annotations
from pathlib import Path
from typing import Optional
from core.openclaw_agent_setup import prepare_openclaw_for_model
from core.openclaw_hygiene import clear_bootstrap_files, discover_workspace_root
EVOLVED_SKILL_DIR = 'skill-adaptor-evolved'

class OpenClawHarness:
    name = 'openclaw'

    def prepare_runtime(self, *, model: str, api_key: str | None = None, base_url: str | None = None) -> None:
        from core.openclaw_hygiene import ensure_gateway_running, openclaw_agent_id

        ensure_gateway_running(max_wait_s=25.0)
        prepare_openclaw_for_model(model, api_key=api_key, base_url=base_url, fix_main_auth=True)
        slug = openclaw_agent_id(model)
        agent_id = slug
        root = discover_workspace_root(agent_id)
        for ws in root.glob('*/agent_workspace'):
            clear_bootstrap_files(ws)
        oc_ws = Path.home() / '.openclaw' / 'workspace'
        if oc_ws.exists():
            clear_bootstrap_files(oc_ws)

    def _openclaw_skill_path(self) -> Path:
        return Path.home() / '.openclaw' / 'workspace' / 'skills' / EVOLVED_SKILL_DIR / 'SKILL.md'

    def inject_skill_text(self, skill_text: str, *, benchmark_root: Path, task_id: Optional[str]=None) -> None:
        if not skill_text:
            return
        repo_skill_dir = benchmark_root / '.skill'
        repo_skill_dir.mkdir(parents=True, exist_ok=True)
        (repo_skill_dir / 'SKILL.md').write_text(skill_text, encoding='utf-8')
        oc_dir = self._openclaw_skill_path().parent
        oc_dir.mkdir(parents=True, exist_ok=True)
        self._openclaw_skill_path().write_text(skill_text, encoding='utf-8')

    def clear_skill_injection(self, *, benchmark_root: Path, task_id: Optional[str]=None) -> None:
        for skill_file in (benchmark_root / '.skill' / 'SKILL.md', self._openclaw_skill_path()):
            if skill_file.exists():
                try:
                    skill_file.unlink()
                except OSError:
                    pass
        if task_id:
            legacy = benchmark_root / task_id / '.skill' / 'SKILL.md'
            if legacy.exists():
                try:
                    legacy.unlink()
                except OSError:
                    pass

    def purge_all_injections(self, *, benchmark_root: Path) -> None:
        self.clear_skill_injection(benchmark_root=benchmark_root)
