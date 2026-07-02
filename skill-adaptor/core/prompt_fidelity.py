"""Detect placeholder deliverables and prompt drift in PinchBench trajectories."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.types import Trajectory

_PLACEHOLDER_PHRASES = (
    'not provided',
    'not specified',
    'placeholder',
    'waiting for',
    'please resend',
    'please specify',
    'terminal request not',
    'no terminal request',
    'request not given',
    'request is not specified',
    'actual request is not',
    'since the actual request',
    'resend your actual',
    'to be determined',
    'fill in later',
    'todo:',
    'tbd',
)

_UNRELATED_SHELL_CMD = re.compile(
    r'\b(date\s+-d|cal\s|^\s*echo\s+["\']?(?:hello|terminal request|placeholder|not provided))',
    re.I | re.M,
)

_WRITE_CONTENT_RE = re.compile(
    r'write\s*\(\s*(\{.*\})\s*\)',
    re.I | re.S,
)


@dataclass
class FidelityViolation:
    code: str
    message: str


@dataclass
class FidelityReport:
    ok: bool
    violations: List[FidelityViolation] = field(default_factory=list)

    def summary(self) -> str:
        if self.ok:
            return 'ok'
        return '; '.join(f'{v.code}: {v.message}' for v in self.violations)


def extract_pinchbench_prompt_section(task_md: str) -> str:
    if not task_md or '## Prompt' not in task_md:
        return ''
    section = task_md.split('## Prompt', 1)[1]
    for marker in ('## Expected', '## Grading', '## Automated', '## Additional'):
        if marker in section:
            section = section.split(marker, 1)[0]
    return section.strip()


def extract_prompt_anchors(prompt: str) -> List[str]:
    anchors: List[str] = []
    for lit in re.findall(r'`([^`]+)`', prompt or ''):
        cleaned = lit.strip()
        if len(cleaned) >= 2:
            anchors.append(cleaned.lower())
    lower = (prompt or '').lower()
    if 'fatal:' in lower and 'fatal:' not in anchors:
        anchors.append('fatal:')
    return anchors


def scan_text_for_placeholders(text: str) -> List[str]:
    if not text:
        return []
    lower = text.lower()
    hits = [p for p in _PLACEHOLDER_PHRASES if p in lower]
    if re.search(r'^#\s*(?:waiting|placeholder|todo)', lower, re.M):
        hits.append('comment_only_command')
    if 'command.txt' in lower and _UNRELATED_SHELL_CMD.search(text):
        hits.append('unrelated_shell_command')
    return hits


def extract_write_payload(action: str) -> Optional[Dict[str, Any]]:
    if not action or 'write(' not in action.lower():
        return None
    m = _WRITE_CONTENT_RE.search(action)
    if not m:
        return None
    raw = m.group(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _combined_step_text(trajectory: 'Trajectory') -> str:
    parts: List[str] = []
    for step in trajectory.steps:
        parts.append(step.observation or '')
        parts.append(step.action or '')
    return '\n'.join(parts)


def check_trajectory_fidelity(trajectory: 'Trajectory') -> FidelityReport:
    violations: List[FidelityViolation] = []
    expected = (trajectory.task_description or '').strip()
    if len(expected) < 20:
        violations.append(FidelityViolation('missing_prompt', 'task_description missing or too short for fidelity check'))

    combined = _combined_step_text(trajectory)
    placeholder_hits = scan_text_for_placeholders(combined)
    if placeholder_hits:
        violations.append(
            FidelityViolation('placeholder_deliverable', f'detected placeholder patterns: {sorted(set(placeholder_hits))}')
        )

    anchors = extract_prompt_anchors(expected)
    lower_combined = combined.lower()

    if anchors and any(
        p in placeholder_hits
        for p in ('not provided', 'not specified', 'terminal request not', 'no terminal request', 'request not given')
    ):
        violations.append(
            FidelityViolation(
                'prompt_ignored',
                f'agent claimed missing prompt but task specifies: {anchors[:4]}',
            )
        )

    if 'command.txt' in expected.lower():
        write_contents: List[str] = []
        for step in trajectory.steps:
            payload = extract_write_payload(step.action or '')
            if not isinstance(payload, dict):
                continue
            path = str(payload.get('path', '')).lower()
            if 'command.txt' in path:
                write_contents.append(str(payload.get('content', '')))
        for content in write_contents:
            ph = scan_text_for_placeholders(content)
            if ph:
                violations.append(
                    FidelityViolation('command_txt_placeholder', f'command.txt content has placeholder: {ph}')
                )
            if content.strip().startswith('#') and 'grep' not in content.lower() and 'find' not in content.lower():
                violations.append(
                    FidelityViolation('command_txt_comment_only', 'command.txt is comment-only, not an executable command')
                )
            if _UNRELATED_SHELL_CMD.search(content):
                violations.append(
                    FidelityViolation('command_txt_unrelated', 'command.txt contains unrelated utility command')
                )
        if anchors and write_contents:
            required = [a for a in anchors if a not in ('command.txt', '.log')]
            for content in write_contents:
                cl = content.lower()
                for req in required:
                    if req in ('fatal:',) and 'fatal' not in cl and 'grep' not in cl and 'find' not in cl:
                        violations.append(
                            FidelityViolation(
                                'command_txt_missing_requirement',
                                f'command.txt does not reflect prompt anchor {req!r}',
                            )
                        )
                        break

    if anchors and 'command.txt' not in expected.lower():
        missing = [a for a in anchors if a not in lower_combined]
        if len(missing) == len(anchors) and len(anchors) >= 2:
            violations.append(
                FidelityViolation('prompt_anchors_absent', f'no prompt anchors reflected in trajectory: {missing[:4]}')
            )

    # de-dupe by code
    seen: set[str] = set()
    unique: List[FidelityViolation] = []
    for v in violations:
        if v.code in seen:
            continue
        seen.add(v.code)
        unique.append(v)
    return FidelityReport(ok=not unique, violations=unique)


def exec_max_retries() -> int:
    import os
    raw = os.environ.get('SkillEvolve_EXEC_MAX_RETRIES', os.environ.get('SKILL_ADAPTOR_EXEC_MAX_RETRIES', '3'))
    try:
        return max(1, int(raw))
    except ValueError:
        return 3
