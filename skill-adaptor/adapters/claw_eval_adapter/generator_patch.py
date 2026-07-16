"""Claw-Eval Generator — LLM-only skill proposals (no heuristic shortcuts)."""

from core.generator import Generator
from core.types import LocalizedFault, FaultType


class ClawEvalGenerator(Generator):
    """Same LLM generate/revise path as base Generator; title only is Claw-Eval-flavored."""

    def _generate_title(self, fault: LocalizedFault) -> str:
        principle = fault.improvement_principle
        principle_clean = principle.strip()
        if '.' in principle_clean:
            principle_clean = principle_clean.split('.')[0]
        words = principle_clean.split()
        if len(words) > 10:
            key_phrase = ' '.join(words[:10]) + '...'
        else:
            key_phrase = principle_clean
        if fault.fault_type == FaultType.SKILL_MISSING:
            return f'Handle: {key_phrase}'
        return f'Fix: {key_phrase}'
