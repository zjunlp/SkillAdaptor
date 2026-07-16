#!/usr/bin/env python3
"""Main SkillAdaptor Runner"""

import argparse
import os
import random
import sys
from pathlib import Path
from typing import List, Optional
sys.path.insert(0, str(Path(__file__).parent))
from core.config import load_config
from core.provider_config import resolve_and_apply, sync_config_from_profile, describe_profile
from core.llm_factory import build_openai_client
from core.orchestrator import SkillAdaptorOrchestrator
from core.types import Step, Trajectory
from adapters.pinchbench_adapter import PinchBenchExecutor, PinchBenchPolicyAdapter
from adapters.webshop_adapter import WebShopEnvWrapper, WebShopEvaluator, SkillAugmentedLLMPolicy
from runtime.harness import get_harness

def parse_args():
    parser = argparse.ArgumentParser(description='Run SkillAdaptor Training-Free Skill Evolution')
    parser.add_argument('--env', choices=['webshop', 'pinchbench', 'claw-eval'], default='webshop', help='Environment to run on')
    parser.add_argument('--provider', default=None, help='LLM backend: auto (default), deepseek, openrouter')
    parser.add_argument('--model', type=str, default=None, help='Specific model name (overrides default)')
    parser.add_argument('--max-iterations', type=int, default=10, help='Maximum SkillAdaptor iterations')
    parser.add_argument('--training-size', type=int, default=500, help='Number of training examples')
    parser.add_argument('--validation-size', type=int, default=100, help='Number of validation examples')
    parser.add_argument('--output', type=str, default='./results', help='Output directory')
    parser.add_argument('--skills', type=str, default=None, help='Initial skill bank JSON file')
    parser.add_argument('--skill-template', choices=['standard', 'enhanced', 'concise'], default='enhanced', help='Skill format profile (standard=verbose, enhanced=balanced, concise=minimal)')
    parser.add_argument('--test', action='store_true', help='Run in test mode (fewer iterations)')
    parser.add_argument('--task-manifest', type=str, default=None, help='JSON manifest with input_tasks / validation_tasks / test_tasks lists')
    return parser.parse_args()

def load_task_manifest(path: str | Path) -> dict:
    import json
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    for key in ('input_tasks', 'validation_tasks', 'test_tasks'):
        if key not in data:
            data[key] = []
    return data

from core.validation_metrics import metrics_from_task_results as _metrics_from_task_results_impl
from core.skill_body_utils import pinchbench_deliverable_banner, summarize_trajectory_actions, format_trajectory_steps_for_analysis

def _deliverable_banner_text(policy_adapter, task_id: str, tasks_dir) -> str:
    return policy_adapter.build_combined_skill_text(
        [],
        task_id=task_id,
        tasks_dir=tasks_dir,
    )

def configure_pinchbench_skill_injection(executor, policy_adapter, task_ids, skill_bank, *, tasks_dir, template: str, model: str, global_prior: str='', embedding_api_key: str='', embedding_base_url: str='', embedding_model: str='', step_top_k: int=3) -> int:
    if not skill_bank and (not global_prior.strip()):
        banner_texts: dict = {}
        for task_id in task_ids:
            text = _deliverable_banner_text(policy_adapter, task_id, tasks_dir)
            if text.strip():
                banner_texts[task_id] = text
        if banner_texts:
            executor.set_task_skills(banner_texts, {tid: [] for tid in banner_texts}, {})
            from runtime.execution_binding import build_prompt_prefix_map

            prefixes = build_prompt_prefix_map(
                list(banner_texts.keys()),
                tasks_dir=tasks_dir,
                task_to_skill_body={},
                allow_task_derivation=True,
            )
            executor.set_task_prompt_prefixes(prefixes)
            print(f'    [Inject] deliverable banners only for {len(banner_texts)} task(s)')
            return len(banner_texts)
        executor.clear_task_skills()
        return 0
    executor.set_skill_bank(skill_bank, top_k=step_top_k, api_key=embedding_api_key or None, base_url=embedding_base_url or None, embedding_model=embedding_model or None)
    task_to_skills = policy_adapter.map_tasks_to_skills(task_ids, skill_bank, tasks_dir=tasks_dir) if skill_bank else {tid: [] for tid in task_ids}
    if skill_bank:
        audit = policy_adapter.map_tasks_to_skills_with_scores(task_ids, skill_bank, tasks_dir=tasks_dir)
        for tid in task_ids:
            entries = audit.get(tid, [])
            if entries:
                detail = ', '.join((f'{s.id}({score:.2f},{reason})' for s, score, reason in entries))
                print(f'    [Retrieve] {tid} <- {detail}')
            else:
                print(f'    [Retrieve] {tid} <- (none)')
    skill_texts: dict = {}
    task_skill_ids: dict = {}
    task_skill_objects: dict = {}
    for task_id in task_ids:
        skills = task_to_skills.get(task_id, [])
        if not skills and (not global_prior.strip()):
            banner_only = _deliverable_banner_text(policy_adapter, task_id, tasks_dir)
            if banner_only.strip():
                skill_texts[task_id] = banner_only
                task_skill_ids[task_id] = []
                task_skill_objects[task_id] = {}
            continue
        skill_texts[task_id] = policy_adapter.build_combined_skill_text(
            skills,
            template=template,
            model=model,
            global_prior=global_prior,
            task_id=task_id,
            tasks_dir=tasks_dir,
        )
        task_skill_ids[task_id] = [s.id for s in skills]
        task_skill_objects[task_id] = {s.id: s for s in skills}
    from runtime.execution_binding import build_prompt_prefix_map

    bodies = {
        tid: (task_to_skills.get(tid) or [None])[0].body if task_to_skills.get(tid) else ''
        for tid in task_ids
    }
    prompt_prefixes = build_prompt_prefix_map(
        task_ids,
        tasks_dir=tasks_dir,
        task_to_skill_body=bodies,
        allow_task_derivation=False,
    )
    executor.set_task_skills(skill_texts, task_skill_ids, task_skill_objects)
    executor.set_task_prompt_prefixes(prompt_prefixes)
    return len(skill_texts)

