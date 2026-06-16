"""Claw-Eval Generator Patch"""

from core.generator import Generator
from core.types import LocalizedFault, FaultType, Skill
from typing import Optional

class ClawEvalGenerator(Generator):

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

    def generate_simple_skill(self, fault: LocalizedFault) -> Optional[Skill]:
        from core.types import Skill, SkillBody
        title = self._generate_title(fault)
        body = SkillBody(description=fault.improvement_principle, when_to_apply=f'Use when: {fault.observation[:100]}...', steps=[f'1. Analyze the situation: {fault.observation[:80]}...', f'2. Apply principle: {fault.improvement_principle[:80]}...', '3. Verify the outcome matches expectation'], validation_criteria='Task completes successfully without the previous error')
        return Skill(id=f'claw_{fault.task_id}_s{fault.step_index}', title=title, body=body.format(), source_faults=[fault], metadata={'generated_by': 'ClawEvalGenerator', 'fault_type': fault.fault_type.value, 'improvement_principle': fault.improvement_principle})
