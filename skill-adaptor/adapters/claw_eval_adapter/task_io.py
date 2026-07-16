"""Shared Claw-Eval task.yaml I/O — prompt, category, and markdown for Localizer."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def _load_yaml_mapping(text: str) -> Optional[Dict[str, Any]]:
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _prompt_from_mapping(data: Dict[str, Any]) -> str:
    prompt = data.get('prompt')
    if isinstance(prompt, str) and prompt.strip():
        return prompt.strip()
    if isinstance(prompt, dict):
        for key in ('text', 'content', 'value', 'message'):
            val = prompt.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    description = data.get('description')
    if isinstance(description, str) and description.strip():
        return description.strip()
    if isinstance(description, dict):
        for key in ('text', 'content', 'value'):
            val = description.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return ''


def _prompt_from_raw_yaml(text: str) -> str:
    """Fallback parser for nested ``prompt: / text: |`` without PyYAML."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith('prompt:') or stripped.startswith('description:'):
            inline = stripped.split(':', 1)[1].strip().strip('"').strip("'")
            if inline and inline not in ('|', '>', '|-', '>-', 'text'):
                return inline
            base_indent = len(lines[i]) - len(lines[i].lstrip())
            j = i + 1
            while j < len(lines):
                raw = lines[j]
                if not raw.strip() or raw.strip().startswith('#'):
                    j += 1
                    continue
                indent = len(raw) - len(raw.lstrip())
                if indent <= base_indent and raw.lstrip():
                    break
                child = raw.strip()
                if child.startswith('text:') or child.startswith('content:'):
                    rest = child.split(':', 1)[1].strip()
                    if rest in ('|', '>', '|-', '>-', ''):
                        block: list[str] = []
                        k = j + 1
                        while k < len(lines):
                            blk = lines[k]
                            if not blk.strip():
                                block.append('')
                                k += 1
                                continue
                            blk_indent = len(blk) - len(blk.lstrip())
                            if blk_indent <= indent:
                                break
                            block.append(blk[indent + 2 :] if blk_indent >= indent + 2 else blk.lstrip())
                            k += 1
                        joined = '\n'.join(block).strip()
                        if joined:
                            return joined
                    else:
                        return rest.strip('"').strip("'")
                j += 1
        i += 1
    return ''


def read_task_yaml(tasks_dir: Path | str, task_id: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """Return (parsed mapping or None, raw text). Empty text if missing."""
    path = Path(tasks_dir) / task_id / 'task.yaml'
    if not path.exists():
        return None, ''
    text = path.read_text(encoding='utf-8', errors='replace')
    return _load_yaml_mapping(text), text


def read_claw_eval_prompt(tasks_dir: Path | str, task_id: str) -> str:
    """Extract agent-facing prompt text from nested or flat task.yaml."""
    data, text = read_task_yaml(tasks_dir, task_id)
    if data:
        extracted = _prompt_from_mapping(data)
        if extracted:
            return extracted
    if text:
        extracted = _prompt_from_raw_yaml(text)
        if extracted:
            return extracted
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith('prompt:') or stripped.startswith('description:'):
                inline = stripped.split(':', 1)[1].strip().strip('"').strip("'")
                if inline and inline not in ('|', '>', '|-', '>-', 'text'):
                    return inline
    return ''


def read_claw_eval_category(tasks_dir: Path | str, task_id: str) -> str:
    data, text = read_task_yaml(tasks_dir, task_id)
    if data:
        cat = data.get('category')
        if isinstance(cat, str) and cat.strip():
            return cat.strip().lower()
    if text:
        for line in text.splitlines():
            m = re.match(r'^category:\s*(\S+)', line.strip(), re.I)
            if m:
                return m.group(1).lower()
    return ''


def task_yaml_as_markdown(tasks_dir: Path | str, task_id: str) -> str:
    """Render task.yaml into markdown for Localizer / Generator task context.

    Uses prompt + rubric/category fields only (never reference_solution as golden answers).
    """
    data, text = read_task_yaml(tasks_dir, task_id)
    prompt = read_claw_eval_prompt(tasks_dir, task_id)
    if not prompt and not data:
        return ''
    lines = [f'# {task_id}', '']
    if data:
        name = data.get('task_name') or data.get('name')
        if name:
            lines.append(f'**Task name:** {name}')
        cat = data.get('category')
        if cat:
            lines.append(f'category: {cat}')
        tags = data.get('tags')
        if tags:
            lines.append(f'tags: {tags}')
        difficulty = data.get('difficulty')
        if difficulty:
            lines.append(f'difficulty: {difficulty}')
        lines.append('')
    lines.append('## Prompt')
    lines.append('')
    lines.append(prompt or task_id)
    lines.append('')
    if data:
        rubric = data.get('judge_rubric') or data.get('rubric')
        if isinstance(rubric, str) and rubric.strip():
            lines.append('## Grading Criteria')
            lines.append('')
            lines.append(rubric.strip())
            lines.append('')
        dims = data.get('primary_dimensions')
        if dims:
            lines.append('## Primary Dimensions')
            lines.append('')
            lines.append(', '.join(str(d) for d in dims))
            lines.append('')
        scoring = data.get('scoring_components')
        if isinstance(scoring, list) and scoring:
            lines.append('## Automated Checks (shape only)')
            lines.append('')
            for comp in scoring[:12]:
                if isinstance(comp, dict):
                    lines.append(f"- {comp.get('name', 'check')} weight={comp.get('weight', '')}")
            lines.append('')
    return '\n'.join(lines).strip() + '\n'
