"""Skill body compaction and deliverable-aware enrichment (shell + artifact tasks)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from core.types import LocalizedFault, Trajectory

_SHELL_DELIVERABLE_MARKERS = ('command.txt', 'terminal request', 'shell command')
_ARTIFACT_EXTENSIONS = ('.sh', '.txt', '.md', '.json', '.py', '.yaml', '.yml')
_SAVE_TO_FILE = re.compile(
    r'\b(?:save|write|store|put|translate)[^.]{0,160}?`([^`]+\.(?:sh|txt|md|json|py|yaml|yml))`',
    re.I | re.S,
)
_UNRELATED_CMD_PATTERNS = re.compile(
    r'\b(date|cal|time|echo\s+["\']hello|pwd\s*$|whoami)\b',
    re.I,
)
_REMOTE_SCRIPT_MARKERS = ('remote set-url', 'backup-remote', 'git fetch', 'git pull', 'set-url origin')
_DIAGNOSTIC_GIT_MARKERS = ('git fsck', 'git reflog', 'git gc', '#!/bin/bash', 'lost-found')
_GOLDEN_GIT_CMD = re.compile(r"^(?:Step\s+\d+:\s*)?(?:Run\s+['\"])?git\s+", re.I)


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
        neg_marker = '## Negative Example'
        neg_idx = compact.find(neg_marker)
        if neg_idx > 0:
            tail = compact[neg_idx:]
            head_budget = max_chars - len(tail) - 24
            if head_budget > 180:
                compact = compact[:head_budget].rstrip() + '\n\n' + tail
            else:
                compact = compact[:max_chars].rstrip() + '\n\n<!-- compacted -->\n'
        else:
            compact = compact[:max_chars].rstrip() + '\n\n<!-- compacted -->\n'
    elif len(compact) < len(body):
        compact += '\n\n<!-- compacted -->\n'
    return compact


def _task_mentions_command_deliverable(text: str) -> bool:
    lower = text.lower()
    return any(m in lower for m in _SHELL_DELIVERABLE_MARKERS)


def task_mentions_command_deliverable(text: str) -> bool:
    """Public API: task brief mentions command.txt / shell deliverable."""
    return _task_mentions_command_deliverable(text)


def _extract_backtick_literals(text: str) -> List[str]:
    return [m.group(1) for m in re.finditer(r'`([^`]+)`', text or '')]


def extract_output_deliverables(text: str) -> List[str]:
    """Output filenames named in the task prompt (no answer leakage)."""
    if not text:
        return []
    found: List[str] = []
    for m in _SAVE_TO_FILE.finditer(text):
        found.append(m.group(1))
    lower = text.lower()
    for lit in _extract_backtick_literals(text):
        if not any(lit.endswith(ext) for ext in _ARTIFACT_EXTENSIONS):
            continue
        pos = lower.find(lit.lower())
        if pos < 0:
            continue
        window = lower[max(0, pos - 100): pos + len(lit) + 40]
        if any(k in window for k in ('save', 'write', 'to `', 'into `', 'file `', 'per line', 'commands to')):
            if lit not in found:
                found.append(lit)
    return list(dict.fromkeys(found))


def _canonical_grep_log_command(search_literal: str) -> str:
    escaped = search_literal.replace('"', '\\"')
    return f'grep -rl "{escaped}" --include="*.log" . | sort -u'


def derive_shell_command_from_task_md(task_md_text: str) -> str:
    """Build canonical bash one-liner from task prompt literals (no golden-path leak)."""
    if not task_md_text or not _task_mentions_command_deliverable(task_md_text):
        return ''
    from core.prompt_fidelity import extract_pinchbench_prompt_section

    prompt_body = extract_pinchbench_prompt_section(task_md_text) or task_md_text
    literals = _extract_backtick_literals(prompt_body)
    search_lit = next(
        (lit for lit in literals if 'fatal' in lit.lower() or (':' in lit and len(lit) <= 32)),
        None,
    )
    if search_lit and ('.log' in prompt_body.lower() or any('.log' in lit for lit in literals)):
        return _canonical_grep_log_command(search_lit)
    return ''


def build_shell_prompt_prefix(canonical_command: str) -> str:
    """Prepend to PinchBench user message so the agent sees binding before task.prompt."""
    cmd = (canonical_command or '').strip()
    if not cmd:
        return ''
    return (
        '[MANDATORY FIRST ACTION — Linux bash/sh only; never PowerShell]\n'
        'Your first tool call must use write path=`command.txt` (relative filename in the task workspace root, '
        'NOT an absolute path like C:\\\\...).\n'
        'File content must be **exactly** this one line (plain text, no markdown fence, no explanation):\n'
        f'{cmd}'
    )


def resolve_immediate_shell_action(skill_body: str, task_md_text: str = '') -> str:
    """Binding command for harness: skill body first, then task-prompt derivation."""
    action = extract_immediate_shell_action(skill_body)
    if action:
        return action
    return derive_shell_command_from_task_md(task_md_text)


def extract_immediate_shell_action(skill_body: str) -> str:
    """First executable command line from enrich_shell procedure (for agent injection)."""
    body = skill_body or ''
    for line in body.splitlines():
        lower = line.lower()
        if 'write to command.txt exactly one line' in lower and ':' in line:
            cmd = line.split(':', 1)[1].strip()
            if cmd and ('grep' in cmd.lower() or 'find' in cmd.lower()):
                return cmd
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith('```') and stripped.endswith('```') and len(stripped) > 6:
            inner = stripped.strip('`').strip()
            if inner and ('grep' in inner.lower() or 'find' in inner.lower()):
                return inner
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        lower = stripped.lower()
        if lower.startswith(('grep ', 'find ', 'rg ')):
            return stripped.lstrip('0123456789. ').strip()
        if '|' in stripped and 'grep' in lower:
            return stripped.lstrip('0123456789. ').strip()
        m = re.search(r'`(grep[^`]+|find[^`]+)`', stripped, re.I)
        if m:
            return m.group(1).strip()
    return ''


def extract_wrong_actions_from_rejections(rejection_summaries: list[str] | None) -> list[str]:
    """Pull trajectory-grounded wrong actions from rejection audit lines (contrastive input)."""
    if not rejection_summaries:
        return []
    import re
    found: list[str] = []
    for line in rejection_summaries:
        text = line or ''
        for marker in ('step1:', 'step2:', 'step3:', 'Wrong action at t*:', 'validation_after_reject:'):
            if marker in text:
                chunk = text.split(marker, 1)[-1].split(';', 1)[0].strip()
                if chunk and chunk not in found:
                    found.append(chunk[:240])
        m = re.search(r'Do NOT repeat this failed write pattern:\s*(.+?)(?:\*\*|$)', text)
        if m:
            snippet = m.group(1).strip()[:240]
            if snippet and snippet not in found:
                found.append(snippet)
    return found[:4]


def summarize_trajectory_actions(trajectory: Trajectory, *, max_steps: int = 3, action_chars: int = 72) -> str:
    """Short post-validation summary for rejection feedback (no answer leak)."""
    if not trajectory or not trajectory.steps:
        return ''
    tail = trajectory.steps[-max_steps:]
    parts = []
    for s in tail:
        act = (s.action or '').replace('\n', ' ').strip()[:action_chars]
        if act:
            parts.append(f'step{s.index + 1}:{act}')
    score = getattr(trajectory, 'total_reward', 0.0)
    ok = getattr(trajectory, 'success', False)
    prefix = f'score={score:.2f} success={ok}'
    return f'{prefix}; ' + '; '.join(parts) if parts else prefix


def format_trajectory_steps_for_analysis(
    trajectory: Trajectory,
    *,
    fault_step_index: int | None = None,
    max_steps: int = 24,
    action_chars: int = 220,
    obs_chars: int = 140,
    include_skills: bool = True,
) -> str:
    """
    Full step-level trajectory for Localizer / Linker / Reviser / Generator.
    EvoSkill-style trace review without leaking golden answers.
    """
    if not trajectory or not trajectory.steps:
        return '(empty trajectory)'
    steps = trajectory.steps
    if len(steps) > max_steps:
        head = steps[: max(2, max_steps // 4)]
        tail_budget = max_steps - len(head) - 1
        tail = steps[-tail_budget:] if tail_budget > 0 else []
        omitted = len(steps) - len(head) - len(tail)
        selected: list = list(head)
        if omitted > 0:
            selected.append(None)  # ellipsis marker
        selected.extend(tail)
    else:
        selected = list(steps)
        omitted = 0

    lines: list[str] = []
    for item in selected:
        if item is None:
            lines.append(f'  ... ({omitted} steps omitted) ...')
            continue
        s = item
        marker = ' << t*' if fault_step_index is not None and s.index == fault_step_index else ''
        act = (s.action or '').replace('\n', ' ').strip()[:action_chars]
        obs = (s.observation or '').replace('\n', ' ').strip()[:obs_chars]
        skill_part = ''
        if include_skills and getattr(s, 'skills_used', None):
            skill_part = f' | skills={s.skills_used}'
        lines.append(f'Step {s.index + 1}{marker}: action={act} | obs={obs}{skill_part}')
    return '\n'.join(lines)


def build_contrastive_failure_block(
    fault: 'LocalizedFault',
    trajectory: Trajectory,
    *,
    rejection_summaries: list[str] | None = None,
) -> str:
    """AutoRefine / EvoSkill Proposer-style contrast (trajectory-grounded, no golden answers)."""
    steps_block = format_trajectory_steps_for_analysis(
        trajectory, fault_step_index=fault.step_index, max_steps=20,
    )
    prior_wrong = (fault.wrong_action or '').replace('\n', ' ')[:240]
    reject_lines = ''
    if rejection_summaries:
        reject_lines = '\n'.join(f'- {ln}' for ln in rejection_summaries[:4])
    return f"""### Step-level failure contrast (read full trace — do NOT invent new scenarios)
