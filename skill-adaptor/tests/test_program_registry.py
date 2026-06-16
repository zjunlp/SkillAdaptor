"""Program registry snapshot tests."""

from __future__ import annotations
from runtime.program_registry import ProgramRegistry, ProgramSnapshot

def test_save_snapshot_no_git(tmp_path) -> None:
    reg = ProgramRegistry(tmp_path, git_branches=False)
    snap = ProgramSnapshot(name='iter-1-adopt-gen_a', iteration=1, adopted_skill_ids=['gen_a'], skill_count=1, delta_success=0.1)
    path = reg.save_snapshot(snap)
    assert path.exists()
    assert (reg.state_dir / 'current.json').exists()
    assert 'iter-1-adopt-gen_a' in reg.list_snapshots()
