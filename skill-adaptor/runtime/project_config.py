"""Workspace project config (SkillAdaptor `.skill-adaptor/project.json`)."""

from __future__ import annotations
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

@dataclass
class ManifestSource:
    mode: str = 'folders'
    path: Optional[str] = None
    train_ratio: float = 0.6
    val_ratio: float = 0.2
    test_ratio: float = 0.2
    auto_discover_limit: int = 30
    min_validation_tasks: int = 5

@dataclass
class ProjectConfig:
    version: int = 1
    benchmark: str = 'pinchbench'
    harness: str = 'openclaw'
    provider: str = 'auto'
    model: str = 'gpt-4.1'
    max_iterations: int = 2
    manifest: ManifestSource = field(default_factory=ManifestSource)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProjectConfig':
        manifest_raw = data.get('manifest') or {}
        manifest = ManifestSource(**{k: v for k, v in manifest_raw.items() if k in ManifestSource.__dataclass_fields__})
        fields = {k: v for k, v in data.items() if k in cls.__dataclass_fields__ and k != 'manifest'}
        return cls(manifest=manifest, **fields)

def project_config_path(workspace: Path) -> Path:
    return workspace / '.skill-adaptor' / 'project.json'

def load_project_config(workspace: Path) -> Optional[ProjectConfig]:
    path = project_config_path(workspace)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding='utf-8'))
    return ProjectConfig.from_dict(data)

def save_project_config(workspace: Path, config: ProjectConfig) -> Path:
    path = project_config_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.to_dict(), ensure_ascii=False, indent=2), encoding='utf-8')
    return path
