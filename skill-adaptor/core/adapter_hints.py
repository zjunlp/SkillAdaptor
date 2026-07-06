"""Per-benchmark hint bundles for Localizer / Generator / Reviser."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional

@dataclass(frozen=True)
class AdapterHints:
    benchmark: str
    localizer_supplement: str = ''
    generator_supplement: str = ''
    reviser_supplement: str = ''

    def is_empty(self) -> bool:
        return not (self.localizer_supplement.strip() or self.generator_supplement.strip() or self.reviser_supplement.strip())
_GENERIC_HINTS = AdapterHints(benchmark='generic', localizer_supplement='### Localization discipline\n- Pick t* at the earliest step where deliverable, rubric, or tool output diverged.\n- Prefer missing executable procedure over vague reasoning faults.\n- If the agent never invoked the right tool, lean skill_missing before reasoning_wrong.\n', generator_supplement='### Skill patch shape\n- One runnable patch: primary path → fallback → verify deliverable on disk.\n- Steps must name tools/files; ban placeholder tokens and answer literals.\n- End with a verification line the agent can execute before finishing.\n', reviser_supplement='### Revision guard\n- Change one skill section; keep title stable unless scope truly changed.\n- Preserve working steps; only replace the broken segment around t*.\n')
_REGISTRY: Dict[str, AdapterHints] = {}
_ACTIVE: Optional[str] = None

def register_adapter_hints(benchmark: str, hints: AdapterHints) -> None:
    _REGISTRY[benchmark.strip().lower()] = hints

def activate_benchmark_hints(benchmark: Optional[str]) -> None:
    global _ACTIVE
    key = (benchmark or 'generic').strip().lower()
    if key in ('openclaw-generic', 'pb'):
        key = 'pinchbench'
    if key in ('workspace', 'openclaw'):
        key = 'generic'
    _ACTIVE = key if key in _REGISTRY else 'generic' if key == 'generic' else _ACTIVE

def get_active_hints() -> AdapterHints:
    key = _ACTIVE or 'generic'
    if key in _REGISTRY:
        return _REGISTRY[key]
    return _GENERIC_HINTS

def reset_adapter_hints() -> None:
    global _ACTIVE
    _REGISTRY.clear()
    _ACTIVE = None
