"""Task discovery and workspace init tests."""

from __future__ import annotations
import json
import tempfile
from pathlib import Path
from adapters.pinchbench_adapter.task_discovery import stratified_task_split
from runtime.project_config import load_project_config
from runtime.task_sync import manifest_from_project
from runtime.workspace_init import init_workspace

def test_stratified_split_min_validation() -> None:
    items = [(f'task_{i}', 'coding' if i % 2 else 'shell') for i in range(12)]
    split = stratified_task_split(items, train_ratio=0.5, val_ratio=0.25, test_ratio=0.1, min_validation=5)
    assert len(split['validation_tasks']) >= 5
    assert split['input_tasks']

def test_stratified_split_disjoint_when_large_pool() -> None:
    items = [(f'task_{i}', 'coding' if i % 2 else 'shell') for i in range(20)]
    split = stratified_task_split(items, min_validation=5)
    iv = set(split['input_tasks']) & set(split['validation_tasks'])
    assert len(iv) == 0
    assert len(split['validation_tasks']) >= 5

def test_init_workspace_smoke5_template() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp) / 'ws'
        init_workspace(ws, template='smoke5')
        assert load_project_config(ws) is not None
        assert (ws / 'input_task').exists()
        assert (ws / '.skill-adaptor' / 'project.json').exists()
        manifest = manifest_from_project(ws, load_project_config(ws))
        assert len(manifest.validation_tasks) >= 5
        assert (ws / 'input_task' / 'task_git_rescue_recovery.md').exists()
