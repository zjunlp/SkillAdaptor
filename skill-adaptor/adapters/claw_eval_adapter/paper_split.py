"""Claw-Eval paper split helpers (66 adapt + 133 test) — no dataset committed.

Run locally against CLAW_EVAL_PATH/tasks to materialize manifests under
secrets/local/ (gitignored). Uploaded code only ships this builder.
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _read_meta(task_dir: Path) -> Tuple[str, str, bool]:
    """Return (category, difficulty, is_multiturn-ish)."""
    yaml_path = task_dir / 'task.yaml'
    cat, diff = 'unknown', 'unknown'
    multiturn = False
    if not yaml_path.exists():
        return cat, diff, multiturn
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(yaml_path.read_text(encoding='utf-8')) or {}
    except Exception:
        text = yaml_path.read_text(encoding='utf-8', errors='replace')
        data = {}
        for line in text.splitlines():
            if line.startswith('category:'):
                data['category'] = line.split(':', 1)[-1].strip()
            if line.startswith('difficulty:'):
                data['difficulty'] = line.split(':', 1)[-1].strip()
    cat = str(data.get('category') or 'unknown').strip()
    diff = str(data.get('difficulty') or 'unknown').strip()
    tags = data.get('tags') or []
    if isinstance(tags, list) and any('multi' in str(t).lower() for t in tags):
        multiturn = True
    prompt = data.get('prompt') or {}
    if isinstance(prompt, dict) and prompt.get('user_agent'):
        multiturn = True
    return cat, diff, multiturn


def list_claw_eval_tasks(tasks_dir: Path | str) -> List[Dict[str, Any]]:
    root = Path(tasks_dir)
    rows: List[Dict[str, Any]] = []
    if not root.exists():
        return rows
    for d in sorted(root.iterdir()):
        if d.is_dir() and (d / 'task.yaml').exists():
            cat, diff, mt = _read_meta(d)
            rows.append(
                {
                    'task_id': d.name,
                    'category': cat,
                    'difficulty': diff,
                    'multiturn': mt,
                    'stratum': f'{"mt" if mt else "st"}|{cat}|{diff}',
                }
            )
    return rows


def build_paper_style_split(
    tasks_dir: Path | str,
    *,
    n_adapt: int = 66,
    n_test: int = 133,
    seed: int = 42,
    val_ratio_of_adapt: float = 0.15,
) -> Dict[str, Any]:
    """Stratify by difficulty × (multi-turn domain proxy), then aggregate.

    Mirrors Appendix C.2 wording; exact official seed/list is not published here.
    """
    rows = list_claw_eval_tasks(tasks_dir)
    if not rows:
        raise ValueError(f'No claw-eval tasks under {tasks_dir}')
    rng = random.Random(seed)
    buckets: Dict[str, List[str]] = defaultdict(list)
    for r in rows:
        buckets[r['stratum']].append(r['task_id'])
    for key in buckets:
        rng.shuffle(buckets[key])

    adapt: List[str] = []
    test: List[str] = []
    # Proportional draw until quotas filled
    total = len(rows)
    target_adapt = min(n_adapt, total)
    target_test = min(n_test, max(0, total - target_adapt))

    # Round-robin strata to keep balance
    keys = sorted(buckets.keys())
    while len(adapt) < target_adapt or len(test) < target_test:
        progressed = False
        for key in keys:
            bucket = buckets[key]
            if not bucket:
                continue
            tid = bucket.pop()
            # Prefer filling adapt first with ~adapt/(adapt+test) share per stratum
            prefer_adapt = len(adapt) < target_adapt and (
                len(test) >= target_test
                or (len(adapt) / max(1, target_adapt)) <= (len(test) / max(1, target_test))
            )
            if prefer_adapt and len(adapt) < target_adapt:
                adapt.append(tid)
                progressed = True
            elif len(test) < target_test:
                test.append(tid)
                progressed = True
            elif len(adapt) < target_adapt:
                adapt.append(tid)
                progressed = True
        if not progressed:
            break

    rng.shuffle(adapt)
    n_val = max(1, int(round(len(adapt) * val_ratio_of_adapt))) if adapt else 0
    validation = adapt[:n_val]
    # Paper uses adapt set for skill adaptation; keep validation as subset with overlap allowed for micro
    return {
        'name': 'claw_eval_paper_style_66_133',
        'benchmark': 'claw-eval',
        'description': (
            'Locally generated stratified split approximating Appendix C.2 '
            '(66 adaptation + 133 test). NOT an official published ID list — '
            'regenerate with build_paper_style_split; do not commit task IDs.'
        ),
        'seed': seed,
        'input_tasks': adapt,
        'validation_tasks': validation,
        'test_tasks': test,
        'allow_train_val_overlap': True,
        'notes': {
            'n_adapt': len(adapt),
            'n_test': len(test),
            'n_total_available': total,
            'strata': {k: len(v) for k, v in buckets.items()},
            'pass_at_k': 3,
            'do_not_commit': True,
        },
    }


def write_split_manifest(payload: Dict[str, Any], path: Path | str) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return out
