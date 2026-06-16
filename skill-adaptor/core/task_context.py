"""Benchmark-agnostic task context loading (registry + explicit paths)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Protocol

_ANSWER_SECTION_STOPS = (
    "## Expected Behavior",
    "## Grading Criteria",
    "## Automated Checks",
    "Key expected values",
)


class TaskContextNotFoundError(FileNotFoundError):
    pass


class TaskContextProvider(Protocol):
    def load_task_markdown(self, task_id: str) -> str: ...


_provider: Optional[TaskContextProvider] = None


def register_task_context_provider(provider: Optional[TaskContextProvider]) -> None:
    global _provider
    _provider = provider


def truncate_task_markdown_for_inference(markdown: str, *, max_chars: int = 2500) -> str:
    if not markdown.strip():
        return ""
    text = markdown
    for stop in _ANSWER_SECTION_STOPS:
        idx = text.find(stop)
        if idx > 0:
            text = text[:idx]
    return text[:max_chars]


def _generic_task_paths(task_id: str) -> list[Path]:
    paths: list[Path] = []
    for env_key in ("TASKS_PATH", "BENCHMARK_TASKS_PATH"):
        root = os.environ.get(env_key, "")
        if not root:
            continue
        base = Path(root)
        paths.append(base / "tasks" / f"{task_id}.md")
        paths.append(base / f"{task_id}.md")
    return paths


def load_task_markdown(task_id: str, *, required: bool = False) -> str:
    text = ""
    if _provider is not None:
        text = _provider.load_task_markdown(task_id)
    if not text:
        for path in _generic_task_paths(task_id):
            if path.exists():
                text = path.read_text(encoding="utf-8", errors="replace")
                break
    if required and not text.strip():
        raise TaskContextNotFoundError(
            f"Task markdown not found for {task_id!r}. "
            "Register a TaskContextProvider or set TASKS_PATH / BENCHMARK_TASKS_PATH."
        )
    return text


def load_task_context_for_inference(task_id: str) -> str:
    return truncate_task_markdown_for_inference(load_task_markdown(task_id, required=True))
