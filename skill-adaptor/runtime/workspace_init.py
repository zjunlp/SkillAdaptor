"""Initialize SkillAdaptor plugin workspace (EvoSkill-init analogue, SkillAdaptor layout)."""

from __future__ import annotations
from pathlib import Path
from typing import Optional
from .project_config import ManifestSource, ProjectConfig, save_project_config
from .task_loader import write_manifest
from .task_sync import copy_bundled_template_manifest, manifest_from_project, sync_manifest_to_workspace
WORKSPACE_README = '# SkillAdaptor Workspace\n\n## Layout\n\n| Path | Role |\n|------|------|\n| `input_task/` | Training task stubs (validation split is auto / in manifest) |\n| `test_task/` | Optional held-out evaluation stubs |\n| `skills/` | Adopted `skills/<id>/SKILL.md` |\n| `.skill-adaptor/project.json` | Harness, benchmark, manifest mode |\n| `.skill-adaptor/active_manifest.json` | Resolved task lists for last run |\n\n## Run\n\n```powershell\ncd skill-adaptor\npython run_plugin.py --workspace <this-dir>\n# or: python run_plugin.py run --workspace <this-dir>\n```\n\nInit again: `python run_plugin.py init --workspace <this-dir> --template smoke5`\n'

def ensure_workspace_dirs(workspace: Path) -> None:
    for name in ('input_task', 'test_task', 'skills', '.skill-adaptor/artifacts', '.skill-adaptor/runs', '.skill-adaptor/programs'):
        (workspace / name).mkdir(parents=True, exist_ok=True)

def init_workspace(workspace: Path, *, benchmark: str='pinchbench', harness: str='openclaw', provider: str='relay-gpt41', model: str='gpt-4.1', max_iterations: int=2, template: Optional[str]=None, mode: str='bundled', auto_discover_limit: int=30) -> ProjectConfig:
    workspace = Path(workspace)
    ensure_workspace_dirs(workspace)
    manifest_source = ManifestSource(mode=mode, auto_discover_limit=auto_discover_limit)
    if template:
        bundled = copy_bundled_template_manifest(template)
        try:
            manifest_source.path = bundled.relative_to(_repo_root()).as_posix()
        except ValueError:
            manifest_source.path = str(bundled)
        manifest_source.mode = 'bundled'
    config = ProjectConfig(benchmark=benchmark, harness=harness, provider=provider, model=model, max_iterations=max_iterations, manifest=manifest_source)
    save_project_config(workspace, config)
    manifest = manifest_from_project(workspace, config)
    sync_manifest_to_workspace(workspace, manifest)
    write_manifest(workspace / '.skill-adaptor' / 'active_manifest.json', manifest)
    readme = workspace / 'README.md'
    if not readme.exists():
        readme.write_text(WORKSPACE_README, encoding='utf-8')
    return config

def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent
