"""SkillAdaptor Orchestrator - Main Controller"""

from __future__ import annotations
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from .types import Skill, Trajectory, LocalizedFault, SkillAttribution, ValidationResult, SkillBank, FaultType
from .config import SkillAdaptorConfig
from .localizer import Localizer
from .linker import Linker
from .reviser import Reviser
from .generator import Generator
from .validator import Validator, ValidationConfig, SimpleEvaluator
from .skill_bank import SkillBankManager
from .skill_matcher import SemanticSkillMatcher
from .task_context import load_task_markdown
from .skill_body_utils import refine_localized_fault, coerce_cold_start_fault, coerce_degraded_bank_fault

@dataclass
class SkillAdaptorIteration:
    iteration: int
    failures: int
    revised: List[str]
    generated: List[str]
    accepted: List[str]
    skill_count: int
    timestamp: str

class SkillAdaptorOrchestrator:

    def __init__(self, config: SkillAdaptorConfig, llm_client: Optional[Any]=None, benchmark_constraints: Optional[str]=None, task_category_fn: Optional[Callable[[str], str]]=None):
        self.config = config
        self.llm_client = llm_client
        self._task_category_fn = task_category_fn
        self.localizer = Localizer(model_name=config.model, skill_template=config.skill_template, llm_client=llm_client)
        self.linker = Linker(model_name=config.model, skill_template=config.skill_template)
        self.reviser = Reviser(model_name=config.model, skill_template=config.skill_template, llm_client=llm_client, benchmark_constraints=benchmark_constraints)
        self.generator = Generator(model_name=config.model, skill_template=config.skill_template, llm_client=llm_client, duplication_similarity_threshold=config.duplication_similarity_threshold)
        self._fault_matcher = SemanticSkillMatcher(similarity_threshold=0.85, api_key=config.embedding_api_key, base_url=config.embedding_base_url, model_name=config.embedding_model)
        self._skill_matcher = SemanticSkillMatcher(similarity_threshold=config.skill_match_threshold, api_key=config.embedding_api_key, base_url=config.embedding_base_url, model_name=config.embedding_model)
        val_config = ValidationConfig(min_sample_size=config.min_sample_size, success_delta_threshold=config.success_delta_threshold, avg_score_delta_threshold=config.avg_score_delta_threshold, regression_threshold=config.regression_threshold)
        self.validator = Validator(val_config)
        self.skill_bank = SkillBankManager()
        self.iteration = 0
        self.consecutive_rejections = 0
        self.iteration_history: List[SkillAdaptorIteration] = []
        self.low_score_success_threshold = 0.6
        self._rejection_history: Dict[str, Dict[str, Any]] = {}
        self._rejection_history_path = config.output_dir / 'rejection_history.json'
        self._load_rejection_history()
        self.global_prior: str = ''
        self._prior_path = config.output_dir / 'global_prior.txt'
        self._load_global_prior()
        self._iteration_principles: List[str] = []
        self._reasoning_fault_count = 0
        self._program_registry = None
        if getattr(config, 'program_workspace', None):
            from runtime.program_registry import ProgramRegistry
            self._program_registry = ProgramRegistry(Path(config.program_workspace), git_branches=getattr(config, 'program_git_branches', False))
        config.create_directories()

    def run(self, training_tasks: List[str], validation_tasks: List[str], eval_func: Callable[[Dict[str, Skill]], Dict[str, Any]], initial_skill_bank: Optional[Dict[str, Skill]]=None) -> Dict[str, Any]:
        if initial_skill_bank:
            for skill in initial_skill_bank.values():
                self.skill_bank.add_skill(skill)
        self._initial_baseline_metrics: Optional[Dict[str, Any]] = None
        print('=' * 60)
        print('SkillAdaptor: Training-Free Skill Adaptation')
        print('=' * 60)
        print(f'Initial skills: {len(self.skill_bank)}')
        for s in self.skill_bank.list_skills():
            print(f'  - {s.id} v{s.version} (from {s.created_from or "seed"})')
        print(f'Training tasks: {len(training_tasks)}')
        print(f'Validation tasks: {len(validation_tasks)}')
        print()
        if validation_tasks:
            self._initial_baseline_metrics = self._establish_validation_baseline(eval_func, validation_tasks)
        print()
        while self.iteration < self.config.max_iterations:
            self.iteration += 1
            print(f"\n{'=' * 60}")
            print(f'Iteration {self.iteration}/{self.config.max_iterations}')
            print(f"{'=' * 60}")
            print('\n[1] Executing training tasks...')
            trajectories = self._execute_tasks(training_tasks)
            print(f'    Executed: {len(trajectories)} tasks')
            print('\n[2] Filtering failures...')
            failures = [t for t in trajectories if not t.success]
            low_score_successes = [t for t in trajectories if t.success and t.total_reward < self.low_score_success_threshold]
            issue_cases = failures + low_score_successes
            print(f'    Failed: {len(failures)}/{len(trajectories)}, Low-score successes: {len(low_score_successes)}')
            if not issue_cases:
                print('\nNo failures - convergence achieved!')
                break
            print('\n[5-7] Evolving skills (fault_chain retry, max 3 steps)...')
            accepted, revised_candidates, new_candidates = self._process_failures_with_chain_validation(issue_cases, validation_tasks, eval_func)
            print(f'\n[7] Results: {len(accepted)} accepted this iteration')
            if accepted:
                self.consecutive_rejections = 0
            else:
                self.consecutive_rejections += 1
            if self._iteration_principles:
                print('\n[6b] Validating global prior π candidate...')
                if self._try_adopt_global_prior(validation_tasks, eval_func):
                    print('      -> π ADOPTED')
                    self.consecutive_rejections = 0
                elif self._aggregate_prior_candidate():
                    print('      -> π REJECTED (keeping prior π)')
            self._record_iteration(failures=failures, revised=revised_candidates, generated=new_candidates, accepted=accepted)
            if self.consecutive_rejections >= self.config.k_reject_threshold:
                print(f"\n{'=' * 60}")
                print(f'CONVERGENCE: {self.config.k_reject_threshold} consecutive rejections')
                print(f"{'=' * 60}")
                break
        return self._generate_report()

    def _establish_validation_baseline(
        self,
        eval_func: Callable[..., Dict[str, Any]],
        validation_tasks: List[str],
    ) -> Dict[str, Any]:
        """Phase 0: evaluate initial bank B₀ on Q′ before any L→G→V (paper A/B anchor)."""
        bank = {s.id: s for s in self.skill_bank.list_skills()}
        print('[0] Baseline evaluation on Q′ (initial skill bank B₀, before evolution)...')
        try:
            metrics = eval_func(bank)
        except TypeError:
            metrics = eval_func(bank, baseline_metrics=None)
        scope_key = 'full'
        baseline_key = f'{self.validator._get_bank_key(bank)}:{scope_key}'
        self.validator._cached_baseline = metrics
        self.validator._cached_baseline_key = baseline_key
        sr = metrics.get('success_rate', 0.0)
        avg = metrics.get('avg_score', 0.0)
        n = metrics.get('sample_size', len(validation_tasks))
        print(f'    B₀ on Q′: success_rate={sr:.3f}, avg_score={avg:.3f}, n={n}')
        task_results = metrics.get('task_results') or {}
        if isinstance(task_results, dict):
            for tid in validation_tasks:
                tr = task_results.get(tid, {})
                if tr:
                    print(
                        f'      {tid}: score={float(tr.get("score", 0)):.2f} '
                        f'success={bool(tr.get("success", False))}'
                    )
        out_path = Path(self.config.output_dir) / 'baseline_metrics.json'
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                'phase': 'B0_validation',
                'skill_bank_ids': sorted(bank.keys()),
                'validation_tasks': list(validation_tasks),
                'metrics': {
                    'success_rate': sr,
                    'avg_score': avg,
                    'sample_size': n,
                    'task_results': task_results,
                },
                'timestamp': datetime.now().isoformat(),
            }
            out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'    Saved baseline → {out_path}')
        except OSError as exc:
            print(f'    WARN: could not save baseline_metrics.json: {exc}')
        return metrics

    def _execute_tasks(self, tasks: List[str], use_cache: bool=True) -> List[Trajectory]:
        trajectories: List[Trajectory] = []
        for task_id in tasks:
            trajectory = self._execute_single_task(task_id)
            if trajectory:
                trajectories.append(trajectory)
        return trajectories

    def _execute_single_task(self, task_id: str) -> Optional[Trajectory]:
        return None

    def _finalize_localized_fault(self, trajectory: Trajectory, fault: LocalizedFault) -> LocalizedFault:
        skill_dict = {s.id: s for s in self.skill_bank.list_skills()}
        coerced = coerce_cold_start_fault(fault, trajectory)
        if coerced.fault_type != fault.fault_type:
            print(
                f'      Fault coerce: {fault.fault_type.value} -> {coerced.fault_type.value} '
                '(no skill coverage for deliverable gap)'
            )
        fault = coerced
        before_repair = fault.fault_type
        fault = coerce_degraded_bank_fault(fault, trajectory, skill_dict)
        if fault.fault_type != before_repair:
            suspects = fault.skills_at_fault or ['?']
            print(
                f'      Fault coerce: {before_repair.value} -> {fault.fault_type.value} '
                f'(degraded bank → repair path, suspect={suspects[0]})'
            )
        return fault

    FAULT_CHAIN_MAX_ATTEMPTS = 3

    def _fault_at_chain_step(self, trajectory: Trajectory, base_fault: LocalizedFault, step_1based: int) -> Optional[LocalizedFault]:
        idx = step_1based - 1
        if idx < 0 or idx >= len(trajectory.steps):
            return None
        step = trajectory.steps[idx]
        fault = LocalizedFault(
            task_id=base_fault.task_id,
            step_index=idx,
            fault_type=base_fault.fault_type,
            observation=step.observation,
            wrong_action=step.action,
            skills_at_fault=list(step.skills_used),
            improvement_principle=base_fault.improvement_principle,
            fault_chain=base_fault.fault_chain,
            deliverable_targets=list(base_fault.deliverable_targets),
            wrong_artifact_note=base_fault.wrong_artifact_note,
            rubric_gap=base_fault.rubric_gap,
        )
        task_md = load_task_markdown(trajectory.task_id) or ''
        return refine_localized_fault(fault, trajectory, task_md)

    def _generate_candidates_for_fault(self, trajectory: Trajectory, fault: LocalizedFault) -> Tuple[List[Skill], List[Skill]]:
        revised_skills: List[Skill] = []
        new_skills: List[Skill] = []
        skill_dict = {s.id: s for s in self.skill_bank.list_skills()}
        reject_h = self._get_rejection_summaries_for_prompt()
        attributions = self.linker.attribute(fault, skill_dict, self.llm_client, skill_matcher=self._skill_matcher)
        if attributions:
            high_conf = self.linker.attributions_for_repair(
                fault, attributions, skill_dict, self.config.attribution_weight_threshold,
            )
            for attr in high_conf:
                skill = skill_dict.get(attr.skill_id)
                if skill:
                    print(
                        f'      [Repair] Reviser ← {attr.skill_id} v{skill.version} '
                        f'(weight={attr.weight:.2f})'
                    )
                    revised = self.reviser.revise(
                        skill, fault, attr, rejection_summaries=reject_h, trajectory=trajectory,
                    )
                    if revised and (not self._is_similar_to_rejected(revised)):
                        revised_skills.append(revised)
        else:
            print(f'      [Generate] No attribution (fault={fault.fault_type.value}) — new skill')
            new_skill = self.generator.generate(trajectory, fault, skill_dict, rejection_summaries=reject_h)
            if new_skill and (not self._is_similar_to_rejected(new_skill)):
                new_skills.append(new_skill)
                self._on_skill_generated(new_skill)
        return (revised_skills, new_skills)

    def _process_failures_with_chain_validation(self, failures: List[Trajectory], validation_tasks: List[str], eval_func: Callable[[Dict[str, Skill]], Dict[str, Any]]) -> Tuple[List[Skill], List[Skill], List[Skill]]:
        accepted_all: List[Skill] = []
        all_revised: List[Skill] = []
        all_new: List[Skill] = []
        print('\n[3] Localizing faults and attributing...')
        self._iteration_principles = []
        all_faults: List[Tuple[Trajectory, LocalizedFault]] = []
        for trajectory in failures:
            fault = self.localizer.localize(trajectory)
            if fault is not None:
                fault = self._finalize_localized_fault(trajectory, fault)
                all_faults.append((trajectory, fault))
        unique_faults = self._deduplicate_faults_by_embedding(all_faults)
        print(f'    Unique fault patterns: {len(unique_faults)}/{len(all_faults)}')
        for i, (trajectory, fault) in enumerate(unique_faults):
            print(f'    Processing fault {i + 1}/{len(unique_faults)}...')
            print(f'      Primary fault at step {fault.step_index + 1}: {fault.fault_type.value}')
            if fault.improvement_principle and fault.fault_type != FaultType.REASONING_WRONG:
                self._iteration_principles.append(fault.improvement_principle.strip())
            if fault.fault_type == FaultType.REASONING_WRONG:
                print('      -> REASONING_WRONG: Recording only, skipping skill modification')
                self._record_reasoning_fault(fault)
                continue
            chain_raw = fault.fault_chain or [fault.step_index + 1]
            chain = list(dict.fromkeys(chain_raw))[:self.FAULT_CHAIN_MAX_ATTEMPTS]
            if fault.fault_chain:
                print(f'      Fault chain (try up to {self.FAULT_CHAIN_MAX_ATTEMPTS}): {chain}')
            adopted_for_fault = False
            for attempt_idx, step_1based in enumerate(chain, start=1):
                attempt_fault = self._fault_at_chain_step(trajectory, fault, step_1based)
                if attempt_fault is None:
                    print(f'      Chain attempt {attempt_idx}: step {step_1based} out of range, skip')
                    continue
                print(f"      Chain attempt {attempt_idx}/{len(chain)} at step {step_1based} (S_{{t*}}={attempt_fault.skills_at_fault or '[]'})")
                revised, new = self._generate_candidates_for_fault(trajectory, attempt_fault)
                revised = self.skill_bank.deduplicate(revised)
                new = self.skill_bank.deduplicate(new)
                all_revised.extend(revised)
                all_new.extend(new)
                candidates = revised + new
                if not candidates:
                    print('      No candidates at this chain step, trying next...')
                    continue
                print(f'      Candidates: {len(revised)} revised, {len(new)} new — validating...')
                print('\n[6] Validating skill changes...')
                batch_accepted = self._validate_and_adopt(candidates, validation_tasks, eval_func)
                if batch_accepted:
                    accepted_all.extend(batch_accepted)
                    adopted_for_fault = True
                    print(f'      -> ADOPTED at chain step {step_1based}')
                    break
                print(f'      -> Validation failed at step {step_1based}, trying next fault_chain candidate...')
            if not adopted_for_fault:
                print('      -> No adoption after fault_chain attempts')
        return (accepted_all, all_revised, all_new)

    def _deduplicate_faults_by_embedding(self, faults: List[Tuple[Trajectory, LocalizedFault]]) -> List[Tuple[Trajectory, LocalizedFault]]:
        if not faults:
            return []
        fault_texts = []
        for _, fault in faults:
            text = f'{fault.fault_type.value}: {fault.observation[:100]} {fault.wrong_action}'
            fault_texts.append(text)
        unique_faults = []
        seen_indices = set()
        for i, (trajectory, fault) in enumerate(faults):
            if i in seen_indices:
                continue
            is_duplicate = False
            for j, (selected_traj, selected_fault) in enumerate(unique_faults):
                if fault.fault_type != selected_fault.fault_type:
                    continue
                similarity = self._compute_fault_similarity(fault, selected_fault)
                if similarity >= 0.85:
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique_faults.append((trajectory, fault))
        return unique_faults
    EMBEDDING_SIMILARITY_THRESHOLD = 0.85

    def _compute_fault_similarity(self, fault1: LocalizedFault, fault2: LocalizedFault) -> float:
        import numpy as np
        text1 = f'{fault1.fault_type.value}: {fault1.observation[:150]} {fault1.wrong_action}'
        text2 = f'{fault2.fault_type.value}: {fault2.observation[:150]} {fault2.wrong_action}'
        emb1 = self._fault_matcher.encode([text1])
        emb2 = self._fault_matcher.encode([text2])
        n1 = float(np.linalg.norm(emb1))
        n2 = float(np.linalg.norm(emb2))
        if n1 == 0.0 or n2 == 0.0:
            return 0.0
        return float(np.dot(emb1.flatten(), emb2.flatten()) / (n1 * n2))

    def _get_fault_pattern_key(self, fault: LocalizedFault) -> str:
        action_verb = 'unknown'
        if fault.wrong_action:
            action_lower = fault.wrong_action.lower()
            if 'click[' in action_lower:
                action_verb = 'click'
            elif 'search[' in action_lower:
                action_verb = 'search'
            elif 'type[' in action_lower:
                action_verb = 'type'
            elif 'buy[' in action_lower:
                action_verb = 'buy'
        skills_sig = ','.join(sorted(fault.skills_at_fault)) if fault.skills_at_fault else 'none'
        return f'{fault.fault_type.value}:{action_verb}:{skills_sig}'

    def _validate_and_adopt(self, candidates: List[Skill], validation_tasks: List[str], eval_func: Callable[[Dict[str, Skill]], Dict[str, Any]]) -> List[Skill]:
        accepted: List[Skill] = []
        original_skills = {s.id: s for s in self.skill_bank.list_skills()}
        evaluator = SimpleEvaluator(validation_tasks, eval_func)
        for skill in candidates:
            current_skills = {s.id: s for s in self.skill_bank.list_skills()}
            revised_bank = current_skills.copy()
            revised_bank[skill.id] = skill
            _sid = skill.id

            def full_eval(bank, baseline_metrics=None):
                try:
                    return eval_func(bank, baseline_metrics=baseline_metrics, candidate_skill_id=_sid)
                except TypeError:
                    return eval_func(bank)
            adopt_result = self.validator.validate(skill, current_skills, revised_bank, full_eval, scope_key='full')
            print(f'    {skill.id}:')
            revised_meta = adopt_result.revised_metrics or {}
            adoption_scope = list(revised_meta.get('adoption_scope') or [])
            if adoption_scope:
                n_total = len(revised_meta.get('scoped_tasks') or validation_tasks)
                print(f"      Validator (injected Q', n={adopt_result.sample_size}/{n_total} re-run): Δ_success={adopt_result.delta_success:+.3f}, Δ_avg={adopt_result.delta_avg_score:+.3f}, regression={adopt_result.regression_detected}")
            else:
                print(f"      Validator (full validation set Q', n={adopt_result.sample_size}): Δ_success={adopt_result.delta_success:+.3f}, Δ_avg={adopt_result.delta_avg_score:+.3f}, regression={adopt_result.regression_detected}")
            frozen = revised_meta.get('retrieval_frozen_tasks')
            if frozen:
                fr = revised_meta.get('frozen_regression', False)
                print(f"      [frozen] {len(frozen)} task(s) not re-run; no-regression constraint={'FAIL' if fr else 'ok'}")
            scoped_result = None
            if skill.created_from:
                from core.validation_metrics import source_result_from_full
                src_id = skill.created_from
                in_val = src_id in validation_tasks
                val_label = ' (held-out val)' if in_val else ' (train origin)'
                if src_id in adoption_scope:
                    scoped_result = source_result_from_full(adopt_result, src_id)
                    if scoped_result is not None:
                        print(f"      [source] task {src_id}{val_label} (same injected run): Δ_success={scoped_result.delta_success:+.3f}, Δ_avg={scoped_result.delta_avg_score:+.3f}, regression={scoped_result.regression_detected}")
                else:
                    scope_tasks = [src_id]

                    def scoped_eval(bank, baseline_metrics=None, _scope=scope_tasks):
                        try:
                            return eval_func(bank, scope_tasks=_scope, baseline_metrics=baseline_metrics, candidate_skill_id=_sid)
                        except TypeError:
                            try:
                                return eval_func(bank, scope_tasks=_scope)
                            except TypeError:
                                return eval_func(bank)
                    scoped_result = self.validator.validate(skill, current_skills, revised_bank, scoped_eval, scope_key=f'source_{scope_tasks[0]}')
                    print(f"      [source] task {src_id}{val_label} (extra run; not in injected scope): Δ_success={scoped_result.delta_success:+.3f}, Δ_avg={scoped_result.delta_avg_score:+.3f}, regression={scoped_result.regression_detected}")
                if scoped_result is not None:
                    print(f"      [source] advisory: {self.validator.source_gate_advisory(scoped_result)}")
            adopt_ok = self.validator.should_adopt(adopt_result)
            if adopt_ok:
                self.skill_bank.update_skill(skill)
                accepted.append(skill)
                print(f'      -> ADOPTED')
                self._on_skill_adopted(skill, adopt_result)
                try:
                    from runtime.evolution_audit import append_audit_record, build_validation_audit
                    append_audit_record(self.config.output_dir, build_validation_audit(skill_id=skill.id, created_from=getattr(skill, 'created_from', None), adopted=True, adopt_result=adopt_result, scoped_result=scoped_result))
                except OSError:
                    pass
                ckpt = self.config.output_dir / 'skill_bank_checkpoint.json'
                try:
                    self.skill_bank.save(ckpt)
                    print(f'      [checkpoint] {ckpt}')
                except OSError as e:
                    print(f'      [warn] checkpoint save failed: {e}')
            else:
                reason = f'Δ_success={adopt_result.delta_success:+.3f}, Δ_avg={adopt_result.delta_avg_score:+.3f}, regression={adopt_result.regression_detected}'
                val_feedback = self._validation_feedback_for_rejection(adopt_result, skill.created_from)
                self._record_rejection(skill, reason, validation_feedback=val_feedback)
                try:
                    from runtime.evolution_audit import append_audit_record, build_validation_audit
                    detail = self._rejection_detail(adopt_result, scoped_result)
                    append_audit_record(self.config.output_dir, build_validation_audit(skill_id=skill.id, created_from=getattr(skill, 'created_from', None), adopted=False, adopt_result=adopt_result, scoped_result=scoped_result, detail=detail))
                except OSError:
                    pass
                if adopt_result.regression_detected or adopt_result.delta_success < 0 or adopt_result.delta_avg_score < 0:
                    print('      -> HOLD_BASELINE (keeping prior bank; skill not adopted)')
                else:
                    detail = self._rejection_detail(adopt_result, scoped_result)
                    print(f'      -> REJECTED ({detail}; recorded in history H)')
        if len(accepted) > 1:
            print('\n    [Holistic Validation] Checking combined skill effects...')
            accepted = self._validate_holistic(accepted, original_skills, validation_tasks, eval_func)
        return accepted

    def _validate_holistic(self, accepted: List[Skill], original_skills: Dict[str, Skill], validation_tasks: List[str], eval_func: Callable[[Dict[str, Skill]], Dict[str, Any]]) -> List[Skill]:
        evaluator = SimpleEvaluator(validation_tasks, eval_func)
        final_skills = original_skills.copy()
        for skill in accepted:
            final_skills[skill.id] = skill
        original_metrics = evaluator.evaluate(original_skills)
        final_metrics = evaluator.evaluate(final_skills)
        delta_success = final_metrics.get('success_rate', 0) - original_metrics.get('success_rate', 0)
        delta_avg = final_metrics.get('avg_score', 0) - original_metrics.get('avg_score', 0)
        print(f'      Combined Δ_success: {delta_success:+.3f}')
        print(f'      Combined Δ_avg: {delta_avg:+.3f}')
        if delta_success < self.config.regression_threshold:
            print(f'      ⚠️  REGRESSION detected: success rate dropped')
            return self._rollback_skills(accepted, original_skills, validation_tasks, eval_func)
        if delta_avg < self.config.regression_threshold:
            print(f'      ⚠️  REGRESSION detected: avg score dropped')
            return self._rollback_skills(accepted, original_skills, validation_tasks, eval_func)
        print(f'      ✓ Holistic validation passed')
        return accepted

    def _rollback_skills(self, accepted: List[Skill], original_skills: Dict[str, Skill], validation_tasks: List[str], eval_func: Callable[[Dict[str, Skill]], Dict[str, Any]]) -> List[Skill]:
        evaluator = SimpleEvaluator(validation_tasks, eval_func)
        current_accepted = accepted.copy()
        for i, skill_to_remove in enumerate(reversed(accepted)):
            print(f'      Rollback: removing {skill_to_remove.id}')
            self._record_rejection(skill_to_remove, 'Holistic validation regression - rolled back')
            current_accepted = [s for s in current_accepted if s.id != skill_to_remove.id]
            test_bank = original_skills.copy()
            for s in current_accepted:
                test_bank[s.id] = s
            original_metrics = evaluator.evaluate(original_skills)
            test_metrics = evaluator.evaluate(test_bank)
            delta_success = test_metrics.get('success_rate', 0) - original_metrics.get('success_rate', 0)
            if delta_success >= self.config.regression_threshold:
                print(f'      ✓ Rollback successful, kept {len(current_accepted)} skills')
                removed_ids = set((s.id for s in accepted)) - set((s.id for s in current_accepted))
                for sid in removed_ids:
                    self.skill_bank.remove_skill(sid)
                return current_accepted
        print(f'      ⚠️  All {len(accepted)} skills rolled back')
        for skill in accepted:
            self._record_rejection(skill, 'Holistic validation - all skills rolled back')
        for skill in accepted:
            self.skill_bank.remove_skill(skill.id)
        return []

    def _record_iteration(self, failures: List[Trajectory], revised: List[Skill], generated: List[Skill], accepted: List[Skill]) -> None:
        record = SkillAdaptorIteration(iteration=self.iteration, failures=len(failures), revised=[s.id for s in revised], generated=[s.id for s in generated], accepted=[s.id for s in accepted], skill_count=len(self.skill_bank), timestamp=datetime.now().isoformat())
        self.iteration_history.append(record)

    def _generate_report(self) -> Dict[str, Any]:
        newly_adopted: List[str] = []
        seen_adopted: set[str] = set()
        for r in self.iteration_history:
            for sid in r.accepted:
                if sid not in seen_adopted:
                    seen_adopted.add(sid)
                    newly_adopted.append(sid)
        report = {'iterations': self.iteration, 'final_skill_count': len(self.skill_bank), 'newly_adopted_skill_ids': newly_adopted, 'consecutive_rejections': self.consecutive_rejections, 'history': [{'iteration': r.iteration, 'failures': r.failures, 'revised': r.revised, 'generated': r.generated, 'accepted': r.accepted, 'skill_count': r.skill_count, 'timestamp': r.timestamp} for r in self.iteration_history], 'skill_bank': self.skill_bank.to_dict()}
        report_path = self.config.output_dir / 'SkillAdaptor_report.json'
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n{'=' * 60}")
        print('SkillAdaptor Complete')
        print(f"{'=' * 60}")
        print(f'Total iterations: {self.iteration}')
        print(f'Final skill count: {len(self.skill_bank)}')
        print(f'Report saved: {report_path}')
        return report

    def save_skill_bank(self, path: Optional[Path]=None) -> Path:
        if path is None:
            path = self.config.output_dir / 'skill_bank_final.json'
        self.skill_bank.save(path)
        return path

    def load_skill_bank(self, path: Path) -> None:
        self.skill_bank.load(path)

    def _load_rejection_history(self) -> None:
        if self._rejection_history_path.exists():
            try:
                with open(self._rejection_history_path, 'r', encoding='utf-8') as f:
                    self._rejection_history = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._rejection_history = {}

    def _save_rejection_history(self) -> None:
        try:
            with open(self._rejection_history_path, 'w', encoding='utf-8') as f:
                json.dump(self._rejection_history, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f'Warning: Could not save rejection history: {e}')

    def _rejection_detail(self, result: ValidationResult, source_result: Optional[ValidationResult]=None) -> str:
        revised = result.revised_metrics or {}
        if revised.get('frozen_regression'):
            return 'frozen task(s) regressed (no-regression constraint)'
        required = self.config.min_sample_size
        if revised.get('adoption_scope'):
            required = max(1, min(required, len(revised['adoption_scope'])))
        if result.sample_size < required:
            return f'sample_size={result.sample_size} < min={required}'
        if result.regression_detected:
            scope = revised.get('adoption_scope')
            label = "injected Q'" if scope else "full validation set Q'"
            return f'regression on {label}'
        if result.delta_success < 0 or result.delta_avg_score < 0:
            return "injected Q' HOLD_BASELINE failed (Δ<0)" if revised.get('adoption_scope') else "full Q' HOLD_BASELINE failed (Δ<0)"
        return 'did not meet adoption criteria'

    def _aggregate_prior_candidate(self) -> str:
        if not self._iteration_principles:
            return ''
        seen: set[str] = set()
        for principle in self._iteration_principles:
            p = principle.strip()
            if p and p not in seen:
                seen.add(p)
                return p[:400]
        return self._iteration_principles[0][:400]

    def _load_global_prior(self) -> None:
        if self._prior_path.exists():
            try:
                self.global_prior = self._prior_path.read_text(encoding='utf-8').strip()
            except OSError:
                self.global_prior = ''

    def _save_global_prior(self) -> None:
        try:
            self._prior_path.parent.mkdir(parents=True, exist_ok=True)
            self._prior_path.write_text(self.global_prior, encoding='utf-8')
        except OSError as e:
            print(f'Warning: Could not save global prior: {e}')

    def _try_adopt_global_prior(self, validation_tasks: List[str], eval_func: Callable[[Dict[str, Skill]], Dict[str, Any]]) -> bool:
        candidate = self._aggregate_prior_candidate()
        if not candidate or candidate == self.global_prior.strip():
            return False
        bank = {s.id: s for s in self.skill_bank.list_skills()}
        baseline = eval_func(bank)
        old = self.global_prior
        self.global_prior = candidate
        try:
            revised = eval_func(bank)
        finally:
            self.global_prior = old
        delta_s = revised.get('success_rate', 0) - baseline.get('success_rate', 0)
        delta_a = revised.get('avg_score', 0) - baseline.get('avg_score', 0)
        sample = revised.get('sample_size', 0)
        print(f'      π Δ_success: {delta_s:+.3f}, Δ_avg: {delta_a:+.3f}, n={sample}')
        if sample < self.config.min_sample_size:
            return False
        if delta_s < 0 or delta_a < 0:
            return False
        if delta_s <= self.config.success_delta_threshold and delta_a <= self.config.avg_score_delta_threshold:
            return False
        self.global_prior = candidate
        self._save_global_prior()
        self.validator.clear_baseline_cache()
        return True

    def _validation_feedback_for_rejection(self, adopt_result: ValidationResult, source_task_id: Optional[str]) -> str:
        revised = adopt_result.revised_metrics or {}
        task_results = revised.get('task_results') or {}
        tid = source_task_id or ''
        tr = task_results.get(tid) if tid else {}
        if not tr and task_results:
            tid, tr = next(iter(task_results.items()))
        tail = str(tr.get('action_tail') or '').strip()
        score = tr.get('score', 0)
        ok = tr.get('success', False)
        parts = [f'post-inject Δ_success={adopt_result.delta_success:+.3f} Δ_avg={adopt_result.delta_avg_score:+.3f}']
        if tid:
            parts.append(f'task={tid} score={score:.2f} success={ok}')
        if tail:
            parts.append(f'agent_tail: {tail}')
        trace = str(tr.get('step_trace') or '').strip()
        if trace and trace != '(empty trajectory)':
            parts.append(f'step_trace: {trace[:420]}')
        hint = 'skill did not change verifier-visible behavior — tighten deliverable name, negative example from wrong_action, and rubric-shape verify'
        return '; '.join(parts) + f'; hint: {hint}'

    def _get_rejection_summaries_for_prompt(self, limit: int=5) -> List[str]:
        if not self._rejection_history:
            return []
        items = sorted(self._rejection_history.values(), key=lambda x: x.get('last_seen', ''), reverse=True)[:limit]
        summaries = []
        for info in items:
            title = info.get('skill_title', 'unknown')
            reason = info.get('reason', '')
            feedback = info.get('validation_feedback', '')
            line = f'- {title}: {reason}'
            if feedback:
                line += f' | after validation: {feedback[:280]}'
            summaries.append(line)
        return summaries

    def _on_skill_generated(self, skill: Skill) -> None:
        if not getattr(self.config, 'direct_skill_write', True):
            return
        root = getattr(self.config, 'skills_workspace_dir', None)
        if not root:
            return
        from runtime.skill_writer import write_skill_folder
        path = write_skill_folder(Path(root), skill, status='candidate')
        print(f'      [skill_dir] candidate → {path}')

    def _on_skill_adopted(self, skill: Skill, adopt_result: ValidationResult) -> None:
        if not getattr(self.config, 'direct_skill_write', True):
            return
        root = getattr(self.config, 'skills_workspace_dir', None)
        if root:
            from runtime.skill_writer import promote_candidate, write_skill_folder
            root_path = Path(root)
            promote_candidate(root_path, skill.id)
            path = write_skill_folder(root_path, skill, status='adopted')
            print(f'      [skill_dir] adopted → {path}')
        if self._program_registry:
            from runtime.program_registry import ProgramSnapshot
            snap = ProgramSnapshot(name=f'iter-{self.iteration}-adopt-{skill.id}', iteration=self.iteration, parent=f'iter-{self.iteration - 1}' if self.iteration > 0 else None, adopted_skill_ids=[skill.id], skill_count=len(self.skill_bank.list_skills()), delta_success=adopt_result.delta_success, delta_avg_score=adopt_result.delta_avg_score, benchmark=os.environ.get('SkillAdaptor_BENCHMARK_ENV', ''), harness=getattr(self.config, 'agent_harness', 'openclaw'))
            reg_path = self._program_registry.save_snapshot(snap)
            print(f'      [program] snapshot → {reg_path}')

    def _record_rejection(self, skill: Skill, reason: str, *, validation_feedback: str = '') -> None:
        signature = skill.body_sha256 or hashlib.sha256(skill.body.encode()).hexdigest()[:16]
        if signature in self._rejection_history:
            self._rejection_history[signature]['count'] += 1
            self._rejection_history[signature]['last_seen'] = datetime.now().isoformat()
            if validation_feedback:
                self._rejection_history[signature]['validation_feedback'] = validation_feedback
        else:
            entry = {
                'reason': reason,
                'count': 1,
                'first_seen': datetime.now().isoformat(),
                'last_seen': datetime.now().isoformat(),
                'skill_id': skill.id,
                'skill_title': skill.title,
                'skill_body_hash': skill.body_sha256,
            }
            if validation_feedback:
                entry['validation_feedback'] = validation_feedback
            self._rejection_history[signature] = entry
        self._save_rejection_history()

    def _is_similar_to_rejected(self, skill: Skill, threshold: float=0.85) -> bool:
        skill_hash = skill.body_sha256 or hashlib.sha256(skill.body.encode()).hexdigest()[:16]
        if skill_hash in self._rejection_history:
            return True
        skill_text = f'{skill.title} {skill.description} {skill.body}'.lower()
        skill_words = set(skill_text.split())
        for signature, info in self._rejection_history.items():
            stored_title = info.get('skill_title', '').lower()
            if stored_title:
                title_words = set(stored_title.split())
                if skill_words and title_words:
                    overlap = len(skill_words & title_words) / len(skill_words | title_words)
                    if overlap >= threshold:
                        return True
            stored_body_hash = info.get('skill_body_hash', '')
            if stored_body_hash and stored_body_hash == skill_hash:
                return True
        return False

    def _record_reasoning_fault(self, fault: LocalizedFault) -> None:
        self._reasoning_fault_count += 1
        reason_path = self.config.output_dir / 'reasoning_faults.log'
        try:
            with open(reason_path, 'a', encoding='utf-8') as f:
                f.write(f'{datetime.now().isoformat()} | Task: {fault.task_id} | Step: {fault.step_index} | Obs: {fault.observation[:80]}...\n')
        except IOError:
            pass