def _task_result_from_trajectory(t) -> dict:
    step_trace = format_trajectory_steps_for_analysis(t, max_steps=12, action_chars=160)
    tail = summarize_trajectory_actions(t, max_steps=4)
    return {
        'success': t.success,
        'score': t.total_reward,
        'action_tail': tail,
        'step_trace': step_trace,
    }

def _metrics_from_task_results(task_ids: list[str], task_results: dict) -> dict:
    return _metrics_from_task_results_impl(list(task_ids), task_results)

def evaluate_pinchbench_bank(executor, policy_adapter, validation_tasks, skill_bank, *, tasks_dir, template: str, model: str, scope_tasks: Optional[List[str]]=None, global_prior: str='', embedding_api_key: str='', embedding_base_url: str='', embedding_model: str='', candidate_skill_id: Optional[str]=None, baseline_metrics: Optional[dict]=None) -> dict:
    tasks = list(scope_tasks) if scope_tasks else list(validation_tasks)
    retrieval_hits: set[str] = set()
    if candidate_skill_id and skill_bank:
        retrieval_hits = policy_adapter.tasks_receiving_skill(tasks, skill_bank, candidate_skill_id, tasks_dir=tasks_dir)
    freeze_unrelated = candidate_skill_id is not None and baseline_metrics is not None and isinstance(baseline_metrics.get('task_results'), dict)
    rerun_tasks = list(retrieval_hits) if freeze_unrelated else tasks
    if freeze_unrelated and (not rerun_tasks):
        base_tr = baseline_metrics.get('task_results', {})
        merged = _metrics_from_task_results(tasks, base_tr)
        merged['scoped_tasks'] = tasks
        merged['retrieval_frozen_tasks'] = tasks
        merged['adoption_scope'] = []
        merged['frozen_regression'] = False
        print(f'    [Validate] retrieval freeze: {len(tasks)} task(s) unchanged (skill {candidate_skill_id} not injected on val)')
        return merged
    injected = configure_pinchbench_skill_injection(executor, policy_adapter, rerun_tasks if freeze_unrelated else tasks, skill_bank, tasks_dir=tasks_dir, template=template, model=model, global_prior=global_prior, embedding_api_key=embedding_api_key, embedding_base_url=embedding_base_url, embedding_model=embedding_model)
    if injected:
        label = f'scoped {len(tasks)}' if scope_tasks else str(len(tasks))
        print(f'    [Validate] Injected skills for {injected} task(s) on {label} validation task(s)')
    if freeze_unrelated:
        frozen = [t for t in tasks if t not in retrieval_hits]
        if frozen:
            print(f'    [Validate] retrieval freeze: {len(frozen)} unrelated task(s) keep baseline scores (no re-run with candidate)')
    trajectories = executor.execute_tasks(rerun_tasks if freeze_unrelated else tasks, model=model)
    if freeze_unrelated:
        base_tr = dict(baseline_metrics.get('task_results', {}))
        revised_tr = dict(base_tr)
        for t in trajectories:
            revised_tr[t.task_id] = _task_result_from_trajectory(t)
        frozen = [t for t in tasks if t not in retrieval_hits]
        injection = list(rerun_tasks)
        merged = _metrics_from_task_results(tasks, revised_tr)
        merged['scoped_tasks'] = tasks
        merged['retrieval_frozen_tasks'] = frozen
        merged['retrieval_rerun_tasks'] = injection
        merged['adoption_scope'] = injection
        from core.validation_metrics import frozen_tasks_regressed
        merged['frozen_regression'] = frozen_tasks_regressed(frozen, base_tr, revised_tr) if frozen else False
        adopt_b = _metrics_from_task_results(injection, base_tr)
        adopt_r = _metrics_from_task_results(injection, revised_tr)
        if injection:
            print(
                f"    [Validate] injected Q' n={len(injection)}/{len(tasks)}: "
                f"Δ_success={adopt_r.get('success_rate', 0) - adopt_b.get('success_rate', 0):+.3f}, "
                f"Δ_avg={adopt_r.get('avg_score', 0) - adopt_b.get('avg_score', 0):+.3f}"
            )
        if frozen:
            fr = 'FAIL' if merged['frozen_regression'] else 'ok'
            print(f'    [Validate] frozen {len(frozen)} task(s) regression check: {fr}')
        return merged
    if not trajectories:
        raise RuntimeError(f'PinchBench validation produced no trajectories for tasks={tasks!r}. Refusing silent zero metrics (check executor / gateway).')
    success_count = sum((1 for t in trajectories if t.success))
    total_score = sum((t.total_reward for t in trajectories))
    return {'success_rate': success_count / len(trajectories), 'avg_score': total_score / len(trajectories), 'sample_size': len(trajectories), 'task_results': {t.task_id: _task_result_from_trajectory(t) for t in trajectories}, 'scoped_tasks': tasks}

