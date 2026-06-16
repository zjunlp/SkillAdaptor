"""Resolve agent harness by name or environment."""

from __future__ import annotations
import os
from pathlib import Path
from typing import Optional
from .base import AgentHarness
from .claude_code import ClaudeCodeHarness
from .openclaw import OpenClawHarness
_REGISTRY: dict[str, type] = {'openclaw': OpenClawHarness, 'claude-code': ClaudeCodeHarness, 'claude': ClaudeCodeHarness}

def get_harness(name: Optional[str]=None, *, project_root: Optional[Path]=None) -> AgentHarness:
    key = (name or os.environ.get('SkillAdaptor_HARNESS', 'openclaw')).strip().lower()
    cls = _REGISTRY.get(key)
    if cls is None:
        raise ValueError(f"Unknown harness {key!r}. Supported: {', '.join(sorted(_REGISTRY))}")
    if cls is ClaudeCodeHarness:
        return ClaudeCodeHarness(project_root=project_root)
    return cls()
