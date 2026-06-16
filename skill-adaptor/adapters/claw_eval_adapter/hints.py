"""Claw-Eval adapter hints — OpenClaw container tasks."""

from __future__ import annotations
from core.adapter_hints import AdapterHints, activate_benchmark_hints, register_adapter_hints
CLAW_EVAL_HINTS = AdapterHints(benchmark='claw-eval', localizer_supplement='\n### Claw-Eval adapter\n- Strip thinking/JSON wrappers from actions when judging wrong_action.\n- Localize where container command or file deliverable failed verifier, not hook noise.\n'.strip(), generator_supplement='\n### Claw-Eval adapter\n- Skills must reference container-safe commands and explicit output paths under workspace.\n- Include verify step that matches claw-eval automated check shape (file exists, command exit 0).\n- One patch per fault; avoid OpenClaw session/bootstrap vocabulary in procedure.\n'.strip())

def install_claw_eval_hints() -> None:
    register_adapter_hints('claw-eval', CLAW_EVAL_HINTS)
    activate_benchmark_hints('claw-eval')
