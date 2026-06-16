"""Global evolution lock (prevents concurrent OpenClaw runs)."""

from __future__ import annotations
import os
from pathlib import Path
import pytest
from runtime.evolution_guard import GlobalEvolutionLockError, cleanup_stale_locks, global_evolution_lock

def test_cleanup_stale_global_lock(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    lock = tmp_path / 'global.lock'
    monkeypatch.setenv('SkillAdaptor_GLOBAL_LOCK', str(lock))
    lock.write_text('{"pid": 999999999, "started_at": "x"}', encoding='utf-8')
    cleaned = cleanup_stale_locks()
    assert str(lock) in cleaned
    assert not lock.exists()

def test_cleanup_workspace_lock(tmp_path: Path) -> None:
    ws = tmp_path / 'ws'
    ws.mkdir()
    wlock = ws / '.skill-adaptor' / 'run.lock'
    wlock.parent.mkdir(parents=True)
    wlock.write_text(f'{{"pid": {os.getpid() + 99999}}}', encoding='utf-8')
    cleaned = cleanup_stale_locks(ws)
    assert str(wlock) in cleaned

def test_global_lock_exclusive(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    lock = tmp_path / 'global.lock'
    monkeypatch.setenv('SkillAdaptor_GLOBAL_LOCK', str(lock))
    with global_evolution_lock(label='a'):
        with pytest.raises(GlobalEvolutionLockError):
            with global_evolution_lock(label='b'):
                pass
    assert not lock.exists()
