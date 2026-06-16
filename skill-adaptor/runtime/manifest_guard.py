"""Manifest split checks — prevent train/val/test leakage in plugin runs."""

from __future__ import annotations
from typing import List, Tuple
from .task_loader import TaskManifest
DEFAULT_MIN_VALIDATION = 5

def validate_task_manifest(manifest: TaskManifest, *, min_validation: int=DEFAULT_MIN_VALIDATION) -> Tuple[List[str], List[str]]:
    warnings: List[str] = []
    errors: List[str] = []
    input_set = set(manifest.input_tasks)
    val_set = set(manifest.validation_tasks)
    test_set = set(manifest.test_tasks)
    overlap_iv = input_set & val_set
    if overlap_iv and (not manifest.allow_train_val_overlap) and (not manifest.probe_mode):
        errors.append(f'input_tasks ∩ validation_tasks = {sorted(overlap_iv)} (set probe_mode=true only for quick probes, not paper eval)')
    elif overlap_iv and manifest.probe_mode:
        warnings.append(f'probe_mode: input/validation overlap {len(overlap_iv)} task(s) — not for paper eval')
    overlap_test = test_set & (input_set | val_set)
    if overlap_test and (not manifest.probe_mode):
        errors.append(f'test_tasks must be held-out: overlap with train/val = {sorted(overlap_test)}')
    elif overlap_test and manifest.probe_mode:
        warnings.append(f'probe_mode: test_tasks overlap train/val ({len(overlap_test)} tasks)')
    if not manifest.validation_tasks:
        errors.append('validation_tasks is empty (Validator needs ≥1 task)')
    elif len(manifest.validation_tasks) < min_validation and (not manifest.probe_mode):
        errors.append(f'validation_tasks has {len(manifest.validation_tasks)} items; need ≥{min_validation} for adoption gate (or probe_mode=true)')
    if not manifest.input_tasks:
        errors.append('input_tasks is empty — nothing to evolve from')
    return (warnings, errors)
