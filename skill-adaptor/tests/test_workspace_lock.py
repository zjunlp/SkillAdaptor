"""Tests for workspace_run_lock."""

from __future__ import annotations
import os
from pathlib import Path
import pytest
from runtime.workspace_lock import WorkspaceRunLockError, workspace_run_lock

def test_workspace_lock_exclusive(tmp_path: Path) -> None:
    ws = tmp_path / 'ws'
    ws.mkdir()
    with workspace_run_lock(ws, label='a'):
        with pytest.raises(WorkspaceRunLockError):
            with workspace_run_lock(ws, label='b'):
                pass
    with workspace_run_lock(ws, label='c'):
        lock = ws / '.skill-adaptor' / 'run.lock'
        assert lock.exists()
        data = lock.read_text(encoding='utf-8')
        assert str(os.getpid()) in data
