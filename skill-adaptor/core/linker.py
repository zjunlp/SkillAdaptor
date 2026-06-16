"""Skill Attribution (Linker) Module."""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from .llm_json import parse_llm_json_object
from .types import LocalizedFault, SkillAttribution, Skill, FaultType
from .prompt_profile import PromptProfile

class Linker:

    def __init__(self, model_name: str='default', skill_template: str='enhanced'):
        self.model_name = model_name
        self.prompt_profile = PromptProfile(model_name=model_name, template=skill_template)

    def attribute(self, fault: LocalizedFault, skill_bank: Dict[str, Skill], llm_client: Any, skill_matcher: Optional[Any]=None) -> List[SkillAttribution]:
        if fault.fault_type == FaultType.SKILL_MISSING:
            return []
        if not skill_bank:
            return []
        if llm_client is None:
            raise RuntimeError('LLM client required for attribution.')
        return self._attribute_with_llm(fault, skill_bank, llm_client, skill_matcher)

    def _attribute_with_llm(self, fault: LocalizedFault, skill_bank: Dict[str, Skill], llm_client: Any, skill_matcher: Optional[Any]=None) -> List[SkillAttribution]:
        relevant_skills = self._get_relevant_skills(fault, skill_bank, skill_matcher)
        prompt = self._build_attribution_prompt(fault, relevant_skills)
        response = llm_client.chat.completions.create(model=self.model_name, messages=[{'role': 'user', 'content': prompt}], temperature=0.2)
        content = response.choices[0].message.content
        parsed = parse_llm_json_object(content, context='Linker attribution')
        if not isinstance(parsed, dict):
            raise ValueError(f'Expected JSON object, got {type(parsed).__name__}')
        raw_items = parsed.get('attributions', [])
        if not isinstance(raw_items, list):
            raise ValueError(f'Linker attributions must be a list, got {type(raw_items).__name__}')
        attributions: List[SkillAttribution] = []
        for item in raw_items:
            if not isinstance(item, dict):
                raise ValueError(f'Each attribution entry must be an object, got {type(item).__name__}')
            skill_id = item.get('skill_id')
            if not skill_id:
                raise ValueError('Linker attribution entry missing skill_id')
            weight = item.get('weight', 0.5)
            reason = item.get('reason', '')
            if skill_id in skill_bank:
                attributions.append(SkillAttribution(skill_id=skill_id, weight=weight, reason=reason))
        attributions.sort(key=lambda x: x.weight, reverse=True)
        return attributions

    def _get_relevant_skills(self, fault: LocalizedFault, skill_bank: Dict[str, Skill], skill_matcher: Optional[Any]=None) -> Dict[str, Skill]:
        if fault.skills_at_fault:
            found = {sid: skill_bank[sid] for sid in fault.skills_at_fault if sid in skill_bank}
            if found:
                return found
        if fault.fault_type == FaultType.SKILL_WRONG and skill_bank and (skill_matcher is not None):
            query = f'{fault.task_id} {fault.observation[:400]} {fault.wrong_action[:120]} {fault.improvement_principle[:200]}'
            matches = skill_matcher.match_skills_to_task(skill_bank, query, top_k=3)
            if matches:
                return {skill.id: skill for skill, _ in matches}
        return {}

    def _build_attribution_prompt(self, fault: LocalizedFault, skill_bank: Dict[str, Skill]) -> str:
        if skill_bank:
            skills_text = '\n\n'.join([f'Skill ID: {skill_id}\n  Title: {skill.title}\n  Description: {skill.description[:200]}\n  When to Apply: {skill.when_to_apply[:150]}' for skill_id, skill in list(skill_bank.items())[:10]])
        else:
            skills_text = 'No skills were active at the fault step.'
        synthetic_examples = '\n<example>\nFault: Agent clicked "Buy Now" without selecting size/color\nSkills:\n  - skill_buy: "Click Buy Now to purchase"\n  - skill_verify: "Check product attributes before buying"\nAttribution:\n  - skill_buy: weight=0.7 (lacked precondition warning)\n  - skill_verify: weight=0.2 (available but not emphasized enough)\n</example>\n\n<example>\nFault: Agent kept searching with same query getting no results\nSkills:\n  - skill_search: "Search for products using keywords"\nAttribution:\n  - skill_search: weight=0.4 (worked but lacked refinement guidance)\n  Note: This suggests skill_missing for "refine_search" rather than skill_wrong\n</example>\n'
        return f'# Skill Attribution Analysis\n\nYou are an expert agent debugger analyzing which skill(s) contributed to a failure.\n\n## Fault Type Context\n\nFault type: {fault.fault_type.value}\n\n- skill_wrong: A skill was used but gave incorrect guidance → attribute to that skill with HIGH weight\n- skill_missing: No skill covered this situation → LOW weights across available skills (or empty)\n- reasoning_wrong: Skills were adequate but agent chose wrong → MEDIUM weights\n\n## Fault Context\n\n**Task**: {fault.task_id}\n**Fault Step**: {fault.step_index}\n\n**Observation at Fault Step**:\n```\n{fault.observation[:600]}\n```\n\n**Wrong Action Taken**: {fault.wrong_action[:200]}\n\n**What Should Have Been Done**:\n{fault.improvement_principle[:300]}\n\n## Skills to Evaluate\n\n{skills_text}\n\n## Examples\n\n{synthetic_examples}\n\n## Attribution Guidelines\n\nAssign weights based on:\n1. **Direct Instruction Match** (±0.3): Did the skill explicitly instruct the wrong action?\n2. **Context Appropriateness** (±0.2): Was the skill misapplied?\n3. **Omission** (±0.2): Did the skill fail to warn against the wrong approach?\n4. **Misleading Description** (±0.2): Was the skill definition confusing?\n\n## Weight Scale\n\n- **0.8-1.0**: Skill fully responsible\n- **0.5-0.7**: Skill partially responsible\n- **0.2-0.4**: Skill tangentially related\n- **0.0-0.1**: Skill not relevant\n\n## Output Format\n\n```json\n{{\n  "attributions": [\n    {{\n      "skill_id": "skill_id_here",\n      "weight": 0.75,\n      "reason": "Explanation"\n    }}\n  ]\n}}\n```\n\nIf no skill shares meaningful responsibility, return empty: {{"attributions": []}}\n\n**Important**: Do not assign weight >= 0.5 unless the skill directly caused or failed to prevent the wrong action.\nSkills with weight < 0.5 are ignored for revision.\n'

    def filter_high_confidence(self, attributions: List[SkillAttribution], threshold: float=0.6) -> List[SkillAttribution]:
        return [a for a in attributions if a.weight >= threshold]

    def get_primary_suspect(self, attributions: List[SkillAttribution]) -> Optional[SkillAttribution]:
        if not attributions:
            return None
        return max(attributions, key=lambda x: x.weight)
