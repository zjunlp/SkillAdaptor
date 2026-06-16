"""Sync benchmark tasks into plugin workspace folders."""

from __future__ import annotations
import json
import os
from pathlib import Path
from typing import List, Optional
from core.task_context import truncate_task_markdown_for_inference
from .project_config import ManifestSource, ProjectConfig
from .task_loader import TaskManifest, write_manifest

def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent

def resolve_bundled_manifest(path: str) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    candidates = [_repo_root() / path, _repo_root() / 'benchmarks' / 'manifests' / path, Path.cwd() / path]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]

def write_task_stub(workspace: Path, folder: str, task_id: str, body: str) -> Path:
    dest_dir = workspace / folder
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f'{task_id}.md'
    if not out.exists():
        out.write_text(body.rstrip() + '\n', encoding='utf-8')
    return out

def stub_from_pinchbench_task(pinchbench_path: Path, task_id: str, tasks_dir: str='tasks') -> str:
    for path in (pinchbench_path / tasks_dir / f'{task_id}.md', pinchbench_path / f'{task_id}.md'):
        if path.exists():
            full = path.read_text(encoding='utf-8', errors='replace')
            brief = truncate_task_markdown_for_inference(full, max_chars=1800)
            return f'# {task_id}\n\n{brief}\n'
    return f'# {task_id}\n\n(SkillAdaptor workspace stub — run with PINCHBENCH_PATH for full task.)\n'

def sync_manifest_to_workspace(workspace: Path, manifest: TaskManifest, *, pinchbench_path: Optional[Path]=None, tasks_dir: str='tasks') -> None:
    pb = pinchbench_path or Path(os.environ.get('PINCHBENCH_PATH', ''))

    def _body(tid: str) -> str:
        if pb and pb.exists() and (manifest.benchmark in ('pinchbench', 'openclaw-generic')):
            return stub_from_pinchbench_task(pb, tid, tasks_dir)
        return f'# {tid}\n\n(SkillAdaptor task stub)\n'
    for tid in manifest.input_tasks:
        write_task_stub(workspace, 'input_task', tid, _body(tid))
    for tid in manifest.test_tasks:
        if tid not in manifest.input_tasks:
            write_task_stub(workspace, 'test_task', tid, _body(tid))
    write_manifest(workspace / '.skill-adaptor' / 'active_manifest.json', manifest)

def manifest_from_project(workspace: Path, config: ProjectConfig) -> TaskManifest:
    ms = config.manifest
    if ms.mode == 'bundled' and ms.path:
        manifest_path = resolve_bundled_manifest(ms.path)
        data = json.loads(manifest_path.read_text(encoding='utf-8'))
        return TaskManifest(name=data.get('name', manifest_path.stem), benchmark=data.get('benchmark', config.benchmark), input_tasks=list(data.get('input_tasks') or []), validation_tasks=list(data.get('validation_tasks') or []), test_tasks=list(data.get('test_tasks') or []), allow_train_val_overlap=bool(data.get('allow_train_val_overlap')), probe_mode=bool(data.get('probe_mode')))
    if ms.mode == 'auto_discover':
        pb = os.environ.get('PINCHBENCH_PATH', '')
        if not pb:
            raise ValueError('auto_discover requires PINCHBENCH_PATH')
        from adapters.pinchbench_adapter.task_discovery import list_tasks_with_categories, stratified_task_split
        tasks_dir = os.environ.get('PINCHBENCH_TASKS_DIR', 'tasks')
        items = list_tasks_with_categories(pb, tasks_dir)
        if ms.auto_discover_limit > 0:
            items = items[:ms.auto_discover_limit]
        split = stratified_task_split(items, train_ratio=ms.train_ratio, val_ratio=ms.val_ratio, test_ratio=ms.test_ratio, min_validation=ms.min_validation_tasks)
        return TaskManifest(name=f'auto_{Path(pb).name}', benchmark=config.benchmark, input_tasks=split['input_tasks'], validation_tasks=split['validation_tasks'], test_tasks=split['test_tasks'], allow_train_val_overlap=len(set(split['input_tasks']) & set(split['validation_tasks'])) > 0)
    from .task_loader import load_tasks_from_workspace
    return load_tasks_from_workspace(workspace, benchmark=config.benchmark)
_TEMPLATE_ALIASES = {'smoke5': 'pinchbench_smoke_5.json', 'smoke_5': 'pinchbench_smoke_5.json', 'smoke2': 'pinchbench_smoke_2.json', 'mix_b5': 'pinchbench_mix_b5.json', 'micro8': 'pinchbench_micro_8.json', 'webshop_micro': 'webshop_micro_8.json', 'claw_micro': 'claw_eval_micro_6.json'}

def copy_bundled_template_manifest(template: str) -> Path:
    key = template.strip()
    name = _TEMPLATE_ALIASES.get(key, key)
    if not name.endswith('.json'):
        name = f'{name}.json' if name.startswith('pinchbench_') else f'pinchbench_{name}.json'
    path = _repo_root() / 'benchmarks' / 'manifests' / name
    if not path.exists():
        raise FileNotFoundError(f'Template manifest not found: {path}')
    return path
