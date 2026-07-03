"""Fault Localization Module"""

from __future__ import annotations
import re
from typing import Any, Dict, List, Optional
from .types import LocalizedFault, FaultType, Trajectory, Step
from .prompt_profile import PromptProfile
from .task_domain import infer_task_category
from .task_context import load_task_context_for_inference, load_task_markdown, truncate_task_markdown_for_inference
from .skill_body_utils import refine_localized_fault, format_trajectory_steps_for_analysis
from .adapter_hints import get_active_hints
from .llm_params import chat_temperature

class Localizer:
    SYNTHETIC_EXAMPLES = '\n<example type="skill_wrong">\nTask: Find a waterproof bluetooth speaker under $50\nTrajectory: Step 1 searches for speakers → Step 2 clicks on product → Step 3 buys immediately without checking waterproof rating\nAnalysis: The agent used a "buy product" skill but it lacked precondition checks.\nResult: t_star=3, fault_type="skill_wrong"\nImprovement: "Before purchasing electronics, verify the product has the required specifications (waterproof, battery life, etc.)"\n</example>\n\n<example type="skill_missing">\nTask: Buy kelly green 3x-large hoodies under $70\nTrajectory: Step 1 search[hoodies] → Step 2 click[next >] → Step 3 click[< prev] → ... Step 50 click[next >] (never clicked any product to check sizes)\nAnalysis: The agent kept flipping pages but never clicked products to verify size/color availability. Missing "click to verify" skill.\nResult: t_star=2, fault_type="skill_missing"\nImprovement: "When browsing search results, click on products that match the instruction to check their size and color options; do not only flip between pages without examining products."\n</example>\n\n<example type="reasoning_wrong">\nTask: Schedule a meeting for next Tuesday at 3pm\nTrajectory: Step 1 opens calendar → Step 2 navigates to correct week → Step 3 accidentally clicks on Wednesday instead of Tuesday\nAnalysis: The agent had correct skills but made wrong selection during execution.\nResult: t_star=3, fault_type="reasoning_wrong"\nImprovement: "Double-check the selected date matches the instruction before confirming the meeting."\n</example>\n\n<example type="skill_missing_tool_usage">\nTask: Calculate compound interest for $5000 over 5 years at 4%\nTrajectory: Step 1 thinks about formula → Step 2 attempts mental math → Step 3 gives approximate answer\nAnalysis: Agent lacked calculator tool skill, tried to do it manually.\nResult: t_star=1, fault_type="skill_missing"\nImprovement: "For financial calculations, always use the calculator tool to ensure precision."\n</example>\n\n<example type="skill_missing_pinchbench">\nTask: Recover corrupted git repository after bad merge\nTrajectory: Step 1 runs git status → Step 2 force-resets without backup → Step 3 loses commits\nAnalysis: No skill covered safe git recovery; agent skipped read-only diagnosis.\nResult: fault_chain=[2,3], t_star=2, fault_type="skill_missing"\nImprovement: "Before mutating git state, inspect reflog and create a backup branch; prefer read-only diagnosis first."\n</example>\n\n<example type="reasoning_wrong_pinchbench">\nTask: Run Playwright e2e test for login flow\nTrajectory: Step 1 launches browser → Step 2 fills wrong selector → Step 3 retries same selector 4 times\nAnalysis: Skills were adequate; agent picked wrong selector and looped without changing strategy.\nResult: fault_chain=[2,3], t_star=2, fault_type="reasoning_wrong"\nImprovement: "After 2 failed selector attempts, inspect DOM and switch selector strategy."\n</example>\n\n<example type="skill_missing_playwright">\nTask: Playwright e2e checkout flow times out waiting for network idle\nTrajectory: Step 1 launch browser → Step 2 goto page → Step 3 wait_for_load_state networkidle (timeout)\nAnalysis: No skill for resilient waiting; agent used brittle networkidle on SPA page.\nResult: fault_chain=[2,3], t_star=3, fault_type="skill_missing"\nImprovement: "Prefer domcontentloaded or explicit element waits over networkidle on dynamic pages."\n</example>\n\n<example type="skill_missing_spreadsheet">\nTask: Summarize quarterly_sales.csv and company_expenses.xlsx into data_summary.md\nTrajectory: Step 1 session_status → Step 2 tries openpyxl → ImportError → Step 3 gives up\nAnalysis: Agent lacked spreadsheet fallback skill; stopped after parser error.\nResult: fault_chain=[2,3], t_star=2, fault_type="skill_missing"\nImprovement: "On xlsx parse failure, use zip/XML sheet fallback; recompute aggregates and rewrite data_summary.md until totals match rubric."\n</example>\n\n<example type="skill_missing_artifact_git">\nTask: Translate git recovery into commands saved to recovery.sh (one git command per line)\nTrajectory: Step 1 writes recovery.sh containing git remote set-url / backup-remote script (unrelated to prompt branch moves)\nAnalysis: No skill anchored deliverable; agent invented wrong recovery scenario at first write.\nResult: fault_chain=[1], t_star=1, fault_type=skill_missing\ndeliverable_target: recovery.sh\nwrong_artifact: Wrote unrelated remote/backup script into recovery.sh instead of prompt branch/commit moves\nrubric_gap: git-only executable lines; deliverable file exists; scenario matches prompt\nimprovement_principle: Write prompt-faithful git commands to recovery.sh (one per line, names/counts from prompt); at t* agent wrote remote backup script instead of local branch moves.\n</example>\n\n<example type="skill_missing_nginx_log">\nTask: Analyze nginx_access.log JSON for 4xx/5xx patterns\nTrajectory: Step 1 reads file → Step 2 parses partial lines → Step 3 incomplete report\nAnalysis: Missing structured log aggregation skill.\nResult: t_star=2, fault_type="skill_missing"\nImprovement: "Parse all JSON lines; compute error rate and top paths/IPs; write error_analysis.md with verifiable counts."\n</example>\n'
    FAULT_TYPE_DEFINITIONS = '\n## Fault Type Definitions (choose exactly one)\n\n**skill_wrong**: An existing skill was misleading or incorrect (e.g., too vague, wrong emphasis, missing precondition).\n- Characteristics: Agent followed a skill\'s guidance but the guidance was wrong\n- Fix: Revise the existing skill\n- Example: Skill said "click buy" but didn\'t mention checking product attributes first\n\n**skill_missing**: No skill told the agent what to do in this situation.\n- Characteristics: Agent lacked guidance for the specific scenario; may have guessed randomly\n- Fix: Create a new skill\n- Example: Agent only flipped pages because no skill told it to click products to verify\n- Special case: If agent ONLY does next/prev navigation without product clicks → skill_missing\n\n**reasoning_wrong**: The agent made a reasoning/exploration mistake; skills were adequate.\n- Characteristics: Correct skills available but agent chose wrong action or misinterpreted UI\n- Fix: No skill repair needed (skip reviser)\n- Example: Correct product shown but agent clicked wrong button; or agent kept trying same failing action despite alternatives\n\n## Heuristics for Classification\n\n- NEVER product clicks + MANY next/prev clicks → strongly suggests skill_missing\n- Tool error messages (ENOENT, "not found") + skill was used → skill_wrong\n- Agent repeatedly says "trying" or "maybe" → reasoning_wrong (exploration mode)\n- Wrong final selection despite correct navigation → reasoning_wrong\n'

    def __init__(self, model_name: str='default', skill_template: str='enhanced', llm_client: Optional[Any]=None):
        self.llm_client = llm_client
        self.model_name = model_name
        self.low_score_success_threshold = 0.6
        self.prompt_profile = PromptProfile(model_name=model_name, template=skill_template)

    def localize(self, trajectory: Trajectory, llm_client: Optional[Any]=None) -> Optional[LocalizedFault]:
        if trajectory.success and trajectory.total_reward >= self.low_score_success_threshold:
            return None
        client = llm_client or self.llm_client
        if client is None:
            raise RuntimeError('LLM client required for localization. Provide llm_client parameter or set during initialization.')
        if not trajectory.steps:
            return None
        result = self._localize_with_llm(trajectory, client)
        return result

    def _localize_with_llm(self, trajectory: Trajectory, llm_client: Any) -> LocalizedFault:
        summary = self._trajectory_summary(trajectory.steps, max_steps=min(15, len(trajectory.steps)))
        full_trace = format_trajectory_steps_for_analysis(trajectory, max_steps=min(24, len(trajectory.steps)))
        recent_steps = trajectory.steps[-5:] if len(trajectory.steps) >= 5 else trajectory.steps
        final_context = '\n'.join([f'Step {s.index + 1}: {s.action[:80]}' for s in recent_steps])
        prompt = f"""# Fault Localization Analysis\n\nAnalyze the failed trajectory to identify the first mistake and classify the fault type.\n\n## Task Description\n{truncate_task_markdown_for_inference(trajectory.task_description or '', max_chars=500)}\n\n## Full Step-Level Trajectory (read every step; mark t* at earliest root-cause step)\n```\n{full_trace}\n```\n\n## Trajectory Summary (compressed)\n{summary}\n\n## Final Steps (Critical Context)\n{final_context}\n\n{self.FAULT_TYPE_DEFINITIONS}\n\n{self.SYNTHETIC_EXAMPLES}\n\n## Analysis Instructions\n\n1. **Extract fault_chain**: List 2-4 candidate fault steps (1-based), ranked by evidence strength\n2. **Select t_star**: Choose the primary step from fault_chain for this revision round (earliest root cause, not latest symptom)\n3. **Check for obvious patterns**:\n   - If agent NEVER clicked products but constantly flipped pages (next/prev) → skill_missing\n   - If agent made wrong selection despite correct navigation → reasoning_wrong\n   - If agent followed wrong guidance → skill_wrong\n   - If same tool+parameters repeated 3+ times without progress → reasoning_wrong (loop pattern)\n   - If ENOENT/tool-not-found after following a skill → skill_wrong (skill lacked preconditions)\n4. **Formulate improvement**: One concise sentence with **domain tools** (git/grep/pytest/csv/xlsx), not logging/transcript advice\n   - Name the **deliverable file** when the prompt specifies one (e.g. recovery.sh, command.txt)\n   - State what was wrong in the **artifact/action** at t* (generic: unrelated remote script — never golden commands)\n   - Never suggest installing packages or creating environments as the fix\n   - Never suggest "capture transcript" or "log actions" as the primary fix (meta-skills do not improve scores)\n   - For task category «{infer_task_category(trajectory.task_description, load_task_context_for_inference(trajectory.task_id), trajectory.task_id)}»: give concrete tool/deliverable steps, never transcript-only advice\n5. **Deliverable anchor** (when prompt names an output file in backticks):\n   - `deliverable_target` MUST be that filename (or none)\n   - `wrong_artifact` MUST describe what t* did to the deliverable (from trajectory action — never golden fix commands)\n   - `rubric_gap` MUST name grader **shape** (e.g. git-only lines, file exists, counts reconcile)\n   - `improvement_principle` MUST include: (a) deliverable filename, (b) rubric shape, (c) wrong_action pattern at t*\n\n{get_active_hints().localizer_supplement}\n\n{self.prompt_profile.constraints_block('localizer')}\n\n{self.prompt_profile.model_specific_block('localizer')}\n\n## Output Format\n\nProvide your analysis in this exact format:\n\nfault_chain: [step numbers, 1-based, e.g. 2, 5, 7]\nt_star: <step number from fault_chain - primary fault for this round>\ndeliverable_target: <output filename from prompt backticks, or none>\nwrong_artifact: <what was wrong in the deliverable/action at t* — no golden answers>\nrubric_gap: <one rubric-shape gap, e.g. git-only lines missing>\nimprovement_principle: <MUST name deliverable + rubric shape + wrong_action at t* — no golden commands>\nfault_type: <skill_wrong | skill_missing | reasoning_wrong>\nreason: <brief explanation of why this classification was chosen>\n"""
        response = llm_client.chat.completions.create(model=self.model_name, messages=[{'role': 'user', 'content': prompt}], temperature=chat_temperature(self.model_name, 0.2))
        content = response.choices[0].message.content
        t_star = 0
        improvement_principle = ''
        fault_type = FaultType.REASONING_WRONG
        fault_chain: List[int] = []
        deliverable_target = ''
        wrong_artifact = ''
        rubric_gap = ''
        for line in content.split('\n'):
            line = line.strip()
            if line.lower().startswith('fault_chain'):
                nums = re.findall('\\d+', line.split(':', 1)[-1])
                fault_chain = [int(n) for n in nums]
            elif line.lower().startswith('t_star'):
                m = re.search('\\d+', line)
                if m:
                    t_star = int(m.group()) - 1
            elif line.lower().startswith('deliverable_target'):
                deliverable_target = line.split(':', 1)[-1].strip().strip('"\'')
            elif line.lower().startswith('wrong_artifact'):
                wrong_artifact = line.split(':', 1)[-1].strip().strip('"\'')
            elif line.lower().startswith('rubric_gap'):
                rubric_gap = line.split(':', 1)[-1].strip().strip('"\'')
            elif line.lower().startswith('improvement_principle'):
                improvement_principle = line.split(':', 1)[-1].strip().strip('"\'')
            elif line.lower().startswith('fault_type'):
                ft_str = line.split(':', 1)[-1].strip().lower()
                if ft_str in ('skill_wrong', 'skill_missing', 'reasoning_wrong'):
                    fault_type = FaultType(ft_str)
        if not trajectory.steps:
            raise RuntimeError('Cannot localize fault: trajectory has no steps')
        if t_star < 0 or t_star >= len(trajectory.steps):
            raise ValueError(f'Localizer returned invalid t_star={t_star + 1} for trajectory with {len(trajectory.steps)} step(s)')
        if not improvement_principle:
            raise ValueError(f'Localizer returned empty improvement_principle for {trajectory.task_id}')
        fault_step = trajectory.steps[t_star]
        targets: List[str] = []
        if deliverable_target and deliverable_target.lower() not in ('none', 'n/a', ''):
            targets = [deliverable_target.strip('`')]
        fault = LocalizedFault(
            task_id=trajectory.task_id,
            step_index=t_star,
            fault_type=fault_type,
            observation=fault_step.observation,
            wrong_action=fault_step.action,
            skills_at_fault=fault_step.skills_used,
            improvement_principle=improvement_principle,
            fault_chain=fault_chain,
            deliverable_targets=targets,
            wrong_artifact_note=wrong_artifact,
            rubric_gap=rubric_gap,
        )
        task_md = load_task_markdown(trajectory.task_id) or ''
        return refine_localized_fault(fault, trajectory, task_md)

    def _trajectory_summary(self, steps: List[Step], max_steps: int=8) -> str:
        if not steps:
            return 'No steps in trajectory.'
        if len(steps) <= max_steps:
            selected_indices = list(range(len(steps)))
        else:
            selected_indices = [0]
            step_size = (len(steps) - 1) / (max_steps - 1)
            for i in range(1, max_steps - 1):
                idx = int(i * step_size)
                if idx != selected_indices[-1]:
                    selected_indices.append(idx)
            selected_indices.append(len(steps) - 1)
            if len(selected_indices) < max_steps and len(steps) > max_steps:
                mid = len(steps) // 2
                if mid not in selected_indices:
                    selected_indices.append(mid)
                    selected_indices.sort()
        lines = []
        prev_idx = -1
        for idx in selected_indices:
            if prev_idx >= 0 and idx > prev_idx + 1:
                lines.append(f'  ... ({idx - prev_idx - 1} steps omitted) ...')
            s = steps[idx]
            obs_preview = s.observation[:120].replace('\n', ' ')
            lines.append(f'Step {idx + 1}: obs=[{obs_preview}...] action={s.action}')
            prev_idx = idx
        if len(steps) > max_steps and selected_indices[-1] < len(steps) - 1:
            lines.append(f'... ({len(steps) - selected_indices[-1] - 1} more steps)')
        return '\n'.join(lines)
