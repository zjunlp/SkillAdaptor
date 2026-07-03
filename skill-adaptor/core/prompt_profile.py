"""Unified prompt profile blocks shared by core components."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class PromptProfile:
    model_name: str
    template: str = 'enhanced'
    env_hints: Dict[str, Any] = field(default_factory=dict)

    def constraints_block(self, stage: str) -> str:
        stage = stage.lower()
        sections = [self.shared_constraints_block()]
        constraints = ['## STAGE CONSTRAINTS', '- Output must be deterministic and grounded in trajectory context.']
        if stage in {'localizer', 'linker'}:
            constraints.append('- Return structured analysis; no action suggestions.')
            constraints.append('- Watch for repetitive action patterns (loops) and flag them.')
            constraints.append('- Never propose runtime package installation or environment creation.')
        elif stage in {'generator', 'reviser'}:
            constraints.append('- Produce principle-based guidance with verification criteria.')
            constraints.append('- Generated skills should prevent infinite loops and repetitive ineffective actions.')
            constraints.append('- DO NOT suggest installing packages or creating virtual environments in runtime.')
        if self.template.lower() == 'concise':
            constraints.append('- Enforce hard stop after 3 ineffective retries.')
        constraints.append('- If you detect repeated actions without progress, warn against looping behavior.')
        return '\n'.join(sections + constraints)

    def shared_constraints_block(self) -> str:
        return '## SHARED CONSTRAINTS\n- Do not fabricate facts; use only trajectory evidence.\n- If repeated actions show no progress, explicitly flag loop risk.\n- Never propose runtime package installation or environment creation.\n- Flag same-tool same-parameter calls repeated >= 3 times without progress.\n- Reject destructive operations targeting system-critical paths; stay workspace-scoped.'

    def model_specific_block(self, stage: str) -> str:
        model = self.model_name.lower()
        stage_l = stage.lower()
        deliverable_hint = ''
        if stage_l in {'generator', 'reviser'}:
            deliverable_hint = (
                '\n- When the task prompt names an output file (`command.txt`, `recovery.sh`, etc.), '
                'the procedure MUST name that file and forbid alternate scenarios.'
            )
        if 'kimi' in model:
            return (
                '## MODEL PROFILE (Kimi)\n'
                '- Use explicit numbered steps with clear termination\n'
                '- Avoid open-ended prompts; provide bounded alternatives\n'
                '- Structure output with clear section delimiters'
                f'{deliverable_hint}'
            )
        if 'glm' in model:
            return (
                '## MODEL PROFILE (GLM)\n'
                '- Lead with schema definition, then examples\n'
                '- Emphasize validation before final output\n'
                '- Use compact, information-dense phrasing'
                f'{deliverable_hint}'
            )
        return f'## MODEL PROFILE\n- Use conservative, verifiable instructions.{deliverable_hint}'

    def format_trajectory(self, steps: List[Dict[str, Any]], fault_idx: Optional[int]=None, window: int=3) -> str:
        if not steps:
            return 'No trajectory steps.'
        lines = ['### Trajectory']
        start = max(0, fault_idx - window) if fault_idx is not None else 0
        end = min(len(steps), fault_idx + window + 1 if fault_idx else len(steps))
        for i in range(start, end):
            step = steps[i]
            marker = ' >>> FAULT' if i == fault_idx else ''
            action = str(step.get('action', 'N/A'))[:80]
            obs = str(step.get('observation', ''))[:100].replace('\n', ' ')
            lines.append(f'\n[{i}]{marker}\n  Action: {action}\n  Obs: {obs}')
        return '\n'.join(lines)

    def render(self, stage: str, **context) -> str:
        sections = [self.constraints_block(stage), self.model_specific_block(stage)]
        if self.env_hints.get('env_type'):
            sections.append(f"## ENV CONTEXT\n- Type: {self.env_hints['env_type']}")
        if context.get('trajectory_fmt'):
            sections.append(context['trajectory_fmt'])
        return '\n\n'.join(sections)