```
{steps_block}
```

- Fault step t*={fault.step_index + 1} | type={fault.fault_type.value}
- Wrong action at t*: {prior_wrong}
- Rubric gap (shape only): {fault.rubric_gap or 'deliverable/rubric mismatch'}
- Improvement direction: {fault.improvement_principle[:320]}
{f'### Prior rejected proposals{chr(10)}{reject_lines}' if reject_lines else ''}
"""


def _strip_leaked_git_commands(proc: List[str]) -> List[str]:
    """Remove LLM procedure lines that embed executable git commands (golden leak)."""
    kept: List[str] = []
    for line in proc:
        text = str(line).strip()
        if _GOLDEN_GIT_CMD.search(text):
            continue
        kept.append(line)
    return kept


def artifact_negative_from_wrong_action(wrong_action: str, deliverable: str) -> Dict[str, str]:
    """Trajectory-grounded negative example (no golden answers)."""
    wa = (wrong_action or '').strip()
    if not wa or not deliverable:
        return {}
    lower = wa.lower()
    if any(x in lower for x in _REMOTE_SCRIPT_MARKERS):
        return {
            'what_not_to_do': (
                f'Do NOT write unrelated git remote/backup/fetch scripts into `{deliverable}` '
                f'when the prompt describes local branch/commit moves.'
            ),
            'why_it_fails': 'Grader executes lines against a controlled fixture; wrong scenario scores 0.',
        }
    if any(x in lower for x in _DIAGNOSTIC_GIT_MARKERS):
        return {
            'what_not_to_do': (
                f'Do NOT write diagnostic boilerplate (fsck/reflog/gc/comments) into `{deliverable}` '
                f'when the prompt asks for branch/commit move git commands only.'
            ),
            'why_it_fails': 'Grader expects executable branch/reset commands from the prompt scenario, not repo repair scripts.',
        }
    if deliverable.lower() in lower or f'"{deliverable}"' in wa or f"'{deliverable}'" in wa:
        snippet = wa.replace('\n', ' ')[:180]
        return {
            'what_not_to_do': f'Do NOT repeat this failed write pattern: {snippet}',
            'why_it_fails': (
                f'`{deliverable}` must implement the prompt scenario, not an invented recovery flow.'
            ),
        }
    return {}


def enrich_shell_skill_data(
    skill_data: Dict[str, Any],
    *,
    task_description: str,
    task_brief: str,
    wrong_action: str = '',
) -> Dict[str, Any]:
    """PinchBench shell tasks: embed canonical command when prompt literals are known."""
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
            f'Write to command.txt exactly one line (no prose, no trailing newline): {cmd}',
            'The task prompt is always provided — never write placeholder or "request not specified" text.',
            'Verify: recursive .log search for exact string from prompt; plain shell only.',
        ] + [p for p in proc if 'command.txt' not in str(p).lower()][:2]
        out['procedure'] = proc[:5]
        out['principle'] = (
            f'Save one executable shell command to command.txt matching the prompt: '
            f'{ext_lit} files containing {search_lit!r}; never placeholders.'
        )
    neg = dict(out.get('negative_example') or {})
    traj_neg = artifact_negative_from_wrong_action(wrong_action, 'command.txt')
    if traj_neg:
        neg.update(traj_neg)
    elif wrong_action and _UNRELATED_CMD_PATTERNS.search(wrong_action):
        neg.setdefault('what_not_to_do', f'Do NOT write unrelated commands like: {wrong_action[:160]}')
        neg.setdefault('why_it_fails', 'command.txt is executed against .log fixtures; unrelated commands score 0.')
        out['negative_example'] = neg
    elif wrong_action and 'command.txt' in wrong_action.lower():
        neg.setdefault('what_not_to_do', 'Do NOT ignore the prompt and write a placeholder or unrelated utility command.')
        neg.setdefault('why_it_fails', 'Grader checks command output paths against expected .log matches.')
    if neg:
        out['negative_example'] = neg
    out['validation_criteria'] = (
        'command.txt exists; single executable shell line; runs with exit 0 on fixture; '
        'outputs only matching .log paths once each.'
    )
    return out


def enrich_artifact_skill_data(
    skill_data: Dict[str, Any],
    *,
    task_description: str,
    task_brief: str,
    wrong_action: str = '',
    deliverable_targets: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Coding/devops artifact tasks: anchor procedure to prompt-named deliverables."""
    combined = f'{task_description}\n{task_brief}'
    if _task_mentions_command_deliverable(combined):
        return skill_data
    targets = list(deliverable_targets or extract_output_deliverables(combined))
    if not targets:
        return skill_data
    primary = targets[0]
    out = dict(skill_data)
    proc: List[str] = list(out.get('procedure') or [])
    git_script = primary.endswith('.sh') and ('git' in combined.lower() or 'branch' in combined.lower())
    lead = [
        f'First: write ONLY to `{primary}` exactly as the prompt specifies (no prose in the file).',
        'Copy branch names, commit counts, and move constraints verbatim from the task prompt.',
        'Do NOT invent a different recovery scenario (remote backup, fetch-all, unrelated repos).',
    ]
    if git_script:
        lead.append('Each non-empty line must be a `git ...` command; one command per line when the prompt requires it.')
    out['procedure'] = _strip_leaked_git_commands(lead + [p for p in proc if primary.lower() not in str(p).lower()][:3])
    out['procedure'] = out['procedure'][:5]
    out['principle'] = (
        f'Translate the prompt into `{primary}` using prompt-stated names and counts; '
        f'never substitute unrelated git/network recovery scripts.'
    )
    neg = dict(out.get('negative_example') or {})
    traj_neg = artifact_negative_from_wrong_action(wrong_action, primary)
    if traj_neg:
        neg.update(traj_neg)
        out['negative_example'] = neg
    out['validation_criteria'] = (
        f'`{primary}` exists; format matches prompt (shape-only); '
        'no placeholder prose; lines are executable in the task workspace.'
    )
    return out


