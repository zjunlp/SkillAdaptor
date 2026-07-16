"""OpenClaw agent harness — gateway, workspace skills, PinchBench .skill mirror."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from core.openclaw_agent_setup import prepare_openclaw_for_model
from core.openclaw_hygiene import clear_bootstrap_files, discover_workspace_root
from runtime.skill_inject import (
    EVOLVED_SKILL_DIR,
    ensure_skill_markdown,
    openclaw_skill_targets,
    write_and_verify_skill_files,
)

# Re-export for callers that import from this module.
ensure_openclaw_skill_markdown = ensure_skill_markdown


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

    def inject_skill_text(self, skill_text: str, *, benchmark_root: Path, task_id: Optional[str] = None) -> None:
        if not skill_text:
            return
        md = ensure_skill_markdown(skill_text)
        targets = openclaw_skill_targets(Path(benchmark_root), task_id=task_id)
        write_and_verify_skill_files(targets, md)

    def clear_skill_injection(self, *, benchmark_root: Path, task_id: Optional[str] = None) -> None:
        for skill_file in openclaw_skill_targets(Path(benchmark_root), task_id=task_id):
            if skill_file.exists():
                try:
                    skill_file.unlink()
                except OSError:
                    pass

    def purge_all_injections(self, *, benchmark_root: Path) -> None:
        self.clear_skill_injection(benchmark_root=benchmark_root)
