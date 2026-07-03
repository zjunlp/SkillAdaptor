"""Unified plugin host for OpenClaw / Claude Code skill self-evolution."""

from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any, Optional
from core.provider_config import ProviderProfile, resolve_and_apply, describe_profile
from .adapter_registry import get_run_callable, resolve_adapter
from .adapter_bootstrap import bootstrap_adapter_runtime
from .project_config import load_project_config
from .task_sync import manifest_from_project, sync_manifest_to_workspace
from .task_loader import TaskManifest, load_tasks_from_workspace, write_manifest
from runtime.harness import get_harness

class PluginHost:

    def __init__(self, workspace: Path, provider: str='auto', harness: Optional[str]=None):
        self.workspace = Path(workspace)
        self.provider = provider
        self.harness_name = harness or os.environ.get('SkillAdaptor_HARNESS', 'openclaw')
        self.state_dir = self.workspace / '.skill-adaptor'
        self._harness = get_harness(self.harness_name, project_root=self.workspace)

    def prepare_agent_runtime(
        self,
        model: str = 'gpt-4.1',
        *,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._harness.prepare_runtime(model=model, api_key=api_key, base_url=base_url)

    def prepare_openclaw_runtime(self, model: str='gpt-4.1') -> None:
        self.prepare_agent_runtime(model=model)

    def apply_provider(self, model: Optional[str]=None, provider: Optional[str]=None) -> ProviderProfile:
        prov = provider or self.provider
        profile = resolve_and_apply(prov, model=model)
        return profile

    def resolve_manifest(self, manifest_path: Optional[Path]=None, env: Optional[str]=None) -> TaskManifest:
        if manifest_path and manifest_path.exists():
            data = json.loads(manifest_path.read_text(encoding='utf-8'))
            return TaskManifest(name=data.get('name', 'manifest'), benchmark=data.get('benchmark', env or 'pinchbench'), input_tasks=list(data.get('input_tasks') or []), validation_tasks=list(data.get('validation_tasks') or []), test_tasks=list(data.get('test_tasks') or []), allow_train_val_overlap=bool(data.get('allow_train_val_overlap')))
        project = load_project_config(self.workspace)
        if project is not None:
            manifest = manifest_from_project(self.workspace, project)
            out = self.state_dir / 'active_manifest.json'
            write_manifest(out, manifest)
            return manifest
        spec = resolve_adapter(env)
        manifest = load_tasks_from_workspace(self.workspace, benchmark=spec.benchmark_key)
        out = self.state_dir / 'active_manifest.json'
        write_manifest(out, manifest)
        return manifest

    def run_evolution(self, args: Any, config: Any, *, env: Optional[str]=None, manifest: Optional[TaskManifest]=None) -> dict:
        spec = resolve_adapter(env or getattr(args, 'env', None))
        if spec.requires_path_env and (not os.environ.get(spec.requires_path_env)):
            raise RuntimeError(f'Adapter {spec.name} requires {spec.requires_path_env} in environment')
        bootstrap_adapter_runtime(spec)
        os.environ.setdefault('SkillAdaptor_BENCHMARK_ENV', spec.benchmark_key)
        profile = getattr(config, '_llm_profile', None)
        self.prepare_agent_runtime(
            getattr(config, 'model', 'gpt-4.1'),
            api_key=getattr(profile, 'api_key', None) if profile else None,
            base_url=getattr(profile, 'base_url', None) if profile else None,
        )
        config.agent_harness = self.harness_name
        os.environ.setdefault('SkillAdaptor_HARNESS', self.harness_name)
        if manifest:
            manifest_path = self.state_dir / 'active_manifest.json'
            write_manifest(manifest_path, manifest)
            args.task_manifest = str(manifest_path)
        run_fn = get_run_callable(spec)
        return run_fn(args, config)
