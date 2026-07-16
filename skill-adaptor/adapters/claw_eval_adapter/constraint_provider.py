"""Claw-Eval-specific revision constraints (container / verifier shaped)."""

from __future__ import annotations

from typing import List


class ClawEvalConstraintProvider:
    CRITICAL_CONSTRAINTS = (
        '\n**Claw-Eval-Specific Constraints (Do NOT Violate):**\n\n'
        '1. **Container / sandbox safety**\n'
        '   - Prefer container-safe commands and paths under the task workspace\n'
        '   - Never invent host-absolute Windows paths (`C:\\\\...`) in skills\n'
        '   - Do not suggest installing packages or creating virtualenvs as the primary fix\n\n'
        '2. **Verifier-aligned deliverables**\n'
        '   - Skill procedures must produce artifacts/actions that the task grader can check\n'
        '   - Name explicit output paths when the prompt requires them\n'
        '   - Include a verify step matching claw-eval check shape (file exists, tool called, exit 0)\n\n'
        '3. **Tool use**\n'
        '   - Use the task-provided tools; do not invent undisclosed service APIs\n'
        '   - Validate tool results before advancing; handle empty/error responses\n\n'
        '4. **Trace hygiene**\n'
        '   - Do not write OpenClaw bootstrap/session vocabulary into skill bodies\n'
        '   - One patch per localized fault; avoid trajectory-level regenerate advice\n'
    )

    @classmethod
    def get_constraints(cls) -> str:
        return cls.CRITICAL_CONSTRAINTS

    @classmethod
    def get_summary(cls) -> str:
        return 'Claw-Eval constraints: container-safe, verifier-aligned, tool-validated'

    @classmethod
    def validate_skill_text(cls, text: str) -> tuple[bool, List[str]]:
        warnings: List[str] = []
        text_lower = text.lower()
        if 'c:\\' in text_lower or 'c:/' in text_lower:
            warnings.append('Warning: host-absolute Windows path in skill text')
        if 'virtualenv' in text_lower or 'pip install' in text_lower:
            warnings.append('Warning: package install / venv guidance in skill text')
        return (len(warnings) == 0, warnings)
