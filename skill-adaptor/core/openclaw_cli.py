"""Resolve OpenClaw CLI on Windows/macOS/Linux — npm shims included."""

from __future__ import annotations
import os
import shutil
import sys
from pathlib import Path
from typing import List

def _candidate_path_dirs() -> List[str]:
    dirs: List[str] = []
    for key in ('OPENCLAW_CLI_DIR',):
        val = os.environ.get(key, '').strip()
        if val:
            dirs.append(val)
    if sys.platform == 'win32':
        npm = Path.home() / 'AppData' / 'Roaming' / 'npm'
        if npm.exists():
            dirs.append(str(npm))
    path = os.environ.get('PATH', '')
    if path:
        dirs.extend(path.split(os.pathsep))
    return dirs

def resolve_openclaw_executable() -> str:
    for env_key in ('OPENCLAW_CLI', 'OPENCLAW_CMD'):
        explicit = os.environ.get(env_key, '').strip()
        if explicit:
            p = Path(explicit)
            if p.exists():
                return str(p)
            found = shutil.which(explicit)
            if found:
                return found
    path_dirs = _candidate_path_dirs()
    merged = os.pathsep.join(path_dirs)
    for name in ('openclaw', 'openclaw.cmd', 'openclaw.exe'):
        found = shutil.which(name, path=merged)
        if found:
            return found
    raise RuntimeError('openclaw CLI not found. Install: npm install -g openclaw\nThen ensure %AppData%\\npm is on PATH, or set OPENCLAW_CLI to the full path.\nWindows: . scripts\\load_secrets.ps1  (prepends npm to PATH)')
