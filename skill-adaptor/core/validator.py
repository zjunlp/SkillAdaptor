"""Skill Validation Module"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING
from .types import Skill, ValidationResult
from .validation_metrics import resolve_adoption_pair
if TYPE_CHECKING:
    from .config import SkillAdaptorConfig

@dataclass
class ValidationConfig:
    min_sample_size: int = 5
    success_delta_threshold: float = 0.05
    avg_score_delta_threshold: float = 0.05
    regression_threshold: float = -0.05
    random_seed: int = 42
    use_cached_baseline: bool = True

class Validator:

    def __init__(self, config: Optional[ValidationConfig]=None):
        self.config = config or ValidationConfig()
        self._cached_baseline: Optional[Dict[str, Any]] = None
        self._cached_baseline_key: Optional[str] = None

    def _get_bank_key(self, skill_bank: Dict[str, Skill]) -> str:
        skill_ids = sorted(skill_bank.keys())
        versions = [f'{sid}:{skill_bank[sid].version}' for sid in skill_ids]
        return str(hash(tuple(versions))) if versions else 'empty'

    def clear_baseline_cache(self) -> None:
        self._cached_baseline = None
        self._cached_baseline_key = None

    def validate(self, skill: Skill, original_skill_bank: Dict[str, Skill], revised_skill_bank: Dict[str, Skill], eval_func: Callable[[Dict[str, Skill]], Dict[str, Any]], scope_key: str='full') -> ValidationResult:
        import random
        random.seed(self.config.random_seed)
        baseline_key = f'{self._get_bank_key(original_skill_bank)}:{scope_key}'
        if self.config.use_cached_baseline and self._cached_baseline is not None and (self._cached_baseline_key == baseline_key):
            baseline_metrics = self._cached_baseline
        else:
            baseline_metrics = eval_func(original_skill_bank)
            if self.config.use_cached_baseline:
                self._cached_baseline = baseline_metrics
                self._cached_baseline_key = baseline_key
        random.seed(self.config.random_seed)
        try:
            revised_metrics = eval_func(revised_skill_bank, baseline_metrics=baseline_metrics)
        except TypeError:
            revised_metrics = eval_func(revised_skill_bank)
        baseline_adopt, revised_adopt, frozen_regression, adoption_scope = resolve_adoption_pair(baseline_metrics, revised_metrics)
        if adoption_scope:
            delta_success = revised_adopt.get('success_rate', 0) - baseline_adopt.get('success_rate', 0)
            delta_avg = revised_adopt.get('avg_score', 0) - baseline_adopt.get('avg_score', 0)
            sample_size = revised_adopt.get('sample_size', 0)
            regression = frozen_regression or delta_success < 0 or delta_avg < 0
            if not frozen_regression:
                regression = regression or self._detect_regression(baseline_adopt, revised_adopt)
        else:
            delta_success = revised_metrics.get('success_rate', 0) - baseline_metrics.get('success_rate', 0)
            delta_avg = revised_metrics.get('avg_score', 0) - baseline_metrics.get('avg_score', 0)
            sample_size = revised_metrics.get('sample_size', 0)
            regression = self._detect_regression(baseline_metrics, revised_metrics)
            if delta_success < 0 or delta_avg < 0:
                regression = True
            source_task = getattr(skill, 'created_from', None) or ''
            if source_task:
                base_tasks = baseline_metrics.get('task_results', {})
                rev_tasks = revised_metrics.get('task_results', {})
                if isinstance(base_tasks, dict) and isinstance(rev_tasks, dict):
                    bt = base_tasks.get(source_task)
                    rt = rev_tasks.get(source_task)
                    if bt and rt:
                        if bool(bt.get('success')) and (not bool(rt.get('success'))):
                            regression = True
                        if float(rt.get('score', 0.0)) < float(bt.get('score', 0.0)):
                            regression = True
        return ValidationResult(skill_id=skill.id, delta_success=delta_success, delta_avg_score=delta_avg, regression_detected=regression, sample_size=sample_size, baseline_metrics=baseline_metrics, revised_metrics=revised_metrics)

    def _detect_regression(self, baseline: Dict[str, Any], revised: Dict[str, Any]) -> bool:
        baseline_success = baseline.get('success_rate', 0)
        revised_success = revised.get('success_rate', 0)
        if revised_success - baseline_success < self.config.regression_threshold:
            return True
        baseline_avg = baseline.get('avg_score', 0)
        revised_avg = revised.get('avg_score', 0)
        if revised_avg - baseline_avg < self.config.regression_threshold:
            return True
        baseline_critical = baseline.get('critical_success_rate', 1.0)
        revised_critical = revised.get('critical_success_rate', 1.0)
        if revised_critical < baseline_critical:
            return True
        base_tasks = baseline.get('task_results', {})
        rev_tasks = revised.get('task_results', {})
        if isinstance(base_tasks, dict) and isinstance(rev_tasks, dict) and base_tasks:
            comparable = [k for k in base_tasks.keys() if k in rev_tasks]
            if comparable:
                regressed = 0
                for task_id in comparable:
                    b = base_tasks[task_id]
                    r = rev_tasks[task_id]
                    b_success = bool(b.get('success', False))
                    r_success = bool(r.get('success', False))
                    b_score = float(b.get('score', 0.0))
                    r_score = float(r.get('score', 0.0))
                    if b_success and (not r_success) or r_score < b_score - 0.1:
                        regressed += 1
                if regressed / len(comparable) > 0.1:
                    return True
        return False

    def _holds_baseline(self, result: ValidationResult, *, min_sample_size: Optional[int]=None) -> bool:
        required = min_sample_size if min_sample_size is not None else self.config.min_sample_size
        revised = result.revised_metrics or {}
        if revised.get('adoption_scope'):
            required = max(1, min(required, len(revised['adoption_scope'])))
        if result.sample_size < required:
            return False
        if result.regression_detected:
            return False
        if result.delta_success < 0 or result.delta_avg_score < 0:
            return False
        return True

    def _source_task_improved(self, result: ValidationResult) -> bool:
        return result.delta_success > 0 or result.delta_avg_score > 0

    def _aggregate_improved(self, result: ValidationResult) -> bool:
        return result.delta_success > self.config.success_delta_threshold or result.delta_avg_score > self.config.avg_score_delta_threshold

    def should_adopt(self, result: ValidationResult) -> bool:
        revised = result.revised_metrics or {}
        if revised.get('frozen_regression'):
            return False
        if not self._holds_baseline(result):
            return False
        return self._aggregate_improved(result)

    def source_gate_advisory(self, scoped_result: Optional[ValidationResult]) -> str:
        if scoped_result is None or scoped_result.sample_size < 1:
            return 'n/a (injected Q′ only)'
        if scoped_result.regression_detected:
            return 'source regressed vs baseline (diagnostic only)'
        if self._source_task_improved(scoped_result):
            return 'source strict improvement (diagnostic only)'
        return 'source no strict improvement (diagnostic only)'

    def should_adopt_with_source_gate(self, full_result: ValidationResult, scoped_result: Optional[ValidationResult], skill: Skill) -> bool:
        """Alias: adoption is injected Q′ only (scoped_result is diagnostic)."""
        return self.should_adopt(full_result)

    def should_adopt_with_gates(self, full_result: ValidationResult, source_result: ValidationResult, category_result: Optional[ValidationResult], skill: Skill) -> bool:
        return self.should_adopt(full_result)

    def batch_validate(self, skills: List[Skill], original_skill_bank: Dict[str, Skill], eval_func: Callable[[Dict[str, Skill]], Dict[str, Any]]) -> Dict[str, ValidationResult]:
        results = {}
        for skill in skills:
            revised_bank = original_skill_bank.copy()
            revised_bank[skill.id] = skill
            result = self.validate(skill, original_skill_bank, revised_bank, eval_func)
            results[skill.id] = result
        return results

    def aggregate_results(self, results: List[ValidationResult]) -> Dict[str, Any]:
        if not results:
            return {'total': 0, 'adopted': 0, 'rejected': 0, 'regressions': 0, 'avg_delta_success': 0, 'avg_delta_avg': 0}
        adopted = sum((1 for r in results if self.should_adopt(r)))
        regressions = sum((1 for r in results if r.regression_detected))
        return {'total': len(results), 'adopted': adopted, 'rejected': len(results) - adopted, 'regressions': regressions, 'avg_delta_success': sum((r.delta_success for r in results)) / len(results), 'avg_delta_avg': sum((r.delta_avg_score for r in results)) / len(results)}

class SimpleEvaluator:

    def __init__(self, tasks: List[str], eval_func: Optional[Callable[[Dict[str, Skill]], Dict[str, Any]]]=None):
        self.tasks = tasks
        self.eval_func = eval_func
        if self.eval_func is None:
            raise ValueError('SimpleEvaluator requires a real eval_func; mock evaluation is disabled in production.')

    def evaluate(self, skill_bank: Dict[str, Skill]) -> Dict[str, Any]:
        return self.eval_func(skill_bank)
