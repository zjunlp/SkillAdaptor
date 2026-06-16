"""Tests for native-primary / extracted-auxiliary step merge."""

from core.trajectory_step_merge import merge_trajectory_steps

def test_native_primary_enriched():
    native = [{'index': 0, 'observation': 'search page', 'action': 'click[b001]', 'reward': 0, 'done': False, 'skills_used': ['s1']}, {'index': 1, 'observation': 'product page', 'action': 'buy now', 'reward': 0, 'done': False, 'skills_used': []}]
    aux = [{'index': 0, 'observation': 'search page with [Tool Result] error', 'action': 'click[b001]', 'reward': 0, 'done': False}]
    merged, label = merge_trajectory_steps(native, aux)
    assert label == 'native_primary_enriched'
    assert len(merged) == 2
    assert merged[0]['skills_used'] == ['s1']
    assert 'extracted detail' in merged[0]['observation'] or 'Tool Result' in merged[0]['observation']

def test_extracted_primary_when_native_empty():
    aux = [{'index': 0, 'observation': 'instr', 'action': 'exec({})', 'reward': 0, 'done': False}, {'index': 1, 'observation': 'result', 'action': 'read({})', 'reward': 0, 'done': False}]
    merged, label = merge_trajectory_steps([], aux)
    assert label == 'extracted_primary'
    assert len(merged) == 2

def test_sparse_native_uses_extracted_granularity():
    native = [{'index': 0, 'observation': 'task', 'action': 'run', 'reward': 0.5, 'done': True}]
    aux = [{'index': 0, 'observation': 'a', 'action': 'tool1({})', 'reward': 0, 'done': False}, {'index': 1, 'observation': 'b', 'action': 'tool2({})', 'reward': 0, 'done': False}]
    merged, label = merge_trajectory_steps(native, aux)
    assert label == 'extracted_primary_sparse_native'
    assert len(merged) == 2
    assert merged[-1]['reward'] == 0.5
    assert merged[-1]['done'] is True