def run_claw_eval(args, config):
    from core.openclaw_hygiene import ensure_gateway_running
    from adapters.claw_eval_adapter.executor import ClawEvalExecutor
    from adapters.claw_eval_adapter.hints import install_claw_eval_hints
    from adapters.claw_eval_adapter.task_context import install_claw_eval_task_context
    from adapters.claw_eval_adapter.config_patch import ClawEvalConfig
    from adapters.claw_eval_adapter.generator_patch import ClawEvalGenerator
    from adapters.claw_eval_adapter.constraint_provider import ClawEvalConstraintProvider

    install_claw_eval_hints()
    print('\n' + '=' * 60)
    print('SkillAdaptor - Claw-Eval Environment')
    print('=' * 60)
    ok, probe_out = ensure_gateway_running()
    if not ok:
        raise RuntimeError(f'OpenClaw Gateway unreachable. Start it before Claw-Eval runs.\nLast probe:\n{probe_out}')
    print('[Setup] OpenClaw Gateway reachable')
    claw_eval_path = os.environ.get('CLAW_EVAL_PATH')
    if not claw_eval_path:
        raise ValueError('CLAW_EVAL_PATH is required for Claw-Eval execution')
    from adapters.claw_eval_adapter.official_config import OFFICIAL_JUDGE_MODEL, resolve_official_judge, allow_nonofficial_judge
    judge_cfg, judge_warns = resolve_official_judge(
        agent_api_key=config.api_key,
        agent_base_url=config.base_url,
    )
    print(f'[Setup] Official judge model_id={judge_cfg.get("model_id")} (locked={OFFICIAL_JUDGE_MODEL})')
    for w in judge_warns:
        print(f'[Setup] judge: {w}')
    if judge_cfg.get('model_id') != OFFICIAL_JUDGE_MODEL:
        if not allow_nonofficial_judge():
            raise ValueError(
                f'Judge model_id={judge_cfg.get("model_id")} is not official '
                f'{OFFICIAL_JUDGE_MODEL}. Submitted runs require official judge. '
                'Local wiring: python -m adapters.claw_eval_adapter.wiring_judge'
            )
        print(
            f'[Setup] WARNING: non-official judge (wiring only) — not paper-comparable'
        )
    if not judge_cfg.get('api_key'):
        raise ValueError(
            'Claw-Eval official judge needs CLAW_EVAL_JUDGE_API_KEY + CLAW_EVAL_JUDGE_BASE_URL '
            f'(or OPENROUTER_API_KEY) serving {OFFICIAL_JUDGE_MODEL}'
        )
    tasks_dir = os.environ.get('CLAW_EVAL_TASKS_DIR', 'tasks')
    install_claw_eval_task_context(claw_eval_path, tasks_dir)
    results_dir = os.environ.get('CLAW_EVAL_RESULTS_DIR', 'results')
    artifact_dir = config.artifact_dir
    # Claw-Eval adoption thresholds (lower initial deltas); keep all other base config fields.
    config = ClawEvalConfig.from_base(config)
    llm_client = build_openai_client(config)
    harness = get_harness(getattr(config, 'agent_harness', None), project_root=Path(claw_eval_path))
    executor = ClawEvalExecutor(
        claw_eval_path=claw_eval_path,
        python_cmd=os.environ.get('CLAW_EVAL_PYTHON') or os.environ.get('PINCHBENCH_PYTHON'),
        tasks_dir=tasks_dir,
        results_dir=results_dir,
        artifact_dir=artifact_dir,
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
        harness=harness,
    )
    all_tasks = executor.list_tasks()
    if not all_tasks:
        raise ValueError('No Claw-Eval tasks found. Check CLAW_EVAL_PATH and CLAW_EVAL_TASKS_DIR.')
    if args.task_manifest:
        manifest = load_task_manifest(args.task_manifest)
        training_tasks = list(manifest.get('input_tasks') or [])
        validation_tasks = list(manifest.get('validation_tasks') or [])
        test_tasks = list(manifest.get('test_tasks') or [])
        if not training_tasks:
            raise ValueError('task manifest must include non-empty input_tasks')
        if not validation_tasks:
            validation_tasks = training_tasks[:1]
        print(f'[Setup] Task manifest: {args.task_manifest}')
        print(f'[Setup] input_tasks: {len(training_tasks)}')
        print(f'[Setup] validation_tasks: {len(validation_tasks)}')
        print(f'[Setup] test_tasks: {len(test_tasks)}')
    else:
        raise ValueError('Claw-Eval runs require --task-manifest')
    overlap = set(training_tasks) & set(validation_tasks)
    if overlap and (not manifest.get('allow_train_val_overlap')):
        raise ValueError(f'Data leakage detected: {sorted(overlap)}')
    ce_tasks_root = executor.tasks_dir
    os.environ['SkillAdaptor_BENCHMARK_ENV'] = 'claw-eval'
    from runtime.retrieval_index import build_retrieval_index
    retrieval_index = build_retrieval_index(manifest, tasks_dir=ce_tasks_root, config=config)
    if retrieval_index.labels:
        print('[Setup] Retrieval index (manifest + task category):')
        for tid in sorted(retrieval_index.labels.keys())[:12]:
            lab = retrieval_index.labels[tid]
            print(f'  {tid}: category={lab.category} tags={lab.tags}')
    policy_adapter = PinchBenchPolicyAdapter(
        artifact_dir,
        api_key=config.embedding_api_key,
        base_url=config.embedding_base_url,
        embedding_model=config.embedding_model,
        similarity_threshold=config.skill_match_threshold,
        cross_task_threshold=config.cross_task_match_threshold,
        retrieval_index=retrieval_index,
        llm_client=llm_client,
        llm_model=config.model,
    )
    initial_bank = None
    if args.skills:
        print(f'[Setup] Loading skills from {args.skills}')
        from core.skill_bank import SkillBankManager
        manager = SkillBankManager()
        manager.load(args.skills)
        initial_bank = {s.id: s for s in manager.list_skills()}

    def _task_category(task_id: str) -> str:
        return retrieval_index.category_of(task_id, ce_tasks_root)

    def eval_skill_bank(skill_bank, scope_tasks: Optional[List[str]]=None, baseline_metrics=None, candidate_skill_id: Optional[str]=None):
        return evaluate_pinchbench_bank(
            executor,
            policy_adapter,
            validation_tasks,
            skill_bank,
            tasks_dir=executor.tasks_dir,
            template=args.skill_template,
            model=config.model,
            scope_tasks=scope_tasks,
            global_prior=orchestrator.global_prior,
            embedding_api_key=config.embedding_api_key,
            embedding_base_url=config.embedding_base_url,
            embedding_model=config.embedding_model,
            candidate_skill_id=candidate_skill_id,
            baseline_metrics=baseline_metrics,
        )

    orchestrator = SkillAdaptorOrchestrator(
        config,
        llm_client=llm_client,
        benchmark_constraints=ClawEvalConstraintProvider.get_constraints(),
        task_category_fn=_task_category,
    )
    orchestrator.generator = ClawEvalGenerator(
        model_name=config.model,
        skill_template=args.skill_template,
        llm_client=llm_client,
        duplication_similarity_threshold=config.duplication_similarity_threshold,
    )
    print('[Setup] Injected Claw-Eval benchmark constraints + ClawEvalGenerator')

    def execute_tasks_with_current_skills(tasks, use_cache=False, **kwargs):
        current_bank = {s.id: s for s in orchestrator.skill_bank.list_skills()}
        injected = configure_pinchbench_skill_injection(
            executor,
            policy_adapter,
            tasks,
            current_bank,
            tasks_dir=executor.tasks_dir,
            template=args.skill_template,
            model=config.model,
            global_prior=orchestrator.global_prior,
            embedding_api_key=config.embedding_api_key,
            embedding_base_url=config.embedding_base_url,
            embedding_model=config.embedding_model,
        )
        if injected:
            print(f'    [Skills] Configured for {injected} task(s) (with step-by-step tracking)')
        return executor.execute_tasks(tasks, model=config.model)

    orchestrator._execute_tasks = execute_tasks_with_current_skills
    print('\n[Run] Starting SkillAdaptor...')
    result = orchestrator.run(
        training_tasks=training_tasks,
        validation_tasks=validation_tasks,
        eval_func=eval_skill_bank,
        initial_skill_bank=initial_bank,
    )
    print('\n[Save] Saving results...')
    orchestrator.save_skill_bank()
    if test_tasks:
        final_bank = {s.id: s for s in orchestrator.skill_bank.list_skills()}
        injected = configure_pinchbench_skill_injection(
            executor,
            policy_adapter,
            test_tasks,
            final_bank,
            tasks_dir=executor.tasks_dir,
            template=args.skill_template,
            model=config.model,
            global_prior=orchestrator.global_prior,
            embedding_api_key=config.embedding_api_key,
            embedding_base_url=config.embedding_base_url,
            embedding_model=config.embedding_model,
        )
        print(f'[Held-out Test] Injected skills for {injected} tasks')
        trajectories = executor.execute_tasks(test_tasks, model=config.model)
        if trajectories:
            success_count = sum((1 for t in trajectories if t.success))
            total_score = sum((t.total_reward for t in trajectories))
            result['held_out_test'] = {
                'success_rate': success_count / len(trajectories),
                'avg_score': total_score / len(trajectories),
                'sample_size': len(trajectories),
                'task_results': {t.task_id: {'success': t.success, 'score': t.total_reward} for t in trajectories},
            }
        else:
            result['held_out_test'] = {'success_rate': 0.0, 'avg_score': 0.0, 'sample_size': 0}
        print(
            f"[Test] Held-out test metrics: success_rate={result['held_out_test'].get('success_rate', 0.0):.3f}, "
            f"avg_score={result['held_out_test'].get('avg_score', 0.0):.3f}, "
            f"sample_size={result['held_out_test'].get('sample_size', 0)}"
        )
    else:
        result['held_out_test'] = {'success_rate': 0.0, 'avg_score': 0.0, 'sample_size': 0}
    return result

