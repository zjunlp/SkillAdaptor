"""Load evolution tasks from plugin workspace."""

from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

@dataclass
class TaskManifest:
    name: str
    input_tasks: List[str] = field(default_factory=list)
    validation_tasks: List[str] = field(default_factory=list)
    test_tasks: List[str] = field(default_factory=list)
    allow_train_val_overlap: bool = False
    probe_mode: bool = False
    benchmark: str = 'openclaw'

    def to_dict(self) -> dict:
        return {'name': self.name, 'benchmark': self.benchmark, 'input_tasks': self.input_tasks, 'validation_tasks': self.validation_tasks, 'test_tasks': self.test_tasks, 'allow_train_val_overlap': self.allow_train_val_overlap, 'probe_mode': self.probe_mode}

def _read_task_ids_from_dir(folder: Path) -> List[str]:
    if not folder.exists():
        return []
    ids: List[str] = []
    for path in sorted(folder.iterdir()):
        if path.name.startswith('.'):
            continue
        if path.suffix == '.md':
            ids.append(path.stem)
        elif path.is_file() and (not path.suffix):
            ids.append(path.name)
        elif path.is_dir() and (path / 'task.yaml').exists():
            ids.append(path.name)
    return ids

def load_tasks_from_workspace(workspace: Path, *, benchmark: str='openclaw', val_ratio: float=0.2) -> TaskManifest:
    input_tasks = _read_task_ids_from_dir(workspace / 'input_task')
    test_tasks = _read_task_ids_from_dir(workspace / 'test_task')
    if not input_tasks:
        raise ValueError(f"No tasks in {workspace / 'input_task'}. Run: python run_plugin.py init --workspace <path> --template smoke5")
    n = len(input_tasks)
    val_count = max(1, int(n * val_ratio)) if n > 1 else 1
    if n > 1:
        val_count = min(val_count, n - 1)
    validation_tasks = input_tasks[:val_count]
    train_tasks = input_tasks[val_count:] if n > val_count else list(input_tasks)
    if not test_tasks:
        test_tasks = [t for t in input_tasks if t not in validation_tasks]
    return TaskManifest(name=workspace.name, benchmark=benchmark, input_tasks=train_tasks if train_tasks else list(input_tasks), validation_tasks=validation_tasks, test_tasks=test_tasks, allow_train_val_overlap=len(set(train_tasks or input_tasks) & set(validation_tasks)) > 0)

def write_manifest(path: Path, manifest: TaskManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2), encoding='utf-8')
