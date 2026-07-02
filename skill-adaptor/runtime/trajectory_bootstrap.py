"""Copy external trajectory files into workspace artifacts (OpenClaw bridge + CLI)."""

from __future__ import annotations

import shutil
from pathlib import Path


def bootstrap_trajectories(workspace: Path, trajectories_path: str | Path) -> Path:
    """Copy trajectory file into ``<workspace>/.skill-adaptor/artifacts/trajectories/``."""
    src = Path(trajectories_path)
    if not src.exists():
        raise FileNotFoundError(f'input-trajectories not found: {src}')
    dest_dir = workspace / '.skill-adaptor' / 'artifacts' / 'trajectories'
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)
    return dest