def run_workspace(args, config):
    from core.adapter_hints import activate_benchmark_hints
    from runtime.workspace_executor import WorkspaceExecutor

    activate_benchmark_hints('generic')
    print('\n' + '=' * 60)
    print('SkillAdaptor - Workspace Plugin Environment')
    print('=' * 60)
    os.environ['SkillAdaptor_BENCHMARK_ENV'] = 'workspace'
    workspace = getattr(config, 'program_workspace', None)
    if not workspace:
        raise ValueError('Workspace path missing on config.program_workspace')
    workspace = Path(workspace)
    artifact_dir = config.artifact_dir
    llm_client = build_openai_client(config)
    harness = get_harness(getattr(config, 'agent_harness', None), project_root=workspace)
    executor = WorkspaceExecutor(
        workspace,
        artifact_dir=artifact_dir,
        harness_name=getattr(config, 'agent_harness', None) or 'openclaw',
        harness=harness,
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
    )
    all_tasks = executor.list_tasks()
    if not all_tasks:
        raise ValueError(f'No workspace tasks in {workspace / "input_task"}. Add *.md briefs.')
    if not args.task_manifest:
        raise ValueError('Workspace runs require --task-manifest')
    manifest_data = load_task_manifest(args.task_manifest)
    training_tasks = list(manifest_data.get('input_tasks') or [])
    validation_tasks = list(manifest_data.get('validation_tasks') or [])
    test_tasks = list(manifest_data.get('test_tasks') or [])
    if not training_tasks:
        raise ValueError('task manifest must include non-empty input_tasks')
    if not validation_tasks:
        validation_tasks = training_tasks[:1]
    print(f'[Setup] Task manifest: {args.task_manifest}')
    print(f'[Setup] input_tasks: {len(training_tasks)}')
    print(f'[Setup] validation_tasks: {len(validation_tasks)}')
    print(f'[Setup] test_tasks: {len(test_tasks)}')
    overlap = set(training_tasks) & set(validation_tasks)
    if overlap and (not manifest_data.get('allow_train_val_overlap')):
        raise ValueError(f'Data leakage detected: {sorted(overlap)}')
    ws_tasks_root = executor.tasks_dir
    from runtime.retrieval_index import build_retrieval_index
    retrieval_index = build_retrieval_index(manifest_data, tasks_dir=ws_tasks_root, config=config)
    policy_adapter = PinchBenchPolicyAdapter(
        artifact_dir,
        api_key=config.embedding_api_key,
        base_url=config.embedding_base_url,
        embedding_model=config.embedding_model,
        similarity_threshold=config.skill_match_threshold,
        cross_task_threshold=config.cross_task_match_threshold,
        retrieval_index=retrieval_index,
        llm_client=llm_client,
        llm_model=config.model,
    )

    def _task_category(task_id: str) -> str:
        return retrieval_index.category_of(task_id, ws_tasks_root)

    orchestrator = SkillAdaptorOrchestrator(
        config,
        llm_client=llm_client,
        benchmark_constraints=policy_adapter.get_revision_constraints(),
        task_category_fn=_task_category,
    )
    print('[Setup] Workspace executor with generic adapter hints')

    def eval_skill_bank(skill_bank, scope_tasks: Optional[List[str]]=None, baseline_metrics=None, candidate_skill_id: Optional[str]=None):
        return evaluate_pinchbench_bank(
            executor,
            policy_adapter,
            validation_tasks,
            skill_bank,
            tasks_dir=executor.tasks_dir,
            template=args.skill_template,
            model=config.model,
            scope_tasks=scope_tasks,
            global_prior=orchestrator.global_prior,
            embedding_api_key=config.embedding_api_key,
            embedding_base_url=config.embedding_base_url,
            embedding_model=config.embedding_model,
            candidate_skill_id=candidate_skill_id,
            baseline_metrics=baseline_metrics,
        )

    def execute_tasks_with_current_skills(tasks, use_cache=False, **kwargs):
        current_bank = {s.id: s for s in orchestrator.skill_bank.list_skills()}
        injected = configure_pinchbench_skill_injection(
            executor,
            policy_adapter,
            tasks,
            current_bank,
            tasks_dir=executor.tasks_dir,
            template=args.skill_template,
            model=config.model,
            global_prior=orchestrator.global_prior,
            embedding_api_key=config.embedding_api_key,
            embedding_base_url=config.embedding_base_url,
            embedding_model=config.embedding_model,
        )
        if injected:
            print(f'    [Skills] Configured for {injected} task(s)')
        return executor.execute_tasks(tasks, model=config.model)

    orchestrator._execute_tasks = execute_tasks_with_current_skills
    print('\n[Run] Starting SkillAdaptor...')
    result = orchestrator.run(
        training_tasks=training_tasks,
        validation_tasks=validation_tasks,
        eval_func=eval_skill_bank,
        initial_skill_bank=None,
    )
    print('\n[Save] Saving results...')
    orchestrator.save_skill_bank()
    if test_tasks:
        final_bank = {s.id: s for s in orchestrator.skill_bank.list_skills()}
        injected = configure_pinchbench_skill_injection(
            executor,
            policy_adapter,
            test_tasks,
            final_bank,
            tasks_dir=executor.tasks_dir,
            template=args.skill_template,
            model=config.model,
            global_prior=orchestrator.global_prior,
            embedding_api_key=config.embedding_api_key,
            embedding_base_url=config.embedding_base_url,
            embedding_model=config.embedding_model,
        )
        print(f'[Held-out Test] Injected skills for {injected} tasks')
        trajectories = executor.execute_tasks(test_tasks, model=config.model)
        if trajectories:
            success_count = sum((1 for t in trajectories if t.success))
            total_score = sum((t.total_reward for t in trajectories))
            result['held_out_test'] = {
                'success_rate': success_count / len(trajectories),
                'avg_score': total_score / len(trajectories),
                'sample_size': len(trajectories),
                'task_results': {t.task_id: {'success': t.success, 'score': t.total_reward} for t in trajectories},
            }
        else:
            result['held_out_test'] = {'success_rate': 0.0, 'avg_score': 0.0, 'sample_size': 0}
        print(
            f"[Test] Held-out test metrics: success_rate={result['held_out_test'].get('success_rate', 0.0):.3f}, "
            f"avg_score={result['held_out_test'].get('avg_score', 0.0):.3f}, "
            f"sample_size={result['held_out_test'].get('sample_size', 0)}"
        )
    else:
        result['held_out_test'] = {'success_rate': 0.0, 'avg_score': 0.0, 'sample_size': 0}
    return result

