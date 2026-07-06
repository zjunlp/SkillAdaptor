from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from core.types import Step


def extract_prompt_section(task_md: str) -> str:
    text = task_md or ''
    if '## Prompt' in text:
        section = text.split('## Prompt', 1)[1]
        for marker in ('## Expected', '## Grading', '## Automated', '## Additional'):
            if marker in section:
                section = section.split(marker, 1)[0]
        body = section.strip()
        if body:
            return body
    stripped = text.strip()
    if stripped.startswith('---'):
        parts = stripped.split('---', 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return stripped


def _deliverable_paths(task_md: str) -> List[str]:
    paths: List[str] = []
    for lit in re.findall(r'`([^`]+)`', task_md or ''):
        cleaned = lit.strip()
        if '/' in cleaned or '.' in cleaned:
            paths.append(cleaned)
    for match in re.finditer(r'(?:write|create|save|output)\s+(?:to\s+)?[`"]?([\w./-]+\.\w+)', task_md or '', re.I):
        paths.append(match.group(1))
    seen: set[str] = set()
    out: List[str] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def grade_workspace_task(workspace: Path, task_id: str, task_md: str, steps: List[Step]) -> float:
    if steps and steps[-1].reward > 0:
        return float(steps[-1].reward)
    deliverables = _deliverable_paths(task_md)
    if deliverables:
        hits = sum(1 for rel in deliverables if (workspace / rel).exists())
        if hits == len(deliverables):
            return 1.0
        if hits > 0:
            return hits / len(deliverables)
    if steps and any(s.done and s.reward >= 1.0 for s in steps):
        return 1.0
    return 0.0
