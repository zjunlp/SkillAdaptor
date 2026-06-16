"""Advanced Prompt Engineering for SkillEvolve"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from .types import Skill, LocalizedFault, Trajectory

class SkillPrompts:

    def __init__(self, model_name: str='default', template: str='enhanced'):
        self.model_name = model_name
        self.template = template

    def build_generation_prompt(self, fault: Any, trajectory: Any, existing_skills: List[Any], env_type: Optional[str]=None) -> str:
        ctx_steps = self._get_context_window(trajectory, fault.step_index, window=3)
        sections = [self._header('Skill Generation from Failure Analysis'), self._generation_instructions(), self._input_section(fault, ctx_steps, existing_skills, env_type), self._output_schema_generation(), self._quality_checklist()]
        return '\n\n'.join(sections)

    def build_revision_prompt(self, skill: Any, fault: Any, attribution: Any, failure_history: Optional[List]=None) -> str:
        sections = [self._header('Skill Revision - Minimal Targeted Changes'), self._revision_instructions(), self._skill_context(skill), self._failure_context(fault, attribution, failure_history), self._output_schema_revision(), self._revision_constraints()]
        return '\n\n'.join(sections)

    def _header(self, title: str) -> str:
        return f'# {title}\n\nYou are an expert agent debugger specializing in converting execution failures into reusable operational skills.\nYour output directly impacts autonomous agent performance - be precise, actionable, and thorough.'

    def _generation_instructions(self) -> str:
        return '## Task: Transform Failure Into Reusable Skill\n\nConvert the provided failure trajectory into a **reusable skill** that prevents similar failures.\n\n### Key Principles\n\n1. **Abstract but Concrete**: Extract the underlying principle, not just the specific fix\n   - BAD: "In task_123, click the red button instead of blue"\n   - GOOD: "When multiple options match criteria, prioritize the one with explicit confirmation markers"\n\n2. **Context-Aware Triggers**: Define clear when_to_apply conditions\n   - Include specific observation patterns or state indicators\n   - Mention prerequisite conditions that must be met\n\n3. **Actionable Procedure**: Provide verifiable steps\n   - Each step must be executable without human judgment\n   - Include validation checkpoints after critical actions\n\n4. **Negative Knowledge**: Document what NOT to do\n   - Describe the failure pattern explicitly\n   - Explain why the wrong approach fails\n\n5. **Reusability**: The skill should apply to similar situations beyond this specific failure\n\n### Execution Constraints (CRITICAL)\n\n1. **No Runtime Installation**: Skills MUST NOT require installing new packages or creating virtual environments during execution\n2. **Loop Prevention**: Include explicit checks to avoid infinite loops (e.g., "stop after 3 failed attempts")\n3. **Resource Safety**: Skills should work with available tools only; no external dependencies'

    def _input_section(self, fault: Any, context_steps: str, existing_skills: List[Any], env_type: Optional[str]) -> str:
        existing_text = '\n'.join([f'- {s.id}: {s.title}\n  {s.description[:80]}...' for s in existing_skills[:5]]) if existing_skills else 'None'
        env_hint = f'\n### Environment Type\n{env_type}\n' if env_type else ''
        return f'## Input Context\n\n### Task Information\n- Task ID: {fault.task_id}\n- Fault Step: {fault.step_index}\n- Preliminary Fault Type: {fault.fault_type.value}\n\n{env_hint}\n### Critical Failure Context\n```\n{context_steps}\n```\n\n### Fault Details\n**Observation at fault step:**\n{fault.observation[:300]}\n\n**Action Taken (Wrong):**\n{fault.wrong_action}\n\n**Preliminary Improvement Principle:**\n{fault.improvement_principle[:200]}\n\n### Existing Skills (Avoid Duplication)\n{existing_text}'

    def _output_schema_generation(self) -> str:
        return '## Output Schema (JSON)\n\nRespond with valid JSON wrapped in ```json``` blocks:\n\n```json\n{\n  "title": "Concise skill name (5-8 words, action-oriented)",\n  "principle": "Core reusable rule (1-2 sentences, abstract but actionable)",\n  "when_to_apply": "Specific trigger conditions (observation patterns, required states)",\n  "procedure": [\n    "Step 1: Concrete action with expected outcome",\n    "Step 2: Include validation criterion",\n    "Step 3: Next action based on validation result",\n    "..."\n  ],\n  "validation_criteria": "How to verify skill was applied correctly",\n  "negative_example": {\n    "what_not_to_do": "Description of the failure pattern",\n    "why_it_fails": "Explanation of the negative outcome"\n  }\n}\n```\n\n### Field Guidelines\n\n- **title**: Use action verbs ("Verify X Before Y", "Handle Z Conditions", "Avoid W Pattern")\n- **principle**: State the invariant or rule, not the specific instance\n- **when_to_apply**: Include specific keywords, patterns, or state indicators from observations\n- **procedure**: 3-5 numbered steps, each verifiable and deterministic\n- **validation_criteria**: Observable check that confirms success ("Confirm X appears in response", "Verify status is Y")\n- **negative_example**: Document the exact failure pattern this skill prevents'

    def _quality_checklist(self) -> str:
        return '## Quality Checklist\n\nBefore outputting, verify your skill meets these criteria:\n\n- [ ] **Specificity**: Addresses the specific failure pattern, not generic advice\n- [ ] **Reusability**: Would prevent similar failures in different tasks\n- [ ] **Actionability**: An agent could follow the procedure without human interpretation\n- [ ] **Verifiability**: Clear criteria to check if skill was applied correctly\n- [ ] **Non-duplication**: Adds value beyond existing skills in context\n- [ ] **Completeness**: Covers trigger, action, and validation\n\n### Common Mistakes to Avoid\n\n1. **Vague triggers**: "When things are confusing" → Use specific patterns\n2. **Over-generalization**: "Always be careful" → State concrete checks\n3. **Missing validation**: Steps without success criteria\n4. **Not reusable**: Too specific to one task/scenario'

    def _revision_instructions(self) -> str:
        return '## Task: Minimal Skill Revision\n\nRevise an existing skill to prevent a similar future failure.\nMake **targeted, minimal changes** rather than complete rewrites.\n\n### Revision Strategy\n\n1. **Add Preconditions**: Insert checks that would have caught this failure before it occurred\n2. **Add Negative Example**: Document this specific failure pattern in the skill\n3. **Clarify Ambiguity**: If instructions were misinterpreted, make them more explicit\n4. **Add Validation Step**: Insert verification checkpoint after critical actions\n\n### Constraints\n\n- Preserve all working parts of the original skill\n- ONLY add/modify content directly related to this failure\n- Do not change the fundamental approach unless proven wrong\n- Prefer additive changes (append rather than rewrite)\n\n### Anti-Patterns to Prevent\n\n1. **No Installation Guidance**: NEVER add instructions to install packages or setup environments\n2. **Loop Detection**: Add guards against repetitive actions (e.g., max 3 retries before switching strategy)\n3. **Progress Validation**: Ensure each step has verifiable progress; fail fast if stuck'

    def _skill_context(self, skill: Any) -> str:
        return f"## Skill to Revise\n\n**ID**: {skill.id}\n**Title**: {skill.title}\n**Version**: {skill.version}\n**Created From**: {skill.created_from or 'N/A'}\n\n**Description**:\n{skill.description}\n\n**Current Body**:\n```\n{skill.body}\n```"

    def _failure_context(self, fault: Any, attribution: Any, history: Optional[List]) -> str:
        history_note = ''
        if history and len(history) > 1:
            history_note = f'\n**Pattern Note**: This skill has {len(history)} recorded failures. Consider stronger constraints.\n'
        return f'## Failure Context\n\n**Task**: {fault.task_id}\n**Fault Step**: {fault.step_index}\n\n**Observation**:\n{fault.observation[:250]}\n\n**Wrong Action**:\n{fault.wrong_action}\n\n**Attribution Analysis**:\n- Weight: {attribution.weight:.2f} (0-1 scale of responsibility)\n- Reason: {attribution.reason[:200]}\n{history_note}'

    def _output_schema_revision(self) -> str:
        return '## Output Schema (JSON)\n\n```json\n{\n  "revision_type": "add_precondition | add_negative_example | clarify_procedure | add_validation",\n  "revision_summary": "One-sentence description of changes",\n  "original_assessment": "Why the original skill failed in this case",\n  "targeted_changes": {\n    "section_modified": "Which section was changed",\n    "before": "Original text (for reference)",\n    "after": "Revised text",\n    "rationale": "How this prevents the specific failure"\n  },\n  "impact_assessment": {\n    "severity_prevention": "high | medium | low - How effectively this prevents recurrence",\n    "generalization_risk": "none | low | medium - Risk of breaking other use cases"\n  }\n}\n```\n\n### Revision Type Guidelines\n\n- **add_precondition**: Add a check before critical action ("Before X, verify Y")\n- **add_negative_example**: Document this failure case in a dedicated section\n- **clarify_procedure**: Make ambiguous steps more explicit, add decision criteria\n- **add_validation**: Insert verification step after action ("Confirm X before proceeding")\n\nIf no revision is needed (skill not at fault), return {"revision_type": "none", "reason": "..."}'

    def _revision_constraints(self) -> str:
        return "## Constraints\n\n1. **Minimal Change Principle**: Make the smallest change that prevents this failure\n2. **Additive Preference**: Add new sections rather than modifying existing working content\n3. **Evidence-Based**: Every change must directly address the observed failure\n4. **Non-Breaking**: Ensure changes don't invalidate correct use cases of the skill\n5. **Document Rationale**: Explain how each change prevents the specific failure"

    def _get_context_window(self, trajectory: Any, fault_idx: int, window: int=3) -> str:
        steps = trajectory.steps
        start = max(0, fault_idx - window)
        end = min(len(steps), fault_idx + window + 1)
        lines = []
        for i in range(start, end):
            step = steps[i]
            prefix = '>>> ' if i == fault_idx else '    '
            lines.append(f'{prefix}[{i}] Action: {step.action[:60]}')
            obs = step.observation[:100].replace('\n', ' ')
            lines.append(f"      Obs: {obs}{('...' if len(step.observation) > 100 else '')}")
            if step.skills_used:
                lines.append(f"      Skills: {', '.join(step.skills_used)}")
        return '\n'.join(lines)

class EnvironmentPromptMixin:

    @staticmethod
    def webshop_tricks() -> Dict[str, str]:
        return {'search_patterns': 'search[keyword]', 'browse_patterns': 'click[next|prev]', 'product_patterns': 'click[b0...]', 'buy_patterns': 'click[buy_now]', 'common_failures': ['Page-flipping without checking products', 'Buying without attribute verification', 'Search terms not matching goal'], 'loop_prevention': ['Stop flipping pages after 3 next/prev without product clicks', 'Avoid repeating the same search query', 'If stuck on search results, click a product to examine details'], 'execution_constraints': ['DO NOT install packages or create virtual environments', 'Work only with available browser actions']}

    @staticmethod
    def pinchbench_tricks() -> Dict[str, str]:
        return {'tool_patterns': 'execute | call | run', 'file_patterns': 'read | write | parse', 'api_patterns': 'request | response | status', 'common_failures': ['Wrong tool selection for task type', 'Missing error handling on API calls', 'Not validating output format'], 'loop_prevention': ['Limit retries to 3 attempts before switching approach', 'Detect repeated tool calls with same parameters', 'If HTTP request fails 3 times, check network or credentials'], 'execution_constraints': ['DO NOT install new packages during task execution', 'DO NOT create virtual environments', 'Use only available system tools and pre-installed libraries']}

def get_prompt_builder(model_name: str='default', template: str='enhanced') -> SkillPrompts:
    return SkillPrompts(model_name=model_name, template=template)
