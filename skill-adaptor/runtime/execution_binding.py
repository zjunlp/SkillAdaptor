"""
Harness execution binding — EvoSkill-style separation of evolution core vs agent-facing inject.

Maps evolved skills + task briefs → skill markdown + optional user-message prefix env vars.
Benchmark adapters (PinchBench, claw-eval) read the env at agent launch time.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Mapping, Optional

# Env var read by PinchBench/claw-eval OpenClaw runners (lib_agent._effective_task_prompt).
PROMPT_PREFIX_ENV = 'PINCHBENCH_PROMPT_PREFIX'


def read_task_markdown(tasks_dir: Path | str, task_id: str) -> str:
    root = Path(tasks_dir)
    path = root / f'{task_id}.md'
    if path.exists():
        return path.read_text(encoding='utf-8')
    return ''


def shell_prompt_prefix_for_task(
    *,
    skill_body: str = '',
    task_md: str = '',
    allow_task_derivation: bool = False,
) -> str:
    """
    Build user-message prefix for shell command.txt tasks.

    allow_task_derivation=False (default): prefix only when skill body encodes a command
    (Validator A/B measures skill content, not task prompt alone).
    allow_task_derivation=True: also derive from task markdown (smoke / cold-start).
    """
    from core.skill_body_utils import (
        build_shell_prompt_prefix,
        extract_immediate_shell_action,
        resolve_immediate_shell_action,
        task_mentions_command_deliverable,
    )

    if task_md and not task_mentions_command_deliverable(task_md):
        return ''
    action = extract_immediate_shell_action(skill_body or '')
    if not action and allow_task_derivation and task_md:
        action = resolve_immediate_shell_action('', task_md)
    return build_shell_prompt_prefix(action)


def build_prompt_prefix_map(
    task_ids: list[str],
    *,
    tasks_dir: Path | str,
    task_to_skill_body: Mapping[str, str],
    allow_task_derivation: bool = False,
) -> Dict[str, str]:
    """Per-task prompt prefixes for executor harness (empty when not applicable)."""
    root = Path(tasks_dir)
    out: Dict[str, str] = {}
    for task_id in task_ids:
        task_md = read_task_markdown(root, task_id)
        prefix = shell_prompt_prefix_for_task(
            skill_body=task_to_skill_body.get(task_id, ''),
            task_md=task_md,
            allow_task_derivation=allow_task_derivation,
        )
        if prefix:
            out[task_id] = prefix
    return out


def apply_prompt_prefix(env: Dict[str, str], task_id: str, prefixes: Mapping[str, str]) -> Dict[str, str]:
    """Return env copy with PROMPT_PREFIX_ENV set or cleared for this task."""
    merged = dict(env)
    prefix = (prefixes.get(task_id) or '').strip()
    if prefix:
        merged[PROMPT_PREFIX_ENV] = prefix
    else:
        merged.pop(PROMPT_PREFIX_ENV, None)
    return merged


def inject_root_for_run(*, workspace: Path, benchmark_root: Optional[Path] = None) -> Path:
    """Where harness writes SKILL.md — workspace for generic plugin, benchmark dir for PinchBench."""
    if benchmark_root is not None and Path(benchmark_root).exists():
        return Path(benchmark_root)
    return Path(workspace)