def refine_localized_fault(fault: LocalizedFault, trajectory: Trajectory, task_markdown: str) -> LocalizedFault:
    """Strengthen localization with deliverable + trajectory grounding (no answer leak)."""
    combined = f'{task_markdown}\n{trajectory.task_description or ""}'
    deliverables = extract_output_deliverables(combined)
    if not fault.deliverable_targets:
        fault.deliverable_targets = deliverables
    deliverables = fault.deliverable_targets
    if deliverables:
        primary = deliverables[0]
        parts = [f'Step {fault.step_index + 1}: deliverable `{primary}` must match the prompt scenario.']
        wa = (fault.wrong_action or '').strip()
        llm_note = (fault.wrong_artifact_note or '').strip()
        if llm_note:
            parts.append(llm_note)
        elif any(x in wa.lower() for x in _REMOTE_SCRIPT_MARKERS):
            parts.append('Observed unrelated remote/backup/fetch scripting.')
        elif any(x in wa.lower() for x in _DIAGNOSTIC_GIT_MARKERS):
            parts.append('Observed fsck/reflog/gc diagnostic scripting instead of branch moves.')
        elif wa:
            parts.append(f'Wrong action at t*: {wa[:140]}')
        fault.wrong_artifact_note = ' '.join(parts)
        imp = (fault.improvement_principle or '').strip()
        rubric = (fault.rubric_gap or 'commands match prompt format').strip()
        if primary not in imp:
            fault.improvement_principle = (
                f'{imp.rstrip(".")}. '
                f'Write prompt-faithful content to `{primary}` ({rubric}); '
                f'at t* refer to wrong action pattern in trajectory — no golden commands.'
            ).strip()
        wa = (fault.wrong_action or '').strip()
        if wa and wa[:80] not in fault.improvement_principle:
            snippet = wa.replace('\n', ' ')[:100]
            fault.improvement_principle = (
                f'{fault.improvement_principle.rstrip(".")}. '
                f'At t* agent action was: {snippet}.'
            ).strip()
    if not fault.rubric_gap:
        fault.rubric_gap = 'Deliverable file exists; commands match prompt format; scenario matches instruction shapes.'
    return fault


