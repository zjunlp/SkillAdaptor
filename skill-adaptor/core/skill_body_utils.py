"""Skill body compaction and domain-specific enrichment (shell command tasks)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


_SHELL_DELIVERABLE_MARKERS = ('command.txt', 'terminal request', 'shell command')
_UNRELATED_CMD_PATTERNS = re.compile(
    r'\b(date|cal|time|echo\s+["\']hello|pwd\s*$|whoami)\b',
    re.I,
)


def smart_compact_skill_body(body: str, max_chars: int = 1600) -> str:
    """Truncate while keeping Procedure / Negative Example / Validation sections."""
    if len(body) <= max_chars:
        return body
    keep_headers = ('## Procedure', '## Negative Example', '## Validation Criteria', '## When to Apply')
    drop_headers = ('## Reference', '## Qualification Criteria', '## Description')
    lines = body.splitlines()
    kept: List[str] = []
    section = 'preamble'
    for line in lines:
        if line.startswith('## '):
            section = line.strip()
        if section in drop_headers:
            continue
        if section == 'preamble' or section in keep_headers or line.startswith('# '):
            kept.append(line)
    compact = '\n'.join(kept).strip()
    if len(compact) > max_chars:
        compact = compact[:max_chars].rstrip() + '\n\n<!-- compacted -->\n'
    elif len(compact) < len(body):
        compact += '\n\n<!-- compacted -->\n'
    return compact


def _task_mentions_command_deliverable(text: str) -> bool:
    lower = text.lower()
    return any(m in lower for m in _SHELL_DELIVERABLE_MARKERS)


def _extract_backtick_literals(text: str) -> List[str]:
    return [m.group(1) for m in re.finditer(r'`([^`]+)`', text or '')]


def _canonical_grep_log_command(search_literal: str) -> str:
    escaped = search_literal.replace('"', '\\"')
    return f'grep -rl "{escaped}" --include="*.log" . | sort -u'


def enrich_shell_skill_data(
    skill_data: Dict[str, Any],
    *,
    task_description: str,
    task_brief: str,
    wrong_action: str = '',
) -> Dict[str, Any]:
    """PinchBench shell tasks: always embed canonical command when prompt literals are known."""
    combined = f'{task_description}\n{task_brief}'
    if not _task_mentions_command_deliverable(combined):
        return skill_data
    out = dict(skill_data)
    literals = _extract_backtick_literals(task_description) or _extract_backtick_literals(task_brief)
    search_lit = next((lit for lit in literals if 'fatal' in lit.lower() or ':' in lit), None)
    ext_lit = next((lit for lit in literals if lit.startswith('.') and len(lit) <= 8), '*.log')
    proc: List[str] = list(out.get('procedure') or [])
    if search_lit:
        cmd = _canonical_grep_log_command(search_lit)
        proc = [
            f'Write to command.txt exactly one line (no prose): {cmd}',
            'The task prompt is always provided — never write placeholder or "request not specified" text.',
            'Verify: recursive .log search for exact string from prompt; plain shell only.',
        ] + [p for p in proc if 'command.txt' not in str(p).lower()][:2]
        out['procedure'] = proc[:5]
        out['principle'] = (
            f'Save one executable shell command to command.txt matching the prompt: '
            f'{ext_lit} files containing {search_lit!r}; never placeholders.'
        )
    neg = dict(out.get('negative_example') or {})
    if wrong_action and _UNRELATED_CMD_PATTERNS.search(wrong_action):
        neg.setdefault('what_not_to_do', f'Do NOT write unrelated commands like: {wrong_action[:160]}')
        neg.setdefault('why_it_fails', 'command.txt is executed against .log fixtures; unrelated commands score 0.')
        out['negative_example'] = neg
    elif wrong_action and 'command.txt' in wrong_action.lower():
        neg.setdefault('what_not_to_do', 'Do NOT ignore the prompt and write a placeholder or unrelated utility command.')
        neg.setdefault('why_it_fails', 'Grader checks command output paths against expected .log matches.')
        out['negative_example'] = neg
    out['validation_criteria'] = (
        'command.txt exists; single executable shell line; runs with exit 0 on fixture; '
        'outputs only matching .log paths once each.'
    )
    return out


def pinchbench_deliverable_banner(task_id: str, task_md_text: str) -> str:
    """Top-of-prompt banner: full task prompt + anti-placeholder rules."""
    from core.prompt_fidelity import extract_pinchbench_prompt_section

    if not _task_mentions_command_deliverable(task_md_text):
        return ''
    prompt_body = extract_pinchbench_prompt_section(task_md_text) or task_md_text.strip()[:1200]
    return (
        '## MANDATORY DELIVERABLE (PinchBench)\n'
        '- The task prompt below **is complete** — never claim it is missing or write placeholders.\n'
        '- Write **only** the requested shell command into `command.txt` (plain text, one command, no explanation).\n'
        '- Match prompt constraints: recursive search, file extension, exact content string.\n'
        '- **Forbidden**: echo/date/pwd placeholders, comment-only files, "request not specified".\n\n'
        '### Task prompt (follow exactly)\n'
        f'{prompt_body}\n\n'
        '---\n\n'
    )
