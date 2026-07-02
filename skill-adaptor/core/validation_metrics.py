"""Adoption metrics: injected-task deltas + frozen-task regression checks."""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from core.types import ValidationResult


def metrics_from_task_results(task_ids: List[str], task_results: Dict[str, Any]) -> Dict[str, Any]:
    rows = [task_results[tid] for tid in task_ids if tid in task_results and isinstance(task_results[tid], dict)]
    if not rows:
        return {'success_rate': 0.0, 'avg_score': 0.0, 'sample_size': 0, 'task_results': {}}
    success_count = sum(1 for r in rows if r.get('success'))
    total_score = sum(float(r.get('score', 0.0)) for r in rows)
    n = len(rows)
    return {
        'success_rate': success_count / n,
        'avg_score': total_score / n,
        'sample_size': n,
        'task_results': {tid: task_results[tid] for tid in task_ids if tid in task_results},
    }


def frozen_tasks_regressed(frozen_ids: List[str], baseline_tr: Dict[str, Any], revised_tr: Dict[str, Any]) -> bool:
    for tid in frozen_ids:
        b = baseline_tr.get(tid)
        r = revised_tr.get(tid)
        if not isinstance(b, dict) or not isinstance(r, dict):
            continue
        if bool(b.get('success')) and not bool(r.get('success')):
            return True
        if float(r.get('score', 0.0)) < float(b.get('score', 0.0)) - 1e-9:
            return True
    return False


def resolve_adoption_pair(
    baseline_metrics: Dict[str, Any],
    revised_metrics: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any], bool, List[str]]:
    """Return (baseline_adopt, revised_adopt, frozen_regression, adoption_scope)."""
    adoption_scope = list(revised_metrics.get('adoption_scope') or [])
    if not adoption_scope:
        return baseline_metrics, revised_metrics, False, []
    base_tr = baseline_metrics.get('task_results') or {}
    rev_tr = revised_metrics.get('task_results') or {}
    frozen = list(revised_metrics.get('retrieval_frozen_tasks') or [])
    frozen_regression = frozen_tasks_regressed(frozen, base_tr, rev_tr) if frozen else False
    baseline_adopt = metrics_from_task_results(adoption_scope, base_tr)
    revised_adopt = metrics_from_task_results(adoption_scope, rev_tr)
    return baseline_adopt, revised_adopt, frozen_regression, adoption_scope


def source_result_from_full(full_result: 'ValidationResult', source_task: str) -> Optional['ValidationResult']:
    """Per-task Δ for source gate diagnostics — same A/B run as injected Q′ (no extra re-execution)."""
    from core.types import ValidationResult

    baseline = full_result.baseline_metrics or {}
    revised = full_result.revised_metrics or {}
    base_tr = baseline.get('task_results') or {}
    rev_tr = revised.get('task_results') or {}
    bt = base_tr.get(source_task)
    rt = rev_tr.get(source_task)
    if not isinstance(bt, dict) or not isinstance(rt, dict):
        return None
    b_succ = bool(bt.get('success'))
    r_succ = bool(rt.get('success'))
    b_score = float(bt.get('score', 0.0))
    r_score = float(rt.get('score', 0.0))
    regression = (b_succ and not r_succ) or r_score < b_score - 1e-9
    return ValidationResult(
        skill_id=full_result.skill_id,
        delta_success=float(r_succ) - float(b_succ),
        delta_avg_score=r_score - b_score,
        regression_detected=regression,
        sample_size=1,
        baseline_metrics=baseline,
        revised_metrics=revised,
    )
