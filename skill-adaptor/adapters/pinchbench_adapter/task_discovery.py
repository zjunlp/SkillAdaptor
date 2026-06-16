"""Discover PinchBench tasks and stratified splits (benchmark adapter concern)."""

from __future__ import annotations
import random
import re
from pathlib import Path
from typing import Dict, List, Tuple
_CATEGORY_RE = re.compile('^category:\\s*(\\S+)', re.MULTILINE | re.IGNORECASE)

def _read_category(task_md: Path) -> str:
    try:
        text = task_md.read_text(encoding='utf-8', errors='replace')[:4000]
    except OSError:
        return 'general'
    m = _CATEGORY_RE.search(text)
    return m.group(1).lower() if m else 'general'

def list_tasks_with_categories(pinchbench_path: Path | str, tasks_dir: str='tasks') -> List[Tuple[str, str]]:
    root = Path(pinchbench_path)
    tasks_root = root / tasks_dir
    out: List[Tuple[str, str]] = []
    if not tasks_root.exists():
        return out
    for path in sorted(tasks_root.glob('task_*.md')):
        out.append((path.stem, _read_category(path)))
    return out

def stratified_task_split(items: List[Tuple[str, str]], *, train_ratio: float=0.6, val_ratio: float=0.2, test_ratio: float=0.2, seed: int=42, min_validation: int=5) -> Dict[str, List[str]]:
    if train_ratio + val_ratio + test_ratio > 1.0:
        raise ValueError('train_ratio + val_ratio + test_ratio must be <= 1.0')
    if not items:
        return {'input_tasks': [], 'validation_tasks': [], 'test_tasks': []}
    rng = random.Random(seed)
    by_cat: Dict[str, List[str]] = {}
    for tid, cat in items:
        by_cat.setdefault(cat, []).append(tid)
    input_tasks: List[str] = []
    validation_tasks: List[str] = []
    test_tasks: List[str] = []
    for cat, ids in by_cat.items():
        shuffled = list(ids)
        rng.shuffle(shuffled)
        n = len(shuffled)
        if n == 1:
            input_tasks.append(shuffled[0])
            continue
        n_train = max(1, int(n * train_ratio))
        n_val = max(1, int(n * val_ratio))
        n_test = max(0, int(n * test_ratio))
        while n_train + n_val + n_test > n:
            if n_test > 0:
                n_test -= 1
            elif n_train > 1:
                n_train -= 1
            else:
                n_val = max(1, n_val - 1)
        rest = n - n_train - n_val - n_test
        n_train += rest
        input_tasks.extend(shuffled[:n_train])
        validation_tasks.extend(shuffled[n_train:n_train + n_val])
        test_tasks.extend(shuffled[n_train + n_val:n_train + n_val + n_test])
    if len(validation_tasks) < min_validation and len(items) >= min_validation:
        all_ids = [t for t, _ in items]
        rng.shuffle(all_ids)
        validation_tasks = sorted(all_ids[:min_validation])
        input_tasks = sorted(all_ids[min_validation:])
        test_tail = max(1, len(all_ids) // 5)
        test_tasks = sorted(all_ids[-test_tail:])
        if not input_tasks:
            input_tasks = sorted(all_ids[:max(1, len(all_ids) - min_validation)])
    return {'input_tasks': sorted(set(input_tasks)), 'validation_tasks': sorted(set(validation_tasks)), 'test_tasks': sorted(set(test_tasks))}
