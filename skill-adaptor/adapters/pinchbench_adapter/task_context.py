"""PinchBench task markdown resolution for Localizer / Generator."""

from __future__ import annotations
import os
from pathlib import Path
from core.task_context import TaskContextProvider, register_task_context_provider

class PinchBenchTaskContextProvider:

    def __init__(self, pinchbench_path: str, tasks_dir: str='tasks'):
        self.root = Path(pinchbench_path)
        self.tasks_root = self.root / tasks_dir

    def load_task_markdown(self, task_id: str) -> str:
        for path in (self.tasks_root / f'{task_id}.md', self.root / f'{task_id}.md'):
            if path.exists():
                return path.read_text(encoding='utf-8', errors='replace')
        return ''

def install_pinchbench_task_context(pinchbench_path: str | None=None, tasks_dir: str | None=None) -> None:
    root = pinchbench_path or os.environ.get('PINCHBENCH_PATH', '')
    if not root:
        return
    sub = tasks_dir or os.environ.get('PINCHBENCH_TASKS_DIR', 'tasks')
    register_task_context_provider(PinchBenchTaskContextProvider(root, sub))