def coerce_cold_start_fault(
    fault: 'LocalizedFault',
    trajectory: 'Trajectory',
) -> 'LocalizedFault':
    """When no skill covered the gap, treat deliverable/rubric mistakes as skill_missing."""
    from core.types import FaultType

    if fault.fault_type != FaultType.REASONING_WRONG:
        return fault
    if fault.skills_at_fault:
        return fault
    task_text = trajectory.task_description or ''
    has_deliverable = bool(fault.deliverable_targets) or _task_mentions_command_deliverable(task_text)
    action = (fault.wrong_action or '').lower()
    wrote_artifact = 'command.txt' in action or 'write(' in action or any(
        ext in action for ext in _ARTIFACT_EXTENSIONS
    )
    if has_deliverable or wrote_artifact:
        fault.fault_type = FaultType.SKILL_MISSING
    return fault


def coerce_degraded_bank_fault(
    fault: 'LocalizedFault',
    trajectory: 'Trajectory',
    skill_bank: dict[str, 'Skill'],
) -> 'LocalizedFault':
    """When a seeded/degraded skill exists for the task, route to Reviser (skill_wrong), not Generator."""
    from core.types import FaultType, Skill

    if not skill_bank:
        return fault
    task_id = fault.task_id
    related: list[Skill] = [
        s for s in skill_bank.values()
        if getattr(s, 'created_from', None) == task_id
        or (getattr(s, 'metadata', None) or {}).get('scope_task') == task_id
    ]
    if not related and len(skill_bank) <= 8:
        related = list(skill_bank.values())
    if not related:
        return fault

    task_text = f'{trajectory.task_description or ""}'
    deliverable_mismatch = bool(fault.deliverable_targets) or _task_mentions_command_deliverable(task_text)
    if not deliverable_mismatch:
        return fault

    if fault.fault_type == FaultType.SKILL_MISSING:
        fault.fault_type = FaultType.SKILL_WRONG
        if not fault.skills_at_fault:
            fault.skills_at_fault = [related[0].id]
        imp = (fault.improvement_principle or '').strip()
        if 'revise' not in imp.lower() and 'misleading' not in imp.lower():
            fault.improvement_principle = (
                f'{imp.rstrip(".") + "." if imp else ""} '
                'An existing skill was active but incomplete or misleading for the deliverable; '
                'revise procedure and validation (shape/rubric only — no answer literals).'
            ).strip()
        return fault

    if fault.fault_type == FaultType.REASONING_WRONG and fault.skills_at_fault:
        fault.fault_type = FaultType.SKILL_WRONG
    return fault