def setup_config(args):
    profile = resolve_and_apply(getattr(args, 'provider', None), getattr(args, 'model', None))
    config = load_config(use_env=True)
    sync_config_from_profile(config, profile)
    config.max_iterations = args.max_iterations
    config.output_dir = Path(args.output)
    config.results_dir = Path(args.output) / args.env
    config.skill_template = args.skill_template
    if not config.api_key:
        raise ValueError('Missing API key. Set SkillAdaptor_API_KEY in secrets/.env')
    config.create_directories()
    config._llm_profile = profile  # type: ignore[attr-defined]
    return config

def build_webshop_splits(goal_count, training_size, validation_size):
    train_start, train_end = (1500, 12086)
    eval_start, eval_end = (500, 1499)
    train_upper = min(train_start + training_size, train_end + 1, goal_count)
    eval_upper = min(eval_start + validation_size, eval_end + 1, goal_count)
    training_goals = list(range(train_start, train_upper))
    validation_goals = list(range(eval_start, eval_upper))
    return (training_goals, validation_goals)

def build_webshop_test_split(goal_count):
    test_start, test_end = (0, 499)
    test_upper = min(test_end + 1, goal_count)
    return list(range(test_start, test_upper))

def run_webshop(args, config):
    from adapters.webshop_adapter.hints import install_webshop_hints
    install_webshop_hints()
    print('\n' + '=' * 60)
    print('SkillAdaptor - WebShop Environment')
    print('=' * 60)
    os.environ['SkillAdaptor_BENCHMARK_ENV'] = 'webshop'
    print('\n[Setup] Initializing WebShop environment...')
    webshop_path = os.environ.get('WEBSHOP_PATH')
    if webshop_path and (not Path(webshop_path).exists()):
        raise ValueError(f'WEBSHOP_PATH does not exist: {webshop_path}')
    env = WebShopEnvWrapper(num_products=1000, webshop_path=webshop_path)
    goal_count = env.get_goal_count()
    print(f'[Setup] WebShop has {goal_count} goals')
    if args.task_manifest:
        manifest = load_task_manifest(args.task_manifest)
        training_goals = [int(x) for x in manifest.get('input_tasks') or []]
        validation_goals = [int(x) for x in manifest.get('validation_tasks') or []]
        test_goals = [int(x) for x in manifest.get('test_tasks') or []]
        if not training_goals:
            raise ValueError('WebShop task manifest must include non-empty input_tasks (goal indices)')
        if not validation_goals:
            validation_goals = build_webshop_splits(goal_count, args.validation_size, args.validation_size)[1]
        if not test_goals:
            test_goals = build_webshop_test_split(goal_count)
        print(f'[Setup] Task manifest: {args.task_manifest}')
    else:
        training_goals, validation_goals = build_webshop_splits(goal_count=goal_count, training_size=args.training_size, validation_size=args.validation_size)
        test_goals = build_webshop_test_split(goal_count)
    if not training_goals or not validation_goals:
        raise ValueError('WebShop split unavailable: check goal_count and training/validation sizes.')
    print(f'[Setup] Training on {len(training_goals)} goals')
    print(f'[Setup] Validating on {len(validation_goals)} goals')
    if not test_goals:
        raise ValueError('WebShop test split unavailable: check goal_count or manifest test_tasks.')
    print(f'[Setup] Held-out test goals: {len(test_goals)}')
    eval_rng = random.Random(42)
    if args.task_manifest and len(validation_goals) <= 50:
        eval_subset = sorted(validation_goals)
    else:
        eval_subset_size = min(50, len(validation_goals))
        eval_subset = sorted(eval_rng.sample(validation_goals, k=eval_subset_size))
    llm_config = {'api_key': config.api_key, 'base_url': config.base_url, 'model': config.model}
    evaluator = WebShopEvaluator(env, llm_config, config.results_dir, embedding_api_key=config.embedding_api_key, embedding_base_url=config.embedding_base_url)

    def eval_skill_bank(skill_bank):
        return evaluator.evaluate(goal_indices=eval_subset, skill_bank=skill_bank, verbose=False)
    initial_bank = None
    if args.skills:
        print(f'[Setup] Loading skills from {args.skills}')
        from core.skill_bank import SkillBankManager
        manager = SkillBankManager()
        manager.load(args.skills)
        initial_bank = {s.id: s for s in manager.list_skills()}
    print('\n[Run] Starting SkillAdaptor...')
    orchestrator = SkillAdaptorOrchestrator(config, llm_client=build_openai_client(config), benchmark_constraints=WebShopEnvWrapper.get_revision_constraints())
    print('[Setup] Injected WebShop benchmark constraints into Reviser')

    def execute_webshop_tasks(goal_indices, use_cache=False, **kwargs):
        current_bank = {s.id: s for s in orchestrator.skill_bank.list_skills()}
        policy = SkillAugmentedLLMPolicy(llm_config, skill_bank=current_bank, top_k_skills=3, embedding_api_key=config.embedding_api_key, embedding_base_url=config.embedding_base_url)
        trajectories = []
        for goal_idx in goal_indices:
            episode = env.run_episode(goal_idx=goal_idx, policy=policy, max_steps=50, verbose=False)
            first_obs = ''
            if episode.get('steps'):
                first_obs = str(episode['steps'][0].get('observation', '')).strip()
            task_desc = first_obs or f'WebShop goal {goal_idx}'
            episode_skill_ids = [s.id for s in policy.skills_for_episode()]
            step_dicts = [{'observation': s.get('observation', ''), 'action': s.get('action', ''), 'type': 'action', 'skills_used': []} for s in episode.get('steps', [])]
            if current_bank and step_dicts:
                from core.skill_matcher import SemanticSkillMatcher
                from core.step_skill_retriever import StepSkillRetriever
                matcher = SemanticSkillMatcher(api_key=config.embedding_api_key, base_url=config.embedding_base_url, model_name=config.embedding_model, similarity_threshold=0.35)
                retriever = StepSkillRetriever(matcher, top_k=3)
                step_dicts = retriever.annotate_trajectory_steps(task_desc, step_dicts, current_bank)
            steps = [Step(index=s['step'], observation=s.get('observation', ''), action=s.get('action', ''), reward=float(s.get('reward', 0.0)), done=bool(s.get('done', False)), skills_used=step_dicts[i].get('skills_used') or episode_skill_ids if i < len(step_dicts) else episode_skill_ids) for i, s in enumerate(episode.get('steps', []))]
            trajectories.append(Trajectory(task_id=f'goal_{goal_idx}', task_description=task_desc, steps=steps, success=bool(episode.get('success', False)), total_reward=float(episode.get('total_reward', 0.0)), error_step=None, metadata={'source': 'webshop', 'goal_idx': goal_idx}))
        return trajectories
    orchestrator._execute_tasks = execute_webshop_tasks
    result = orchestrator.run(training_tasks=training_goals, validation_tasks=validation_goals, eval_func=eval_skill_bank, initial_skill_bank=initial_bank)
    print('\n[Save] Saving results...')
    orchestrator.save_skill_bank()
    final_bank = {s.id: s for s in orchestrator.skill_bank.list_skills()}
    held_out_metrics = evaluator.evaluate(goal_indices=test_goals, skill_bank=final_bank, verbose=False)
    result['held_out_test'] = held_out_metrics
    print(f"[Test] Held-out test metrics: success_rate={held_out_metrics.get('success_rate', 0.0):.3f}, avg_score={held_out_metrics.get('avg_score', 0.0):.3f}, sample_size={held_out_metrics.get('sample_size', 0)}")
    print('\n' + '=' * 60)
    print('Results Summary')
    print('=' * 60)
    print(f"Iterations completed: {result['iterations']}")
    print(f"Final skill count: {result['final_skill_count']}")
    print(f"Held-out success: {result['held_out_test'].get('success_rate', 0.0):.3f} on {result['held_out_test'].get('sample_size', 0)} goals")
    print(f'Output directory: {config.output_dir}')
    return result

