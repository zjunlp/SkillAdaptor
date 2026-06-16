"""Agent harness protocol — OpenClaw, Claude Code, and other coding agents."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class AgentHarness(Protocol):
    name: str

    def prepare_runtime(self, *, model: str) -> None: ...

    def inject_skill_text(
        self,
        skill_text: str,
        *,
        benchmark_root: Path,
        task_id: Optional[str] = None,
    ) -> None: ...

    def clear_skill_injection(
        self,
        *,
        benchmark_root: Path,
        task_id: Optional[str] = None,
    ) -> None: ...

    def purge_all_injections(self, *, benchmark_root: Path) -> None: ...
