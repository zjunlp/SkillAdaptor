"""PinchBench adapter hints — registered at run_pinchbench startup."""

from __future__ import annotations
from core.adapter_hints import AdapterHints, activate_benchmark_hints, register_adapter_hints
PINCHBENCH_HINTS = AdapterHints(benchmark='pinchbench', localizer_supplement='\n### PinchBench adapter (short coding-agent trajectories)\n- Localize at the step where a deliverable diverged from the rubric, not at session bootstrap.\n- If the agent skipped read/parse before write, classify skill_missing.\n- If the same command or selector failed twice without tactic change, classify reasoning_wrong.\n- Improvement must name concrete tools (git, grep, pytest, parser, file write) — not transcript capture.\n'.strip(), generator_supplement='\n### PinchBench adapter (executable patch)\n- The skill must change verifier-visible behavior on the next run (not documentation-only).\n- Test-generation tasks: run the project test runner before claiming completion.\n- Spreadsheet/log tasks: include an independent recompute or count cross-check against the prompt.\n- Shell tasks: output artifact must be a single executable command line, no prose.\n- Bundle exactly one fix per skill — do not merge unrelated categories.\n'.strip(), reviser_supplement='\n### PinchBench adapter (revision)\n- Preserve category scope; tighten procedure steps without adding meta-logging.\n- After revision, procedure must still include an explicit verify step tied to rubric shape.\n'.strip())

def install_pinchbench_hints() -> None:
    register_adapter_hints('pinchbench', PINCHBENCH_HINTS)
    activate_benchmark_hints('pinchbench')
