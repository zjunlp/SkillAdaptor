"""OpenClaw runtime hygiene utilities (benchmark-agnostic)."""

from __future__ import annotations
import subprocess
from pathlib import Path
from typing import Iterable, List, Optional, Tuple
from .openclaw_cli import resolve_openclaw_executable

def _run_openclaw(args: list[str], **kwargs):
    import platform
    exe = resolve_openclaw_executable()
    cmd = [exe, *args]
    if 'shell' not in kwargs:
        kwargs['shell'] = platform.system() == 'Windows'
    return subprocess.run(cmd, **kwargs)
DEFAULT_BOOTSTRAP_FILES: List[str] = ['BOOTSTRAP.md', 'AGENTS.md', 'SOUL.md', 'IDENTITY.md', 'USER.md', 'HEARTBEAT.md', 'TOOLS.md']

def openclaw_agent_slug(model: str) -> str:
    return model.replace('/', '-').replace(':', '-').replace('.', '-')

def openclaw_agent_id(model: str, *, prefix: str='bench') -> str:
    return f'{prefix}-{openclaw_agent_slug(model)}'

def get_agent_store_dir(agent_id: str) -> Path:
    base_dir = Path.home() / '.openclaw' / 'agents'
    direct_dir = base_dir / agent_id
    if direct_dir.exists():
        return direct_dir
    normalized_dir = base_dir / agent_id.replace(':', '-')
    if normalized_dir.exists():
        return normalized_dir
    return direct_dir

def cleanup_agent_sessions(agent_id: str) -> int:
    agent_dir = get_agent_store_dir(agent_id)
    sessions_dir = agent_dir / 'sessions'
    if not sessions_dir.exists():
        sessions_dir.mkdir(parents=True, exist_ok=True)
        return 0
    removed = 0
    for pattern in ('*.jsonl', '*.jsonl.lock', '*.trajectory.jsonl'):
        for path in sessions_dir.glob(pattern):
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    sessions_store = sessions_dir / 'sessions.json'
    if sessions_store.exists():
        try:
            sessions_store.unlink()
            removed += 1
        except OSError:
            pass
    return removed

def clear_bootstrap_files(workspace: Path, bootstrap_files: Iterable[str]=DEFAULT_BOOTSTRAP_FILES) -> List[str]:
    if not workspace.exists():
        return []
    removed: List[str] = []
    for filename in bootstrap_files:
        filepath = workspace / filename
        if filepath.exists():
            try:
                filepath.unlink()
                removed.append(filename)
            except OSError:
                pass
    return removed

def discover_workspace_root(agent_id: str) -> Path:
    try:
        result = _run_openclaw(['agents', 'list'], capture_output=True, text=True, check=False, shell=False)
    except RuntimeError as exc:
        raise RuntimeError(str(exc)) from exc
    if result.returncode != 0:
        raise RuntimeError(f"openclaw agents list failed (exit {result.returncode}): {(result.stderr or result.stdout or '').strip()}")
    normalized_id = agent_id.replace(':', '-')
    lines = result.stdout.split('\n')
    found_agent = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f'- {agent_id}') or stripped.startswith(f'- {normalized_id}'):
            found_agent = True
        elif found_agent and 'Workspace:' in line:
            workspace_str = line.split('Workspace:', 1)[1].strip()
            if workspace_str.startswith('~/'):
                workspace_str = str(Path.home() / workspace_str[2:])
            return Path(workspace_str)
        elif found_agent and stripped.startswith('-'):
            break
    raise RuntimeError(f'OpenClaw agent workspace not found for {agent_id!r}. Register the agent or run a PinchBench task once before evolution.')

def gateway_probe_ok(output: str) -> bool:
    return 'Connectivity probe: ok' in output or 'Reachable: yes' in output

def ensure_gateway_running(max_wait_s: float=30.0) -> Tuple[bool, str]:
    import platform
    import time
    last_output = ''
    for args in (['gateway', 'status'], ['gateway', 'probe']):
        try:
            result = _run_openclaw(args, capture_output=True, text=True, check=False, shell=False)
        except RuntimeError as exc:
            return (False, str(exc))
        last_output = f"{result.stdout or ''}{result.stderr or ''}"
        if gateway_probe_ok(last_output):
            return (True, last_output)
    if platform.system() == 'Windows':
        try:
            subprocess.run(['schtasks', '/Run', '/TN', 'OpenClaw Gateway'], capture_output=True, text=True, check=False)
        except FileNotFoundError:
            pass
    try:
        _run_openclaw(['gateway', 'start'], capture_output=True, text=True, check=False, shell=False)
    except RuntimeError:
        pass
    deadline = time.monotonic() + max_wait_s
    while time.monotonic() < deadline:
        time.sleep(3)
        try:
            result = _run_openclaw(['gateway', 'status'], capture_output=True, text=True, check=False, shell=False)
            last_output = f"{result.stdout or ''}{result.stderr or ''}"
            if gateway_probe_ok(last_output):
                return (True, last_output)
        except RuntimeError:
            break
    return (False, last_output)

def require_gateway_running(max_wait_s: float=30.0) -> str:
    ok, msg = ensure_gateway_running(max_wait_s=max_wait_s)
    if not ok:
        raise RuntimeError(f'OpenClaw Gateway unavailable: {msg}')
    return msg