def run_pinchbench(args, config):
    from core.openclaw_hygiene import ensure_gateway_running
    print('\n' + '=' * 60)
    print('SkillAdaptor - PinchBench Environment')
    print('=' * 60)
    os.environ['SkillAdaptor_BENCHMARK_ENV'] = 'pinchbench'
    ok, probe_out = ensure_gateway_running()
    if not ok:
        raise RuntimeError(f'OpenClaw Gateway unreachable. Start it before PinchBench runs.\nLast probe:\n{probe_out}')
    print('[Setup] OpenClaw Gateway reachable')
    pinchbench_path = os.environ.get('PINCHBENCH_PATH')
    if not pinchbench_path:
        raise ValueError('PINCHBENCH_PATH is required for PinchBench execution')
    tasks_dir = os.environ.get('PINCHBENCH_TASKS_DIR', 'tasks')
    from adapters.pinchbench_adapter.task_context import install_pinchbench_task_context
    from adapters.pinchbench_adapter.hints import install_pinchbench_hints
    install_pinchbench_task_context(pinchbench_path, tasks_dir)
    install_pinchbench_hints()
    results_dir = os.environ.get('PINCHBENCH_RESULTS_DIR', 'results')
    artifact_dir = config.artifact_dir
    llm_client = build_openai_client(config)
    harness = get_harness(getattr(config, 'agent_harness', None), project_root=Path(pinchbench_path))
    executor = PinchBenchExecutor(pinchbench_path=pinchbench_path, python_cmd=os.environ.get('PINCHBENCH_PYTHON'), tasks_dir=tasks_dir, results_dir=results_dir, artifact_dir=artifact_dir, api_key=config.api_key, base_url=config.base_url, model=config.model, llm_client=llm_client, harness=harness)
    all_tasks = executor.list_tasks()
    if not all_tasks:
        raise ValueError('No PinchBench tasks found. Check PINCHBENCH_TASKS_DIR.')
    manifest_data: Optional[dict] = None
    if args.task_manifest:
        manifest_data = load_task_manifest(args.task_manifest)
        training_tasks = list(manifest_data.get('input_tasks') or [])
        validation_tasks = list(manifest_data.get('validation_tasks') or [])
        test_tasks = list(manifest_data.get('test_tasks') or [])
        if not training_tasks:
            raise ValueError('task manifest must include non-empty input_tasks')
        if not validation_tasks:
            validation_tasks = training_tasks[:1]
        print(f'[Setup] Task manifest: {args.task_manifest}')
        print(f'[Setup] input_tasks: {len(training_tasks)}')
        print(f'[Setup] Validation tasks: {len(validation_tasks)}')
        print(f'[Setup] test_tasks: {len(test_tasks)}')
    else:
        rng = random.Random(42)
        shuffled = all_tasks.copy()
        rng.shuffle(shuffled)
        total_tasks = len(shuffled)
        test_min_count = max(1, total_tasks // 10)
        max_train_val = total_tasks - test_min_count
        if max_train_val < 2:
            raise ValueError(f'Not enough PinchBench tasks ({total_tasks}) after reserving held-out test ({test_min_count}). Need at least 2 for train/validation.')
        desired_val = min(args.validation_size, max(1, total_tasks // 5))
        val_count = min(desired_val, max_train_val - 1)
        remaining_after_val = total_tasks - val_count
        train_cap = remaining_after_val - test_min_count
        if train_cap < 1:
            raise ValueError('PinchBench split invalid: no room for training after reserving validation and held-out test.')
        train_count = min(args.training_size, train_cap)
        validation_tasks = sorted(shuffled[:val_count])
        training_tasks = sorted(shuffled[val_count:val_count + train_count])
        test_tasks = sorted(shuffled[val_count + train_count:])
        if not training_tasks:
            raise ValueError('No training tasks selected for PinchBench.')
        if not args.task_manifest:
            print(f'[Setup] Total tasks: {len(all_tasks)}')
            print(f'[Setup] Training tasks: {len(training_tasks)}')
            print(f'[Setup] Validation tasks: {len(validation_tasks)}')
            print(f'[Setup] Held-out test tasks: {len(test_tasks)}')
    overlap = set(training_tasks) & set(validation_tasks)
    if overlap and (not (manifest_data and manifest_data.get('allow_train_val_overlap'))):
        raise ValueError(f'Data leakage detected: {sorted(overlap)}')
    pb_tasks_root = Path(pinchbench_path) / tasks_dir
    from runtime.retrieval_index import build_retrieval_index
    retrieval_index = build_retrieval_index(manifest_data, tasks_dir=pb_tasks_root, config=config)
    if retrieval_index.labels:
        print('[Setup] Retrieval index (manifest + task category):')
        for tid in sorted(retrieval_index.labels.keys())[:12]:
            lab = retrieval_index.labels[tid]
            print(f'  {tid}: category={lab.category} tags={lab.tags}')
    policy_adapter = PinchBenchPolicyAdapter(artifact_dir, api_key=config.embedding_api_key, base_url=config.embedding_base_url, embedding_model=config.embedding_model, similarity_threshold=config.skill_match_threshold, cross_task_threshold=config.cross_task_match_threshold, retrieval_index=retrieval_index, llm_client=llm_client, llm_model=config.model)
    initial_bank = None
    if args.skills:
        print(f'[Setup] Loading skills from {args.skills}')
        from core.skill_bank import SkillBankManager
        manager = SkillBankManager()
        manager.load(args.skills)
        initial_bank = {s.id: s for s in manager.list_skills()}
    from adapters.pinchbench_adapter.task_category import get_task_category

    def _task_category(task_id: str) -> str:
        return retrieval_index.category_of(task_id, pb_tasks_root)
    print('\n[Run] Starting SkillAdaptor...')
    orchestrator = SkillAdaptorOrchestrator(config, llm_client=llm_client, benchmark_constraints=policy_adapter.get_revision_constraints(), task_category_fn=_task_category)
    print('[Setup] Injected PinchBench benchmark constraints into Reviser')

    def eval_skill_bank(skill_bank, scope_tasks: Optional[List[str]]=None, baseline_metrics=None, candidate_skill_id: Optional[str]=None):
        return evaluate_pinchbench_bank(executor, policy_adapter, validation_tasks, skill_bank, tasks_dir=executor.tasks_dir, template=args.skill_template, model=config.model, scope_tasks=scope_tasks, global_prior=orchestrator.global_prior, embedding_api_key=config.embedding_api_key, embedding_base_url=config.embedding_base_url, embedding_model=config.embedding_model, candidate_skill_id=candidate_skill_id, baseline_metrics=baseline_metrics)

    def execute_tasks_with_current_skills(tasks, use_cache=False, **kwargs):
        current_bank = {s.id: s for s in orchestrator.skill_bank.list_skills()}
        injected = configure_pinchbench_skill_injection(executor, policy_adapter, tasks, current_bank, tasks_dir=executor.tasks_dir, template=args.skill_template, model=config.model, global_prior=orchestrator.global_prior, embedding_api_key=config.embedding_api_key, embedding_base_url=config.embedding_base_url, embedding_model=config.embedding_model)
        if injected:
            print(f'    [Skills] Configured for {injected} task(s) (with step-by-step tracking)')
        return executor.execute_tasks(tasks, model=config.model)
    orchestrator._execute_tasks = execute_tasks_with_current_skills
    result = orchestrator.run(training_tasks=training_tasks, validation_tasks=validation_tasks, eval_func=eval_skill_bank, initial_skill_bank=initial_bank)
    print('\n[Save] Saving results...')
    orchestrator.save_skill_bank()
    if test_tasks:
        final_bank = {s.id: s for s in orchestrator.skill_bank.list_skills()}
        injected = configure_pinchbench_skill_injection(executor, policy_adapter, test_tasks, final_bank, tasks_dir=executor.tasks_dir, template=args.skill_template, model=config.model, global_prior=orchestrator.global_prior, embedding_api_key=config.embedding_api_key, embedding_base_url=config.embedding_base_url, embedding_model=config.embedding_model)
        print(f'[Held-out Test] Injected skills for {injected} tasks')
        trajectories = executor.execute_tasks(test_tasks, model=config.model)
        if trajectories:
            success_count = sum((1 for t in trajectories if t.success))
            total_score = sum((t.total_reward for t in trajectories))
            result['held_out_test'] = {'success_rate': success_count / len(trajectories), 'avg_score': total_score / len(trajectories), 'sample_size': len(trajectories), 'task_results': {t.task_id: {'success': t.success, 'score': t.total_reward} for t in trajectories}}
        else:
            result['held_out_test'] = {'success_rate': 0.0, 'avg_score': 0.0, 'sample_size': 0}
        print(f"[Test] Held-out test metrics: success_rate={result['held_out_test'].get('success_rate', 0.0):.3f}, avg_score={result['held_out_test'].get('avg_score', 0.0):.3f}, sample_size={result['held_out_test'].get('sample_size', 0)}")
    else:
        print('[Test] No held-out tasks remaining after train/validation split.')
        result['held_out_test'] = {'success_rate': 0.0, 'avg_score': 0.0, 'sample_size': 0}
    return result

def main():
    args = parse_args()
    if args.test:
        print('[Test Mode] Reducing iteration count')
        args.max_iterations = 2
        args.training_size = 10
        args.validation_size = 5
    print('\n' + '=' * 60)
    print('SkillAdaptor - Training-Free Skill Evolution')
    print('=' * 60)
    print(f'Environment: {args.env}')
    print(f'Provider: {args.provider}')
    try:
        config = setup_config(args)
        print(f'Model: {config.model}')
        print(f'Max iterations: {config.max_iterations}')
    except Exception as e:
        print(f'Configuration error: {e}')
        print('Please check configs/.env file')
        return 1
    try:
        if args.env == 'webshop':
            result = run_webshop(args, config)
        elif args.env == 'claw-eval':
            result = run_claw_eval(args, config)
        elif args.env == 'workspace':
            result = run_workspace(args, config)
        else:
            result = run_pinchbench(args, config)
        print('\n✓ SkillAdaptor completed successfully!')
        return 0
    except KeyboardInterrupt:
        print('\n\nInterrupted by user')
        return 1
    except Exception as e:
        print(f'\n✗ Error: {e}')
        import traceback
        traceback.print_exc()
        return 1
if __name__ == '__main__':
    sys.exit(main())
