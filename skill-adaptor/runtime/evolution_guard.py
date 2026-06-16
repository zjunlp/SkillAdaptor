"""Global singleton lock: one evolution run across all workspaces (OpenClaw gateway)."""

from __future__ import annotations
import atexit
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

class GlobalEvolutionLockError(RuntimeError):
    pass


def _lock_path() -> Path:
    override = os.environ.get('SkillAdaptor_GLOBAL_LOCK')
    if override:
        return Path(override)
    return Path(tempfile.gettempdir()) / 'skill-adaptor-global.lock'

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

def cleanup_stale_locks(workspace: Path | None=None) -> list[str]:
    cleaned: list[str] = []
    gpath = _lock_path()
    if gpath.exists():
        info = _read_lock(gpath)
        if info is None or not _is_pid_alive(int(info.get('pid', 0))):
            try:
                gpath.unlink()
                cleaned.append(str(gpath))
            except OSError:
                pass
    if workspace is not None:
        wpath = workspace / '.skill-adaptor' / 'run.lock'
        if wpath.exists():
            info = _read_lock(wpath)
            if info is None or not _is_pid_alive(int(info.get('pid', 0))):
                try:
                    wpath.unlink()
                    cleaned.append(str(wpath))
                except OSError:
                    pass
    return cleaned

@contextmanager
def global_evolution_lock(*, label: str='evolution') -> Iterator[Path]:
    lock_path = _lock_path()
    pid = os.getpid()
    payload = {'pid': pid, 'label': label, 'started_at': datetime.now(timezone.utc).isoformat()}
    if lock_path.exists():
        info = _read_lock(lock_path) or {}
        holder_pid = int(info.get('pid', 0))
        if _is_pid_alive(holder_pid):
            raise GlobalEvolutionLockError(f"Global evolution lock held by pid={holder_pid} (started {info.get('started_at', '?')}). Only one run_plugin evolution at a time. Lock: {lock_path}")
        try:
            lock_path.unlink()
        except OSError:
            pass
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise GlobalEvolutionLockError(f'Could not acquire global lock: {lock_path}') from exc
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
