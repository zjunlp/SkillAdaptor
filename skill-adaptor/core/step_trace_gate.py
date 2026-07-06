from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence

from adapters.errors import TaskExecutionError

_PLACEHOLDER_ACTIONS = frozenset({'', '(no action)', '(end)', '(no transcript captured)'})

_TOOL_ACTION_RE = re.compile(r'^[a-zA-Z_][\w.-]*\s*\(', re.ASCII)


def is_placeholder_action(action: str) -> bool:
    return (action or '').strip().lower() in _PLACEHOLDER_ACTIONS


def is_tool_action(action: str) -> bool:
    text = (action or '').strip()
    if not text or is_placeholder_action(text):
        return False
    if text == '(assistant response)':
        return False
    return bool(_TOOL_ACTION_RE.match(text))


def count_tool_actions(steps: Sequence[Dict[str, Any]]) -> int:
    return sum(1 for s in steps if is_tool_action(str(s.get('action', ''))))


def count_actionable_steps(steps: Sequence[Dict[str, Any]]) -> int:
    return sum(
        1
        for s in steps
        if not is_placeholder_action(str(s.get('action', ''))) or str(s.get('observation', '')).strip()
    )


def require_actionable_trace(
    steps: Sequence[Dict[str, Any]],
    *,
    task_id: str,
    require_tool: bool = True,
) -> None:
    if count_actionable_steps(steps) == 0:
        raise TaskExecutionError(
            f'No step-level trajectory for {task_id}. Agent run produced zero actionable steps.'
        )
    if require_tool and count_tool_actions(steps) == 0:
        raise TaskExecutionError(
            f'No tool-level actions in trajectory for {task_id}. '
            'Runs must include at least one tool call step (not text-only).'
        )
