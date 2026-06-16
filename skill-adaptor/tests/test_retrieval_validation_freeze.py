"""Retrieval-scoped validation: unrelated val tasks frozen at baseline (no re-run)."""

from __future__ import annotations
from run_skillevolve import _metrics_from_task_results

def test_metrics_from_task_results_merge():
    tasks = ['a', 'b', 'c']
    tr = {'a': {'success': True, 'score': 1.0}, 'b': {'success': False, 'score': 0.2}, 'c': {'success': True, 'score': 0.8}}
    m = _metrics_from_task_results(tasks, tr)
    assert m['sample_size'] == 3
    assert abs(m['success_rate'] - 2 / 3) < 1e-06
    assert abs(m['avg_score'] - (1.0 + 0.2 + 0.8) / 3) < 1e-06

def test_freeze_yields_zero_delta_when_only_unrelated_change():
    tasks = ['hit', 'miss']
    baseline = {'task_results': {'hit': {'success': False, 'score': 0.3}, 'miss': {'success': True, 'score': 1.0}}}
    revised_tr = dict(baseline['task_results'])
    base_m = _metrics_from_task_results(tasks, baseline['task_results'])
    rev_m = _metrics_from_task_results(tasks, revised_tr)
    assert base_m['success_rate'] == rev_m['success_rate']
    assert base_m['avg_score'] == rev_m['avg_score']
