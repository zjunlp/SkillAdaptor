"""Skill Revision Module"""

from __future__ import annotations
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING, Union
from .types import Skill, LocalizedFault, SkillAttribution, Trajectory
from .skill_body_utils import enrich_shell_skill_data, enrich_artifact_skill_data, build_contrastive_failure_block, format_trajectory_steps_for_analysis, extract_wrong_actions_from_rejections
from .task_context import load_task_context_for_inference, load_task_markdown
from .prompt_profile import PromptProfile
from .prompts import SkillPrompts
from .adapter_hints import get_active_hints
from .llm_json import parse_llm_json_object
from .llm_params import chat_temperature
if TYPE_CHECKING:
    from .config import SkillAdaptorConfig
RevisionHandler = Callable[[Skill, Dict[str, Any], LocalizedFault], Skill]

class Reviser:
    DEFAULT_REVISION_TYPES = ['add_precondition', 'add_negative_example', 'clarify_procedure', 'add_validation', 'reorder_workflow', 'remove_outdated', 'consolidate', 'generalize', 'specialize', 'none']

    def __init__(self, model_name: str='default', skill_template: str='enhanced', history_dir: Optional[Path]=None, llm_client: Optional[Any]=None, benchmark_constraints: Optional[str]=None, max_iterations: int=3):
        self.llm_client = llm_client
        self.model_name = model_name
        self.history_dir = Path(history_dir) if history_dir else None
        self._fault_history: dict[str, list[LocalizedFault]] = defaultdict(list)
        self.prompt_profile = PromptProfile(model_name=model_name, template=skill_template)
        self.prompt_builder = SkillPrompts(model_name=model_name, template=skill_template)
        self._revision_handlers: Dict[str, RevisionHandler] = {}
        self._register_default_handlers()
        self._load_history()
        self.benchmark_constraints = benchmark_constraints or ''
        self.max_iterations = max_iterations

    def set_benchmark_constraints(self, constraints: str) -> None:
        self.benchmark_constraints = constraints

    def _register_default_handlers(self) -> None:
        self._revision_handlers = {'add_precondition': self._handle_add_precondition, 'add_negative_example': self._handle_add_negative_example, 'clarify_procedure': self._handle_clarify_procedure, 'add_validation': self._handle_add_validation, 'reorder_workflow': self._handle_reorder_workflow, 'remove_outdated': self._handle_remove_outdated, 'consolidate': self._handle_consolidate, 'generalize': self._handle_generalize, 'specialize': self._handle_specialize}

    def register_revision_handler(self, revision_type: str, handler: RevisionHandler) -> None:
        self._revision_handlers[revision_type] = handler

    def _handle_add_precondition(self, skill: Skill, changes: Dict[str, Any], fault: LocalizedFault) -> Skill:
        precond = changes.get('after', '')
        if precond:
            if '## Preconditions' not in skill.body:
                skill.body += f'\n\n## Preconditions\n\n- {precond}\n'
            else:
                skill.body = skill.body.replace('## Preconditions', f'## Preconditions\n\n- {precond}')
        return skill

    def _handle_add_negative_example(self, skill: Skill, changes: Dict[str, Any], fault: LocalizedFault) -> Skill:
        example = changes.get('after') or changes.get('negative_example', {})
        if isinstance(example, dict):
            what_not = example.get('what_not_to_do', 'Unknown action')
            why = example.get('why_it_fails', 'Causes error')
        else:
            what_not = str(example)
            why = 'Causes error'
        section = f'\n\n## Negative Example (from {fault.task_id})\n\n**Do NOT:** {what_not}\n\n**Why it fails:** {why}\n'
        skill.body = skill.body.rstrip() + section
        return skill

    def _handle_clarify_procedure(self, skill: Skill, changes: Dict[str, Any], fault: LocalizedFault) -> Skill:
        after_text = changes.get('after', '')
        section = changes.get('section_modified', '')
        if after_text:
            if section:
                pattern = f'(##\\s*{re.escape(section)}\\s*\\n)(.*?)(?=\\n##|$)'
                if re.search(pattern, skill.body, re.DOTALL | re.IGNORECASE):
                    skill.body = re.sub(pattern, f'\\1{after_text}\\n\\n', skill.body, flags=re.DOTALL | re.IGNORECASE)
                    return skill
            skill.description = after_text
        return skill

    def _handle_add_validation(self, skill: Skill, changes: Dict[str, Any], fault: LocalizedFault) -> Skill:
        validation = changes.get('after', '')
        if validation:
            if '## Validation' not in skill.body:
                skill.body += f'\n\n## Validation\n\n- {validation}\n'
            else:
                skill.body = skill.body.replace('## Validation', f'## Validation\n\n- {validation}')
        return skill

    def _handle_reorder_workflow(self, skill: Skill, changes: Dict[str, Any], fault: LocalizedFault) -> Skill:
        new_procedure = changes.get('after', '')
        if new_procedure:
            proc_pattern = '(##\\s*Procedure\\s*\\n)(.*?)(?=\\n##|$)'
            if re.search(proc_pattern, skill.body, re.DOTALL | re.IGNORECASE):
                skill.body = re.sub(proc_pattern, '\\1\\n(Reordered based on failure in ' + fault.task_id + ')\n' + new_procedure + '\n\n', skill.body, flags=re.DOTALL | re.IGNORECASE)
            else:
                skill.body += f'\n\n## Procedure (Reordered)\n\n{new_procedure}\n'
        return skill

    def _handle_remove_outdated(self, skill: Skill, changes: Dict[str, Any], fault: LocalizedFault) -> Skill:
        to_remove = changes.get('after') or changes.get('remove_text', '')
        if to_remove and to_remove in skill.body:
            skill.body = skill.body.replace(to_remove, '')
        return skill

    def _handle_consolidate(self, skill: Skill, changes: Dict[str, Any], fault: LocalizedFault) -> Skill:
        consolidated = changes.get('after', '')
        if consolidated:
            skill.body += f'\n\n## Consolidated Guidance\n\n{consolidated}\n'
        return skill

    def _handle_generalize(self, skill: Skill, changes: Dict[str, Any], fault: LocalizedFault) -> Skill:
        generalized = changes.get('after', '')
        if generalized:
            skill.when_to_apply = generalized
        return skill

    def _handle_specialize(self, skill: Skill, changes: Dict[str, Any], fault: LocalizedFault) -> Skill:
        specialized = changes.get('after', '')
        if specialized:
            if '## Edge Cases' not in skill.body:
                skill.body += f'\n\n## Edge Cases\n\n- {specialized}\n'
            else:
                skill.body = skill.body.replace('## Edge Cases', f'## Edge Cases\n\n- {specialized}')
        return skill

    def revise(self, skill: Skill, fault: LocalizedFault, attribution: SkillAttribution, iterative: bool=False, rejection_summaries: Optional[List[str]]=None, trajectory: Optional[Trajectory]=None) -> Optional[Skill]:
        if self.llm_client is None:
            raise RuntimeError('LLM client not configured. Reviser requires an LLM client.')
        self.record_fault(skill.id, fault)
        if iterative:
            return self._revise_iterative(skill, fault, attribution, rejection_summaries, trajectory=trajectory)
        return self._revise_with_llm(skill, fault, attribution, rejection_summaries, trajectory=trajectory)

    def _revise_iterative(self, skill: Skill, fault: LocalizedFault, attribution: SkillAttribution, rejection_summaries: Optional[List[str]]=None, trajectory: Optional[Trajectory]=None) -> Optional[Skill]:
        current_skill = skill
        revised_skill = None
        for iteration in range(self.max_iterations):
            result = self._revise_with_llm(current_skill, fault, attribution, rejection_summaries, trajectory=trajectory)
            if result is None:
                break
            revised_skill = result
            current_skill = revised_skill
            revised_skill.body += f'\n<!-- Revision iteration {iteration + 1} -->'
        return revised_skill

    def revise_comprehensive(self, skill: Skill, faults: List[LocalizedFault], attributions: List[SkillAttribution]) -> Optional[Skill]:
        if not faults or not attributions:
            return None
        if len(faults) != len(attributions):
            raise ValueError('faults and attributions must have same length')
        current_skill = skill
        final_revised = None
        for fault, attribution in zip(faults, attributions):
            if attribution.weight < 0.3:
                continue
            result = self.revise(current_skill, fault, attribution, iterative=True)
            if result is not None:
                final_revised = result
                current_skill = result
        return final_revised
    MAX_REVISED_BODY_CHARS = 2000

    def _revise_with_llm(self, skill: Skill, fault: LocalizedFault, attribution: SkillAttribution, rejection_summaries: Optional[List[str]]=None, trajectory: Optional[Trajectory]=None) -> Optional[Skill]:
        history = self._fault_history.get(skill.id, [])
        prompt = self._build_revision_prompt(skill, fault, attribution, history, rejection_summaries=rejection_summaries, trajectory=trajectory)
        try:
            response = self.llm_client.chat.completions.create(model=self.model_name, messages=[{'role': 'user', 'content': prompt}], temperature=chat_temperature(self.model_name, 0.2))
            content = response.choices[0].message.content
        except Exception as e:
            raise RuntimeError(f'LLM revision call failed: {e}') from e
        revision_data = parse_llm_json_object(content, context='Reviser skill revision')
        if revision_data.get('skill_profile') and isinstance(revision_data['skill_profile'], dict):
            revised = self._apply_skill_profile_revision(skill, revision_data, fault)
            return self._post_enrich_revised_skill(revised, fault, trajectory, rejection_summaries)
        self._validate_revision_data(revision_data)
        if revision_data.get('revision_type') == 'none':
            return None
        revised = self._apply_structured_revision(skill, revision_data, fault)
        if revised is None:
            return None
        return self._post_enrich_revised_skill(revised, fault, trajectory, rejection_summaries)

    def _compact_body(self, body: str) -> str:
        if len(body) <= self.MAX_REVISED_BODY_CHARS:
            return body
        return body[:self.MAX_REVISED_BODY_CHARS] + '\n\n<!-- compacted -->\n'

    def _validate_revision_data(self, data: Dict[str, Any]) -> None:
        required_fields = ['revision_type', 'revision_summary', 'targeted_changes']
        for field in required_fields:
            if field not in data:
                raise ValueError(f'Missing required field: {field}')
        changes = data.get('targeted_changes', {})
        if not isinstance(changes, dict):
            raise ValueError('targeted_changes must be a dictionary')
        impact = data.get('impact_assessment', {})
        if impact:
            valid_severity = ['high', 'medium', 'low']
            severity = impact.get('severity_prevention', '').lower()
            if severity and severity not in valid_severity:
                raise ValueError(f'Invalid severity_prevention: {severity}')
            valid_risk = ['none', 'low', 'medium', 'high']
            risk = impact.get('generalization_risk', '').lower()
            if risk and risk not in valid_risk:
                raise ValueError(f'Invalid generalization_risk: {risk}')

    def _build_revision_prompt(self, skill: Skill, fault: LocalizedFault, attribution: Any, history: Optional[List], rejection_summaries: Optional[List[str]]=None, trajectory: Optional[Trajectory]=None) -> str:
        history_note = ''
        pattern_warning = ''
        if history and len(history) > 1:
            history_note = f'\n**Pattern Note**: This skill has {len(history)} recorded failures. Consider stronger constraints.\n'
            if len(history) >= 3:
                pattern_warning = '\n**WARNING**: Multiple failures detected on this skill. Apply stricter validation.'
        existing_cases = ''
        if history:
            recent_cases = [f'- {f.task_id}: {f.wrong_action[:80]}' for f in history[-3:]]
            existing_cases = '\n'.join(recent_cases)
        few_shot_examples = self._get_few_shot_examples()
        benchmark_block = ''
        if self.benchmark_constraints:
            benchmark_block = f'\n### Benchmark-Specific Constraints (Do NOT Violate):\n{self.benchmark_constraints}\n'
        rejection_block = ''
        if rejection_summaries:
            rejection_block = '\n### Previously Rejected Proposals (avoid similar changes)\n' + '\n'.join(rejection_summaries[:5]) + '\n'
        contrast_block = ''
        if trajectory is not None:
            contrast_block = build_contrastive_failure_block(fault, trajectory, rejection_summaries=rejection_summaries)
        wrong_merged = fault.wrong_action or ''
        extras = extract_wrong_actions_from_rejections(rejection_summaries)
        if extras:
            wrong_merged = f'{wrong_merged} | prior_failures: {" | ".join(extras[:2])}'[:400]
        return f'''# Skill Revision - Minimal Targeted Changes

You are repairing an **existing** skill (skill_wrong path). Read the full step-level trace; do not invent new scenarios.

{contrast_block}

## Task: Minimal Skill Revision\n\nRevise an existing skill to prevent a similar future failure.\nMake **targeted, minimal changes** rather than complete rewrites.\n\n### Revision Strategy\n\n1. **Add Preconditions**: Insert checks that would have caught this failure before it occurred\n2. **Add Negative Example**: Document this specific failure pattern in the skill\n3. **Clarify Ambiguity**: If instructions were misinterpreted, make them more explicit\n4. **Add Validation Step**: Insert verification checkpoint after critical actions\n\n### Constraints (CRITICAL)\n\n- Preserve all working parts of the original skill\n- ONLY add/modify content directly related to this failure\n- Do not change the fundamental approach unless proven wrong\n- Prefer additive changes (append rather than rewrite)\n- Prefer: add_precondition, add_negative_example, add_validation, clarify_procedure\n- Avoid: generalize, consolidate (unless evidence demands it)\n- NEVER add instructions to install packages or create virtual environments\n- Add loop prevention constraints if the failure involves repetitive actions (max 3 retries)\n{benchmark_block}{rejection_block}\n\n## Skill to Revise\n\n**ID**: {skill.id}\n**Title**: {skill.title}\n**Version**: {skill.version}\n**Created From**: {skill.created_from or 'N/A'}\n\n**Description**:\n{skill.description}\n\n**Current Body**:\n```\n{skill.body}\n```\n\n## Failure Context\n\n**Task**: {fault.task_id}\n**Fault Step**: {fault.step_index}\n\n**Observation**:\n{fault.observation[:250]}\n\n**Wrong Action**:\n{wrong_merged}\n\n**Attribution Analysis**:\n- Weight: {attribution.weight:.2f} (0-1 scale of responsibility)\n- Reason: {attribution.reason[:200]}\n{history_note}{pattern_warning}\n\n### Recent Failure History\n{(existing_cases if existing_cases else 'None recorded')}\n\n## Few-Shot Examples\n\n{few_shot_examples}\n\n## Output Schema (JSON) — prefer skill_profile (paper-aligned full replace)\n\n```json\n{{\n  "update_mode": "revise_existing",\n  "target_skill_id": "{skill.id}",\n  "revision_summary": "One-sentence description of changes",\n  "skill_profile": {{\n    "title": "{skill.title}",\n    "principle": "Core rule (max 2 sentences)",\n    "when_to_apply": "Trigger patterns only — no task ids",\n    "procedure": ["Step 1", "Step 2", "Step 3"],\n    "qualification_criteria": "Preconditions before applying",\n    "negative_example": {{\n      "what_not_to_do": "...",\n      "why_it_fails": "..."\n    }}\n  }}\n}}\n```\n\nLegacy patch mode (only if skill_profile is impossible):\n\n```json\n{{\n  "revision_type": "<add_precondition | add_negative_example | clarify_procedure | add_validation | none>",\n  "revision_summary": "One-sentence description of changes",\n  "original_assessment": "Why the original skill failed in this case",\n  "targeted_changes": {{\n    "section_modified": "Which section was changed (e.g., 'Preconditions', 'Procedure')",\n    "before": "Original text (for reference)",\n    "after": "Revised text (use markdown format)",\n    "rationale": "How this prevents the specific failure"\n  }},\n  "impact_assessment": {{\n    "severity_prevention": "high | medium | low - How effectively this prevents recurrence",\n    "generalization_risk": "none | low | medium | high - Risk of breaking other use cases"\n  }}\n}}\n```\n\n### Revision Type Guidelines\n\n**Core Types:**\n- **add_precondition**: Add a check before critical action ("Before X, verify Y")\n- **add_negative_example**: Document this failure case in its own section\n- **clarify_procedure**: Make ambiguous steps more explicit, add decision criteria\n- **add_validation**: Insert verification step after action ("Confirm X before proceeding")\n- **reorder_workflow**: Fix workflow/procedure ordering issues\n- **none**: No revision needed (skill not at fault)\n\n**Extended Types** (via extensible handler registry):\n- **remove_outdated**: Delete harmful/obsolete guidance causing failures\n- **consolidate**: Merge overlapping or redundant instructions\n- **generalize**: Broaden skill applicability to similar contexts\n- **specialize**: Add explicit edge case handling\n\n**Custom Types:** If none fit, use a descriptive name. The system will apply `targeted_changes.after` content to a new section named after your type.\n\n{get_active_hints().reviser_supplement}\n\n{self.prompt_profile.model_specific_block('reviser')}'''

    def _get_few_shot_examples(self) -> str:
        return '### Example 1: Adding Precondition\n\n**Original Skill Failure**: Agent proceeded without verifying prerequisites\n\n**Correct Revision**:\n```json\n{\n  "revision_type": "add_precondition",\n  "revision_summary": "Add prerequisite check before tool execution",\n  "original_assessment": "Skill didn\'t specify need to verify tool availability before use",\n  "targeted_changes": {\n    "section_modified": "Preconditions",\n    "before": "(no preconditions section)",\n    "after": "Before calling execute(), verify the tool is installed by checking \'which <tool>\' output",\n    "rationale": "This prevents the FileNotFoundError when tool is missing"\n  },\n  "impact_assessment": {\n    "severity_prevention": "high",\n    "generalization_risk": "none"\n  }\n}\n```\n\n### Example 2: Adding Negative Example\n\n**Original Skill Failure**: Agent repeated a pattern that causes infinite loops\n\n**Correct Revision**:\n```json\n{\n  "revision_type": "add_negative_example",\n  "revision_summary": "Document the avoid-loop pattern with explanation",\n  "original_assessment": "Skill didn\'t warn against repeatedly searching without examining results",\n  "targeted_changes": {\n    "section_modified": "Negative Examples",\n    "before": "(no negative examples)",\n    "after": "**Do NOT:** Search repeatedly without clicking on any product\\n\\n**Why it fails:** This creates an infinite loop - you must examine specific products to make progress",\n    "rationale": "Explicit warning prevents the infinite search loop behavior"\n  },\n  "impact_assessment": {\n    "severity_prevention": "high",\n    "generalization_risk": "none"\n  }\n}\n```\n\n### Example 3: Custom Type (Unknown to System)\n\n**Situation**: A completely new type of error not covered by built-in types\n\n**Correct Revision**:\n```json\n{\n  "revision_type": "add_caching_guidance",\n  "revision_summary": "Add guidance on handling stale API cache",\n  "original_assessment": "API returns 304 but skill doesn\'t mention cache handling",\n  "targeted_changes": {\n    "section_modified": "API Handling",\n    "before": "Make API request and parse response",\n    "after": "If API returns 304 (Not Modified), clear local cache and retry with Cache-Control: no-cache header",\n    "rationale": "Prevents false negatives from stale cached responses"\n  },\n  "impact_assessment": {\n    "severity_prevention": "medium",\n    "generalization_risk": "low"\n  }\n}\n```\n'

    def _post_enrich_revised_skill(
        self,
        revised: Skill,
        fault: LocalizedFault,
        trajectory: Optional[Trajectory],
        rejection_summaries: Optional[List[str]],
    ) -> Skill:
        """Apply shell/artifact enrich so IMMEDIATE ACTION harness can bind agent execution."""
        task_md = ''
        try:
            task_brief = load_task_context_for_inference(fault.task_id) or ''
            task_md = load_task_markdown(fault.task_id, required=False) or task_brief
        except Exception:
            task_brief = ''
            task_md = ''
        wrong = fault.wrong_action or ''
        extras = extract_wrong_actions_from_rejections(rejection_summaries)
        if extras:
            wrong = f'{wrong} | {" | ".join(extras[:2])}'[:480]
        profile = {
            'title': revised.title,
            'principle': revised.description,
            'when_to_apply': revised.when_to_apply,
            'procedure': [
                ln.strip().lstrip('0123456789. ')
                for ln in revised.body.splitlines()
                if ln.strip() and not ln.strip().startswith('#')
            ][:5],
            'negative_example': {},
        }
        desc = (trajectory.task_description if trajectory else '') or task_brief
        profile = enrich_shell_skill_data(
            profile,
            task_description=desc,
            task_brief=task_brief,
            wrong_action=wrong,
        )
        profile = enrich_artifact_skill_data(
            profile,
            task_description=desc,
            task_brief=task_brief,
            wrong_action=wrong,
            deliverable_targets=fault.deliverable_targets or None,
        )
        procedure = profile.get('procedure', [])[:5]
        proc_str = '\n'.join(f'{i + 1}. {step}' for i, step in enumerate(procedure))
        neg = profile.get('negative_example') or {}
        neg_str = ''
        if isinstance(neg, dict) and neg.get('what_not_to_do'):
            neg_str = (
                f"\n\n## Negative Example\n\n**Do NOT:** {neg.get('what_not_to_do')}\n\n"
                f"**Why:** {neg.get('why_it_fails', 'Causes error')}\n"
            )
        revised.description = profile.get('principle', revised.description)
        revised.body = (
            f'# {revised.title}\n\n## Description\n{revised.description}\n\n'
            f'## When to Apply\n{revised.when_to_apply}\n\n## Procedure\n{proc_str}\n'
            f'{neg_str}\n\n## Reference\n- Repaired from {fault.task_id}\n'
        )
        revised.body = self._compact_body(revised.body)
        return revised

    def _apply_skill_profile_revision(self, skill: Skill, revision: Dict[str, Any], fault: LocalizedFault) -> Skill:
        profile = revision.get('skill_profile', {})
        revised = skill.copy_with_revision()
        revised.title = profile.get('title', skill.title) or skill.title
        revised.description = profile.get('principle', skill.description) or skill.description
        revised.when_to_apply = profile.get('when_to_apply', skill.when_to_apply) or skill.when_to_apply
        procedure = profile.get('procedure', [])[:5]
        proc_str = '\n'.join((f'{i + 1}. {step}' for i, step in enumerate(procedure)))
        qual = profile.get('qualification_criteria', '')
        neg = profile.get('negative_example', {}) or {}
        neg_str = ''
        if isinstance(neg, dict) and neg.get('what_not_to_do'):
            neg_str = f"\n\n## Negative Example\n\n**Do NOT:** {neg.get('what_not_to_do')}\n\n**Why:** {neg.get('why_it_fails', 'Causes error')}\n"
        revised.body = f"# {revised.title}\n\n## Description\n{revised.description}\n\n## When to Apply\n{revised.when_to_apply}\n\n## Procedure\n{proc_str}\n\n## Qualification Criteria\n{qual}\n{neg_str}\n\n## Reference\n- Fault type: {fault.fault_type.value}\n- Revision: {revision.get('revision_summary', 'skill_profile replace')}\n"
        revised.body = self._compact_body(revised.body)
        return revised

    def _apply_structured_revision(self, skill: Skill, revision: Dict[str, Any], fault: LocalizedFault) -> Optional[Skill]:
        revision_type = revision.get('revision_type', 'none')
        if revision_type == 'none':
            return None
        revised = skill.copy_with_revision()
        changes = revision.get('targeted_changes', {})
        if revision_type in self._revision_handlers:
            try:
                revised = self._revision_handlers[revision_type](revised, changes, fault)
            except Exception as e:
                print(f'Warning: Handler for {revision_type} failed: {e}. Using generic handler.')
                self._apply_generic_revision(revised, revision_type, changes, fault)
        else:
            self._apply_generic_revision(revised, revision_type, changes, fault)
        if self.get_fault_count(skill.id) >= 3:
            revised.body = self._add_cluster_revision(revised.body, skill.id)
        revised.body += f"\n\n## Revision Note\nVersion {revised.version}: Addressed failure in {fault.task_id}\n- Type: {revision_type}\n- Rationale: {revision.get('revision_summary', 'Improved error prevention')}\n- Impact: {revision.get('impact_assessment', {}).get('severity_prevention', 'unknown')} prevention\n"
        revised.body = self._compact_body(revised.body)
        return revised

    def _apply_generic_revision(self, skill: Skill, revision_type: str, changes: Dict[str, Any], fault: LocalizedFault) -> None:
        after_text = changes.get('after', '')
        before_text = changes.get('before', '')
        section = changes.get('section_modified', 'Additional Guidance')
        if not after_text:
            return
        if before_text and before_text in skill.body:
            skill.body = skill.body.replace(before_text, after_text)
            return
        section_header = f'## {section}'
        if revision_type != section.lower().replace(' ', '_'):
            section_header += f' ({revision_type})'
        if section_header not in skill.body:
            skill.body += f'\n\n{section_header}\n\n{after_text}\n'
        else:
            skill.body += f'\n\n### From {fault.task_id}\n{after_text}\n'

    def _add_cluster_revision(self, body: str, skill_id: str) -> str:
        recent = self._fault_history.get(skill_id, [])[-5:]
        if not recent:
            return body
        contexts = [f'- {f.task_id}: {f.wrong_action[:80]}' for f in recent]
        section = '\n\n## Clustered Failure Guidance\n\nThis skill has recurring failures across tasks. Apply stricter constraints:\n- Verify prerequisites before acting\n- Stop after repeated ineffective retries and switch strategy\n- Prefer conservative, validated actions over exploratory loops\n\nRecent recurring cases:\n' + '\n'.join(contexts) + '\n'
        return body.rstrip() + section

    def add_precondition(self, skill: Skill, precondition: str) -> Skill:
        revised = skill.copy_with_revision()
        if '## Preconditions' in revised.body:
            revised.body = revised.body.replace('## Preconditions', f'## Preconditions\n\n- {precondition}')
        else:
            revised.body = revised.body.rstrip() + f'\n\n## Preconditions\n\n- {precondition}\n'
        return revised

    def add_negative_example(self, skill: Skill, example: str, explanation: str) -> Skill:
        revised = skill.copy_with_revision()
        example_section = f'\n\n## Negative Example\n\n**Do NOT:** {example}\n\n**Why:** {explanation}\n'
        if '## Negative Example' in revised.body:
            revised.body = revised.body.rstrip() + '\n\n---\n' + example_section
        else:
            revised.body = revised.body.rstrip() + example_section
        return revised

    def _get_history_path(self) -> Optional[Path]:
        if self.history_dir is None:
            return None
        return self.history_dir / 'fault_history.json'

    def _load_history(self) -> None:
        history_path = self._get_history_path()
        if history_path is None or not history_path.exists():
            return
        try:
            data = json.loads(history_path.read_text(encoding='utf-8'))
            for skill_id, faults_data in data.items():
                self._fault_history[skill_id] = [LocalizedFault.from_dict(fault_dict) for fault_dict in faults_data]
        except (json.JSONDecodeError, TypeError, KeyError, ValueError) as e:
            print(f'Warning: Could not load fault history: {e}')

    def _save_history(self) -> None:
        history_path = self._get_history_path()
        if history_path is None:
            return
        try:
            self.history_dir.mkdir(parents=True, exist_ok=True)
            data = {skill_id: [fault.to_dict() for fault in faults] for skill_id, faults in self._fault_history.items()}
            history_path.write_text(json.dumps(data, indent=2), encoding='utf-8')
        except (OSError, TypeError) as e:
            print(f'Warning: Could not save fault history: {e}')

    def record_fault(self, skill_id: str, fault: LocalizedFault) -> None:
        self._fault_history[skill_id].append(fault)
        self._save_history()

    def get_fault_count(self, skill_id: str) -> int:
        return len(self._fault_history.get(skill_id, []))

    def clear_history(self, skill_id: Optional[str]=None) -> None:
        if skill_id is None:
            self._fault_history.clear()
        else:
            self._fault_history.pop(skill_id, None)
        self._save_history()
