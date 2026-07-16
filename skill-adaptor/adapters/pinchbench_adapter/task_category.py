"""Read PinchBench task category from task markdown (for stratified validation)."""

from __future__ import annotations
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

@lru_cache(maxsize=512)
def get_task_category(task_id: str, tasks_dir: str | Path) -> str:
    root = Path(tasks_dir)
    # PinchBench markdown briefs
    for path in (root / f'{task_id}.md', root.parent / f'{task_id}.md'):
        if path.exists():
            for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
                m = re.match('^category:\\s*(\\S+)', line.strip(), re.I)
                if m:
                    return m.group(1).lower()
            break
    # Claw-Eval nested task.yaml (and any env that uses the same layout)
    yaml_path = root / task_id / 'task.yaml'
    if yaml_path.exists():
        try:
            from adapters.claw_eval_adapter.task_io import read_claw_eval_category

            cat = read_claw_eval_category(root, task_id)
            if cat:
                return cat
        except Exception:
            for line in yaml_path.read_text(encoding='utf-8', errors='replace').splitlines():
                m = re.match('^category:\\s*(\\S+)', line.strip(), re.I)
                if m:
                    return m.group(1).lower()
    tid = task_id.lower()
    if 'log_' in tid or 'nginx' in tid or 'ssh' in tid:
        return 'log_analysis'
    if 'spreadsheet' in tid or 'csv' in tid or 'data' in tid:
        return 'analysis'
    if 'sanity' in tid or 'productivity' in tid:
        return 'productivity'
    return 'coding'
