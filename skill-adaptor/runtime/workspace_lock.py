"""Exclusive lock: one active plugin evolution run per workspace."""

from __future__ import annotations
import atexit
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

class WorkspaceRunLockError(RuntimeError):
    pass


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    else:
        return True

def _read_lock(lock_path: Path) -> dict | None:
    if not lock_path.exists():
        return None
    try:
        return json.loads(lock_path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return None

def _stale_lock(lock_path: Path) -> bool:
    info = _read_lock(lock_path)
    if info is None:
        return True
    pid = int(info.get('pid', 0))
    return not _is_pid_alive(pid)

@contextmanager
def workspace_run_lock(workspace: Path, *, label: str='run') -> Iterator[Path]:
    lock_dir = workspace / '.skill-adaptor'
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / 'run.lock'
    pid = os.getpid()
    payload = {'pid': pid, 'label': label, 'started_at': datetime.now(timezone.utc).isoformat(), 'workspace': str(workspace.resolve())}
    if lock_path.exists() and (not _stale_lock(lock_path)):
        holder = _read_lock(lock_path) or {}
        raise WorkspaceRunLockError(f"Workspace locked by pid={holder.get('pid')} (started {holder.get('started_at', '?')}). Wait for it to finish or remove stale lock: {lock_path}")
    if lock_path.exists():
        try:
            lock_path.unlink()
        except OSError:
            pass
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise WorkspaceRunLockError(f'Could not acquire workspace lock: {lock_path}') from exc
    with os.fdopen(fd, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    def _release() -> None:
        try:
            if lock_path.exists():
                current = _read_lock(lock_path)
                if current and int(current.get('pid', -1)) == pid:
                    lock_path.unlink()
        except OSError:
            pass
    atexit.register(_release)
    try:
        yield lock_path
    finally:
        _release()
        try:
            atexit.unregister(_release)
        except Exception:
            pass
