"""Claw-Eval task context for Localizer / Generator / Reviser."""

from __future__ import annotations

import os
from pathlib import Path

from core.task_context import register_task_context_provider

from .task_io import task_yaml_as_markdown


class ClawEvalTaskContextProvider:
    """Expose Claw-Eval ``tasks/<id>/task.yaml`` as markdown task context."""

    def __init__(self, claw_eval_path: str, tasks_dir: str = 'tasks'):
        self.root = Path(claw_eval_path)
        self.tasks_root = self.root / tasks_dir

    def load_task_markdown(self, task_id: str) -> str:
        return task_yaml_as_markdown(self.tasks_root, task_id)


def install_claw_eval_task_context(claw_eval_path: str | None = None, tasks_dir: str | None = None) -> None:
    root = claw_eval_path or os.environ.get('CLAW_EVAL_PATH', '')
    if not root:
        return
    sub = tasks_dir or os.environ.get('CLAW_EVAL_TASKS_DIR', 'tasks')
    register_task_context_provider(ClawEvalTaskContextProvider(root, sub))