def pinchbench_deliverable_banner(task_id: str, task_md_text: str) -> str:
    """Top-of-injection banner: full prompt + deliverable rules (shell or named artifact)."""
    from core.prompt_fidelity import extract_pinchbench_prompt_section

    prompt_body = extract_pinchbench_prompt_section(task_md_text) or task_md_text.strip()[:1200]
    once_hint = ''
    if re.search(r'\b(?:once each|each .+ once|print each)\b', prompt_body, re.I):
        once_hint = '- When the prompt requires each matching path **once**, pipe the command through `| sort -u`.\n'
    if _task_mentions_command_deliverable(task_md_text):
        return (
            '## MANDATORY DELIVERABLE (PinchBench)\n'
            '- The task prompt below **is complete** — never claim it is missing or write placeholders.\n'
            '- Write **only** the requested shell command into `command.txt` (plain text, one command, no explanation).\n'
            '- Match prompt constraints: recursive search, file extension, exact content string.\n'
            f'{once_hint}'
            '- **Forbidden**: echo/date/pwd placeholders, comment-only files, "request not specified".\n\n'
            '### Task prompt (follow exactly)\n'
            f'{prompt_body}\n\n'
            '---\n\n'
        )
    deliverables = extract_output_deliverables(task_md_text)
    if not deliverables:
        return ''
    primary = deliverables[0]
    extra = ''
    if primary.endswith('.sh') and 'git' in task_md_text.lower():
        extra = '- Each line in the script file must be a `git ...` command when the prompt asks for git commands.\n'
    return (
        '## MANDATORY DELIVERABLE (PinchBench)\n'
        '- The task prompt below **is complete** — never claim it is missing.\n'
        f'- Write **only** into `{primary}` as specified (format from prompt; no alternate filenames).\n'
        '- Use branch names, commit counts, and constraints **from the prompt** — do not invent a different scenario.\n'
        f'{extra}'
        '- **Forbidden**: unrelated remote/backup scripts, fsck/reflog/gc diagnostic scripts, comment-only files, placeholder prose.\n\n'
        '### Task prompt (follow exactly)\n'
        f'{prompt_body}\n\n'
        '---\n\n'
    )
