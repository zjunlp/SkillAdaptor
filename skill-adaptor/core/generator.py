"""Skill Generation Module"""

from __future__ import annotations
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from .types import Skill, LocalizedFault, Trajectory, FaultType
from .prompt_profile import PromptProfile
from .task_domain import PROCEDURE_VOCABULARY, extract_grading_rubric, generator_workflow_anchor, infer_task_category, is_meta_improvement, resolve_domain_principle
from .task_context import load_task_context_for_inference, load_task_markdown
from .llm_json import parse_llm_json_object
from .adapter_hints import get_active_hints
from .skill_body_utils import enrich_shell_skill_data, enrich_artifact_skill_data, smart_compact_skill_body, build_contrastive_failure_block, format_trajectory_steps_for_analysis, extract_wrong_actions_from_rejections
from .llm_params import chat_temperature
if TYPE_CHECKING:
    from .config import SkillAdaptorConfig

class Generator:
    MAX_SKILL_BODY_CHARS = 1600
    MAX_PROCEDURE_STEPS = 5

    def __init__(self, model_name: str='default', skill_template: str='enhanced', llm_client: Optional[Any]=None, duplication_similarity_threshold: float=0.75):
        self.llm_client = llm_client
        self.model_name = model_name
        self._skill_counter = 0
        self.duplication_similarity_threshold = duplication_similarity_threshold
        self.prompt_profile = PromptProfile(model_name=model_name, template=skill_template)

    def generate(self, trajectory: Trajectory, fault: LocalizedFault, existing_skills: Dict[str, Skill], rejection_summaries: Optional[List[str]]=None) -> Optional[Skill]:
        if self.llm_client is None:
            raise RuntimeError('LLM client not configured. Generator requires an LLM client. Provide llm_client parameter during initialization.')
        improvement = fault.improvement_principle
        for existing in existing_skills.values():
            if self._is_similar(improvement, existing.description):
                return None
        return self._generate_with_llm(trajectory, fault, existing_skills, rejection_summaries=rejection_summaries)

    def _generate_with_llm(self, trajectory: Trajectory, fault: LocalizedFault, existing_skills: Dict[str, Skill], rejection_summaries: Optional[List[str]]=None) -> Optional[Skill]:
        prompt = self._build_generation_prompt(fault, trajectory, existing_skills, rejection_summaries=rejection_summaries)
        response = self.llm_client.chat.completions.create(model=self.model_name, messages=[{'role': 'user', 'content': prompt}], temperature=chat_temperature(self.model_name, 0.3))
        content = response.choices[0].message.content
        skill_data = parse_llm_json_object(content, context='Generator skill proposal')
        task_brief = self._load_task_brief(fault.task_id)
        wrong_for_enrich = self._merge_wrong_action_with_rejection(fault.wrong_action or '', rejection_summaries)
        skill_data = enrich_shell_skill_data(
            skill_data,
            task_description=trajectory.task_description or '',
            task_brief=task_brief,
            wrong_action=wrong_for_enrich,
        )
        skill_data = enrich_artifact_skill_data(
            skill_data,
            task_description=trajectory.task_description or '',
            task_brief=task_brief,
            wrong_action=wrong_for_enrich,
            deliverable_targets=fault.deliverable_targets or None,
        )
        principle = str(skill_data.get('principle', fault.improvement_principle))
        if is_meta_improvement(principle):
            print(f'      [Generator] Rejected meta principle: {principle[:80]}')
            return None
        body_preview = self._format_skill_body(skill_data, fault)
        if self._is_meta_skill(skill_data, body_preview):
            print(f"      [Generator] Rejected meta-skill proposal: {skill_data.get('title', '')[:60]}")
            return None
        self._skill_counter += 1
        skill_id = f'gen_{fault.task_id}_{self._skill_counter}'
        body = self._format_skill_body(skill_data, fault)
        body = self._compact_skill_body(body)
        domain_category = self._infer_domain_category(fault.task_id)
        return Skill(id=skill_id, title=skill_data.get('title', self._generate_title(fault)), description=skill_data.get('principle', fault.improvement_principle), body=body, when_to_apply=self._sanitize_trigger(skill_data.get('when_to_apply', self._infer_when_to_apply(fault)), fault.task_id), created_from=fault.task_id, domain_category=domain_category)

    def _merge_wrong_action_with_rejection(self, wrong_action: str, rejection_summaries: Optional[List[str]]) -> str:
        base = (wrong_action or '').strip()
        extras = extract_wrong_actions_from_rejections(rejection_summaries)
        if not extras:
            if rejection_summaries:
                for line in rejection_summaries:
                    if 'agent_tail:' not in line:
                        continue
                    tail = line.split('agent_tail:', 1)[-1].strip()
                    if tail and tail not in base:
                        return f'{base} | validation_after_reject: {tail[:220]}'.strip(' |')
            return base
        merged = ' | '.join([base] + [e for e in extras if e not in base])
        return merged[:480]

    def _build_generation_prompt(self, fault: LocalizedFault, trajectory: Trajectory, existing_skills: Dict[str, Skill], rejection_summaries: Optional[List[str]]=None) -> str:
        contrast_block = build_contrastive_failure_block(fault, trajectory, rejection_summaries=rejection_summaries)
        context_steps = trajectory.get_step_context(fault.step_index, window=5)
        context_str = format_trajectory_steps_for_analysis(
            Trajectory(
                task_id=trajectory.task_id,
                task_description=trajectory.task_description,
                steps=context_steps,
                success=trajectory.success,
                total_reward=trajectory.total_reward,
            ),
            fault_step_index=fault.step_index,
            max_steps=12,
        )
        task_brief = self._load_task_brief(fault.task_id)
        full_md = load_task_markdown(fault.task_id) or task_brief
        task_ctx = load_task_context_for_inference(fault.task_id) or task_brief
        grading_rubric = extract_grading_rubric(full_md)
        workflow_anchor = generator_workflow_anchor(trajectory.task_description, task_ctx, fault.task_id)
        domain_principle = resolve_domain_principle(trajectory.task_description, task_ctx, fault.task_id)
        cat = infer_task_category(trajectory.task_description, task_ctx, fault.task_id)
        adapter_block = get_active_hints().generator_supplement
        existing_text = '\n'.join([f'- {s.id}: {s.title}\n  {s.description[:80]}...' for s in list(existing_skills.values())[:5]]) if existing_skills else 'None available'
        rejection_block = ''
        if rejection_summaries:
            rejection_block = '\n### Previously Rejected Proposals (do NOT repeat)\n' + '\n'.join(rejection_summaries[:5]) + '\n'
        deliverable_line = ', '.join(fault.deliverable_targets) if fault.deliverable_targets else 'none'
        artifact_block = ''
        if fault.wrong_artifact_note or fault.rubric_gap or fault.deliverable_targets:
            artifact_block = f"""
### Deliverable anchor (from localization — shape only, no answers)
- Targets: {deliverable_line}
- Wrong artifact at t*: {fault.wrong_artifact_note or 'see Wrong Action below'}
- Rubric gap: {fault.rubric_gap or 'deliverable format + scenario fidelity'}
"""
        return f"""# Skill Generation from Failure Analysis\n\nYou are an expert agent debugger for SkillAdaptor. Distill a **compact**, **reusable** skill —\none actionable patch per localized fault, transferable within the task category.\n\n**Use Generator when:** fault_type=skill_missing, OR cold-start (empty bank), OR fault_type=reasoning_wrong needing a soft procedural patch.\nIf an existing skill was misleading (skill_wrong) and Linker named it, revision (not new skill) is preferred — do not duplicate.\n\n{contrast_block}\n\n**Improvement direction (from localization — stay aligned, do not narrow to one task ID):**\n{fault.improvement_principle[:400]}\n{artifact_block}\n**Category workflow (primary / fallback / verify):**\n{workflow_anchor}\n\n## Task category: {cat}\n\n## Rubric shapes for verification (NO answers — procedure must satisfy these shapes)\n{grading_rubric or 'Deliverable exists; inputs consumed; internal consistency checks pass.'}\n\n## FORBIDDEN (meta-skill anti-patterns — instant reject)\n- Logging, capturing, or documenting transcripts/session_status as the main procedure\n- Meta-skills about monitoring the agent instead of solving the task\n- Task IDs or benchmark names in when_to_apply (deliverable filenames from the task prompt are allowed in procedure)\n- Numeric answers, expected scores, or golden values from grading rubrics\n\n## Required structure\n1. **Primary path**: concrete actions using tools (read / parse / write / run / test)\n2. **Fallback**: named alternate if primary fails (parse error, selector miss, etc.)\n3. **Verify**: checkpoint tied to rubric **shape** (artifact exists, tests pass, counts reconcile)\n4. **Negative**: anti-pattern from Wrong Action / wrong_artifact at t* (trajectory-grounded, no golden commands)\n5. **Scope**: state *when_to_apply* as observation patterns — skill must transfer to similar tasks in same category\n\n## Hard Limits\n- principle: max 2 sentences; reusable across tasks in this category\n- procedure: 3-5 steps; you MAY name deliverable filenames that appear in the task prompt (e.g. recovery.sh, command.txt); otherwise use generic "report deliverable"\n- Copy branch names, counts, and format constraints from the prompt — never invent alternate scenarios (remote backup, fetch-all)\n- Keep skill **narrow in category** but **not tied to one task id** — avoids harming unrelated validation tasks\n\n## Input Context\n\nTask ID: {fault.task_id}\nTask Brief:\n{task_brief}\n\nFault Step: {fault.step_index + 1}\nFault Type: {fault.fault_type.value}\n\n### Trajectory Context\n```\n{context_str}\n```\n\n### Fault Details\nObservation: {fault.observation[:500]}\nWrong Action: {fault.wrong_action}\nImprovement Direction: {fault.improvement_principle[:400]}\n\n### Existing Skills (Avoid Duplication)\n{existing_text}\n{rejection_block}\n{adapter_block}\n\n## Output Schema\n\nRespond with valid JSON in ```json``` blocks:\n\n```json\n{{\n  "title": "Concise skill name (5-8 words, domain-specific)",\n  "principle": "Core rule (1-2 sentences) — MUST include fallback + verify",\n  "when_to_apply": "Observation patterns when this skill applies",\n  "procedure": [\n    "Step 1: Primary action + expected outcome",\n    "Step 2: Fallback if step 1 fails (name the trigger)",\n    "Step 3: Verification against grader (file/test/count)",\n    "Step 4: Optional refine loop"\n  ],\n  "validation_criteria": "Rubric-shape checks only (no leaked answers): artifact exists, metrics recompute, tests pass",\n  "qualification_criteria": "Preconditions before applying",\n  "negative_example": {{\n    "what_not_to_do": "The failure pattern from this trajectory",\n    "why_it_fails": "Why grader score stays 0"\n  }}\n}}\n```\n\n{self.prompt_profile.model_specific_block('generator')}"""

    @staticmethod
    def _sanitize_trigger(text: str, task_id: str) -> str:
        text = re.sub('task[_\\-\\s]*\\d+[a-z0-9_\\-]*', ' ', text, flags=re.IGNORECASE)
        text = re.sub(re.escape(task_id), ' ', text, flags=re.IGNORECASE)
        text = re.sub('\\s+', ' ', text).strip()
        return text or 'When similar operational failure pattern appears'

    def _compact_skill_body(self, body: str) -> str:
        return smart_compact_skill_body(body, max_chars=self.MAX_SKILL_BODY_CHARS)
    _META_SKILL_PATTERNS = ('transcript', 'capture action', 'capture and document', 'log all action', 'document action', 'action logging', 'session_status', 'observability', 'monitor agent', 'record every step', 'logging protocol', 'initiate task with', 'concrete first action without')
    _DOMAIN_HINTS = PROCEDURE_VOCABULARY

    def _is_meta_skill(self, skill_data: Dict[str, Any], body: str) -> bool:
        title = str(skill_data.get('title', '')).lower()
        principle = str(skill_data.get('principle', '')).lower()
        combined = f'{title} {principle} {body.lower()}'
        if is_meta_improvement(combined):
            return True
        hits = sum((1 for p in self._META_SKILL_PATTERNS if p in combined))
        has_domain = any((h in combined for h in self._DOMAIN_HINTS))
        proc = skill_data.get('procedure') or []
        proc_text = ' '.join((str(p) for p in proc)).lower()
        has_proc_domain = any((h in proc_text for h in self._DOMAIN_HINTS))
        if not has_domain and (not has_proc_domain):
            return True
        return hits >= 2 or (hits >= 1 and (not has_domain))

    def _load_task_brief(self, task_id: str) -> str:
        return load_task_context_for_inference(task_id)

    def _format_skill_body(self, skill_data: Dict[str, Any], fault: LocalizedFault) -> str:
        procedure = skill_data.get('procedure', [])[:self.MAX_PROCEDURE_STEPS]
        proc_str = '\n'.join([f'{i + 1}. {step}' for i, step in enumerate(procedure)])
        qual = skill_data.get('qualification_criteria') or skill_data.get('validation_criteria', '')
        neg_example = skill_data.get('negative_example', {})
        neg_str = ''
        if neg_example and isinstance(neg_example, dict):
            neg_str = f"\n\n## Negative Example\n\n**Do NOT:** {neg_example.get('what_not_to_do', 'Unknown')}\n\n**Why:** {neg_example.get('why_it_fails', 'Causes error')}\n"
        return f"# {skill_data.get('title', 'Skill')}\n\n## Description\n{skill_data.get('principle', '')}\n\n## When to Apply\n{self._sanitize_trigger(skill_data.get('when_to_apply', ''), fault.task_id)}\n\n## Procedure\n{proc_str}\n\n## Qualification Criteria\n{qual}\n\n## Validation Criteria\n{skill_data.get('validation_criteria', 'Verify outcome matches expectation')}\n{neg_str}\n\n## Reference\n- Fault type: {fault.fault_type.value}\n\n{self.prompt_profile.render('generator')}\n"

    def _generate_title(self, fault: LocalizedFault) -> str:
        action = fault.wrong_action[:40].replace('click[', '').replace('search[', '')
        if fault.fault_type == FaultType.SKILL_MISSING:
            return f'Handle {action} situations'
        return f'Avoid {action} errors'

    def _infer_domain_category(self, task_id: str) -> str:
        import os
        from pathlib import Path
        pb = os.environ.get('PINCHBENCH_PATH', '').strip()
        if not pb:
            return ''
        from adapters.pinchbench_adapter.task_category import get_task_category
        tasks_dir = os.environ.get('PINCHBENCH_TASKS_DIR', 'tasks')
        return get_task_category(task_id, Path(pb) / tasks_dir)

    def _infer_when_to_apply(self, fault: LocalizedFault) -> str:
        obs_keywords = self._extract_keywords(fault.observation)
        if obs_keywords:
            return f"When observation contains: {', '.join(obs_keywords[:5])}"
        return 'When similar situation occurs'

    def _extract_keywords(self, text: str) -> List[str]:
        words = re.findall('\\b[a-zA-Z]{{4,}}\\b', text.lower())
        stopwords = {'with', 'from', 'they', 'have', 'this', 'that', 'will', 'your', 'should'}
        keywords = [w for w in words if w not in stopwords]
        seen = set()
        unique = []
        for k in keywords:
            if k not in seen:
                seen.add(k)
                unique.append(k)
        return unique

    def _is_similar(self, text1: str, text2: str, threshold: Optional[float]=None) -> bool:
        if threshold is None:
            threshold = self.duplication_similarity_threshold
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        if not words1 or not words2:
            return False
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        similarity = intersection / union if union > 0 else 0
        return similarity >= threshold

    def deduplicate(self, new_skills: List[Skill], existing_skills: Dict[str, Skill], threshold: Optional[float]=None) -> List[Skill]:
        if threshold is None:
            threshold = self.duplication_similarity_threshold
        unique = []
        for new_skill in new_skills:
            is_duplicate = False
            for existing in existing_skills.values():
                if self._is_similar(new_skill.description, existing.description, threshold):
                    is_duplicate = True
                    break
            if not is_duplicate:
                for accepted in unique:
                    if self._is_similar(new_skill.description, accepted.description, threshold):
                        is_duplicate = True
                        break
            if not is_duplicate:
                unique.append(new_skill)
        return unique
