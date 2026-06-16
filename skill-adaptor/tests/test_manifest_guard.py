"""Manifest leakage guard tests."""

from __future__ import annotations
import pytest
from runtime.manifest_guard import validate_task_manifest
from runtime.task_loader import TaskManifest

def test_disjoint_manifest_passes():
    m = TaskManifest(name='micro', benchmark='pinchbench', input_tasks=['a', 'b', 'c'], validation_tasks=['d', 'e', 'f', 'g', 'h'], test_tasks=['i', 'j'], probe_mode=False)
    warnings, errors = validate_task_manifest(m)
    assert errors == []
    assert warnings == []

def test_overlap_without_probe_errors():
    m = TaskManifest(name='bad', benchmark='pinchbench', input_tasks=['a', 'b'], validation_tasks=['a', 'c', 'd', 'e', 'f'], test_tasks=[], probe_mode=False)
    _, errors = validate_task_manifest(m)
    assert any(('input_tasks ∩ validation_tasks' in e for e in errors))

def test_probe_mode_overlap_warns_not_errors():
    m = TaskManifest(name='smoke5', benchmark='pinchbench', input_tasks=['a', 'b', 'c'], validation_tasks=['a', 'b', 'c', 'd', 'e'], test_tasks=['f'], probe_mode=True, allow_train_val_overlap=True)
    warnings, errors = validate_task_manifest(m)
    assert errors == []
    assert any(('probe_mode' in w for w in warnings))

def test_validation_too_small_for_paper():
    m = TaskManifest(name='tiny', benchmark='pinchbench', input_tasks=['a'], validation_tasks=['b', 'c'], test_tasks=[], probe_mode=False)
    _, errors = validate_task_manifest(m)
    assert any(('validation_tasks has 2' in e for e in errors))
