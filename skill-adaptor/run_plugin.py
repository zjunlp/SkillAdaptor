#!/usr/bin/env python3
"""SkillAdaptor plugin runner — evolve skills from workspace tasks."""

from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from run_skill_adaptor import load_task_manifest, setup_config
from core.provider_config import describe_profile
from runtime.plugin_host import PluginHost
from runtime.project_config import load_project_config
from runtime.task_loader import TaskManifest, write_manifest
from runtime.task_sync import manifest_from_project, sync_manifest_to_workspace
from runtime.workspace_init import init_workspace
from runtime.evolution_guard import GlobalEvolutionLockError, cleanup_stale_locks, global_evolution_lock
from runtime.manifest_guard import validate_task_manifest
from runtime.workspace_lock import WorkspaceRunLockError, workspace_run_lock

def _default_workspace() -> Path:
    return ROOT.parent / 'plugin' / 'workspace'

def parse_init_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Initialize SkillAdaptor workspace')
    parser.add_argument('--workspace', type=str, default=str(_default_workspace()))
    parser.add_argument('--benchmark', default='workspace', choices=['workspace', 'pinchbench', 'claw-eval', 'webshop'])
    parser.add_argument('--harness', default='openclaw', choices=['openclaw', 'claude-code', 'codex', 'hermes'])
    parser.add_argument('--provider', default='auto', help='LLM backend: auto (default), deepseek, openrouter')
    parser.add_argument('--model', default='gpt-4.1')
    parser.add_argument('--max-iterations', type=int, default=2)
    parser.add_argument('--template', default=None, help='Optional bundled manifest alias (local repro); default init uses folders mode')
    parser.add_argument('--mode', choices=['bundled', 'auto_discover', 'folders'], default=None, help='Task source: bundled manifest, PINCHBENCH auto split, or empty folders')
    parser.add_argument('--auto-discover-limit', type=int, default=30)
    return parser.parse_args(argv)

def parse_run_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='SkillAdaptor OpenClaw/Claude Code plugin runner')
    parser.add_argument('--workspace', type=str, default=str(_default_workspace()))
    parser.add_argument('--manifest', type=str, default=None)
    parser.add_argument('--env', choices=['workspace', 'pinchbench', 'claw-eval', 'webshop', 'auto'], default='auto')
    parser.add_argument('--model', type=str, default=None)
    parser.add_argument('--provider', default=None, help='LLM backend: auto (default), deepseek, openrouter')
    parser.add_argument('--max-iterations', type=int, default=None)
    parser.add_argument('--output', type=str, default=None)
    parser.add_argument('--skills', type=str, default=None)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--harness', choices=['openclaw', 'claude-code', 'codex', 'hermes'], default=None)
    parser.add_argument('--program-git', action='store_true')
    parser.add_argument('--sync-tasks', action='store_true', help='Refresh task briefs from manifest/project')
    parser.add_argument('--input-trajectories', type=str, default=None, help='Seed trajectory file into workspace artifacts before evolution')
    return parser.parse_args(argv)

def _manifest_from_args(args: argparse.Namespace, host: PluginHost) -> TaskManifest:
    if args.manifest:
        data = load_task_manifest(args.manifest)
        manifest = TaskManifest(name=data.get('name', 'manifest'), benchmark=data.get('benchmark', args.env if args.env != 'auto' else 'pinchbench'), input_tasks=list(data.get('input_tasks') or []), validation_tasks=list(data.get('validation_tasks') or []), test_tasks=list(data.get('test_tasks') or []), allow_train_val_overlap=bool(data.get('allow_train_val_overlap')), probe_mode=bool(data.get('probe_mode')))
        if getattr(args, 'sync_tasks', False):
            sync_manifest_to_workspace(host.workspace, manifest)
        return manifest
    project = load_project_config(host.workspace)
    if project is not None:
        manifest = manifest_from_project(host.workspace, project)
        if getattr(args, 'sync_tasks', False) or not (host.workspace / 'input_task').exists():
            sync_manifest_to_workspace(host.workspace, manifest)
        return manifest
    env_key = None if args.env == 'auto' else args.env
    return host.resolve_manifest(env=env_key)

def write_run_record(workspace: Path, manifest: TaskManifest, result: dict, *, bank_path: Path) -> Path:
    state_dir = workspace / '.skill-adaptor' / 'runs'
    state_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = state_dir / f'run_{stamp}.json'
    from runtime.skill_export import collect_newly_adopted_skill_ids, list_skill_bank_ids
    newly_adopted = collect_newly_adopted_skill_ids(result)
    bank_ids = list_skill_bank_ids(bank_path)
    payload = {'timestamp': stamp, 'manifest': manifest.to_dict(), 'result_summary': {'iterations': result.get('iterations'), 'final_skill_count': result.get('final_skill_count'), 'newly_adopted_skill_ids': newly_adopted, 'skill_bank_ids': bank_ids, 'held_out_test': result.get('held_out_test')}}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return out

def cmd_init(args: argparse.Namespace) -> int:
    mode = args.mode or ('bundled' if args.template else 'folders')
    config = init_workspace(Path(args.workspace), benchmark=args.benchmark, harness=args.harness, provider=args.provider, model=args.model, max_iterations=args.max_iterations, template=args.template if mode == 'bundled' else None, mode=mode, auto_discover_limit=args.auto_discover_limit)
    try:
        manifest = manifest_from_project(Path(args.workspace), config)
    except ValueError:
        print('SkillAdaptor workspace initialized')
        print(f'  Path: {args.workspace}')
        print(f'  Manifest mode: {config.manifest.mode}')
        print(f'  Tasks: add *.md under input_task/ (then run again)')
        print(f'  Harness: {config.harness}  Benchmark: {config.benchmark}')
        print('\nNext:')
        print(f'  . ..\\scripts\\load_secrets.ps1')
        print(f'  python run_plugin.py --workspace {args.workspace}')
        return 0
    print('SkillAdaptor workspace initialized')
    print(f'  Path: {args.workspace}')
    print(f'  Manifest mode: {config.manifest.mode}')
    if config.manifest.path:
        print(f'  Manifest: {config.manifest.path}')
    print(f'  Tasks: input={len(manifest.input_tasks)} val={len(manifest.validation_tasks)} test={len(manifest.test_tasks)}')
    print(f'  Harness: {config.harness}  Benchmark: {config.benchmark}')
    print('\nNext:')
    print(f'  . ..\\scripts\\load_secrets.ps1')
    print(f'  python run_plugin.py --workspace {args.workspace}')
    return 0

def _maybe_reexec_for_benchmark(env: str) -> None:
    key = {'pinchbench': 'PINCHBENCH_PYTHON', 'claw-eval': 'CLAW_EVAL_PYTHON'}.get(env)
    if not key:
        return
    target = os.environ.get(key, '').strip()
    if not target:
        return
    target_path = Path(target).resolve()
    current = Path(sys.executable).resolve()
    if target_path == current:
        return
    if not target_path.exists():
        print(f'WARN {key}={target} not found; using {current}')
        return
    print(f'[{env}] Re-launching with {target_path}')
    import subprocess
    result = subprocess.run([str(target_path), *sys.argv], env=os.environ)
    raise SystemExit(result.returncode)

def cmd_run(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace)
    if args.input_trajectories:
        from runtime.trajectory_bootstrap import bootstrap_trajectories
        try:
            dest = bootstrap_trajectories(workspace, args.input_trajectories)
            print(f'[Plugin] Bootstrapped trajectories → {dest}')
        except FileNotFoundError as exc:
            print(f'Plugin run failed: {exc}')
            return 1
    project = load_project_config(workspace)
    provider_name = args.provider or (project.provider if project else None) or os.environ.get('SkillAdaptor_PROVIDER', 'auto')
    harness = args.harness or (project.harness if project else None)
    host = PluginHost(workspace, provider=provider_name, harness=harness)
    try:
        manifest = _manifest_from_args(args, host)
    except ValueError as exc:
        print(f'Manifest error: {exc}')
        print('Hint: python run_plugin.py init --workspace <path>  then add tasks under input_task/')
        return 1
    env = args.env
    if env == 'auto':
        from runtime.adapter_registry import resolve_adapter
        spec = resolve_adapter(manifest.benchmark)
        env = spec.benchmark_key
    if manifest.benchmark in ('claw-eval', 'claw_eval'):
        env = 'claw-eval'
    elif manifest.benchmark in ('workspace', 'openclaw-generic', 'openclaw'):
        env = 'workspace'
    max_iter = args.max_iterations
    if max_iter is None and project:
        max_iter = project.max_iterations
    if max_iter is None:
        max_iter = 3
    if args.output is None:
        args.output = str(workspace / '.skill-adaptor' / 'evolution_output')

    class _Args:
        pass
    bridge = _Args()
    bridge.env = env
    bridge.provider = args.provider or (project.provider if project else None)
    bridge.model = args.model or (project.model if project else None)
    bridge.max_iterations = max_iter
    bridge.training_size = len(manifest.input_tasks)
    bridge.validation_size = len(manifest.validation_tasks)
    bridge.output = args.output
    bridge.skills = args.skills
    bridge.skill_template = 'enhanced'
    bridge.test = False
    bridge.task_manifest = None
    print('=' * 60)
    print('SkillAdaptor Plugin Run')
    print('=' * 60)
    print(f'Workspace: {workspace}')
    print(f'Environment: {env}')
    print(f'Harness: {host.harness_name}')
    print(f'input_tasks ({len(manifest.input_tasks)}): {manifest.input_tasks}')
    print(f'validation_tasks ({len(manifest.validation_tasks)}): {manifest.validation_tasks}')
    print(f'test_tasks ({len(manifest.test_tasks)}): {manifest.test_tasks}')
    warns, errs = validate_task_manifest(manifest)
    for w in warns:
        print(f'[Manifest] WARNING: {w}')
    if errs and (not args.dry_run):
        for e in errs:
            print(f'[Manifest] ERROR: {e}')
        print('Hint: use init --mode auto_discover for disjoint splits, or probe_mode=true for quick smoke')
        return 1
    if args.dry_run:
        from runtime.adapter_registry import resolve_adapter
        spec = resolve_adapter(env)
        if spec.requires_path_env and not os.environ.get(spec.requires_path_env):
            print(f'[Dry-run] Live run requires {spec.requires_path_env} (optional benchmark executor).')
            print('[Dry-run] Workspace-only: add trajectories via --input-trajectories or use --harness claude-code for custom tasks.')
        print('[Dry-run] Manifest OK — evolution skipped.')
        return 0
    _maybe_reexec_for_benchmark(env)
    cleanup_stale_locks(workspace)
    lock_label = manifest.name or 'plugin-run'
    try:
        with global_evolution_lock(label=lock_label):
            with workspace_run_lock(workspace, label=lock_label):
                return _run_evolution_locked(args, workspace, project, host, manifest, env, max_iter, bridge)
    except GlobalEvolutionLockError as exc:
        print(f'Global evolution busy: {exc}')
        print('Hint: only one run_plugin evolution at a time (shared OpenClaw gateway).')
        return 3
    except WorkspaceRunLockError as exc:
        print(f'Workspace busy: {exc}')
        return 2

def _run_evolution_locked(args: argparse.Namespace, workspace: Path, project, host: PluginHost, manifest: TaskManifest, env: str, max_iter: int, bridge) -> int:
    provider_name = args.provider or (project.provider if project else None) or os.environ.get('SkillAdaptor_PROVIDER', 'auto')
    try:
        config = setup_config(bridge)
        profile = getattr(config, '_llm_profile', None)
        if profile is not None:
            print(f'[Provider] {describe_profile(profile)}')
    except Exception as exc:
        print(f'Configuration error: {exc}')
        return 1
    os.environ.setdefault('SkillAdaptor_output_DIR', args.output)
    config.output_dir = Path(args.output)
    config.artifact_dir = workspace / '.skill-adaptor' / 'artifacts'
    config.results_dir = workspace / '.skill-adaptor' / 'results'
    config.skills_workspace_dir = workspace / 'skills'
    config.program_workspace = workspace
    config.agent_harness = host.harness_name
    config.program_git_branches = args.program_git
    config.direct_skill_write = True
    if manifest.probe_mode:
        config.min_sample_size = 1
        os.environ.setdefault('ALLOW_SYNTHETIC_TRAJECTORY', '1')
        print('[Plugin] probe_mode: min_sample_size=1 for adoption gate')
    config.create_directories()
    skills_out = workspace / 'skills'
    skills_out.mkdir(parents=True, exist_ok=True)
    write_manifest(workspace / '.skill-adaptor' / 'active_manifest.json', manifest)
    try:
        result = host.run_evolution(bridge, config, env=env, manifest=manifest)
    except Exception as exc:
        import traceback
        print(f'Plugin run failed: {exc}')
        if os.environ.get('SKILLADAPTOR_DEBUG', '').strip().lower() in ('1', 'true', 'yes'):
            traceback.print_exc()
        return 1
    record = write_run_record(workspace, manifest, result, bank_path=config.output_dir / 'skill_bank_final.json')
    print(f'\n[Plugin] Run record: {record}')
    bank_path = config.output_dir / 'skill_bank_final.json'
    from runtime.skill_export import collect_newly_adopted_skill_ids, export_skills_to_workspace, list_skill_bank_ids, sync_workspace_skills_to_claude, sync_workspace_skills_to_codex, sync_workspace_skills_to_hermes
    exported = export_skills_to_workspace(bank_path, skills_out)
    newly_adopted = collect_newly_adopted_skill_ids(result)
    bank_ids = list_skill_bank_ids(bank_path)
    print(f'[Plugin] Exported {exported} skill(s) to {skills_out}')
    if host.harness_name in ('claude-code', 'claude'):
        n_claude = sync_workspace_skills_to_claude(skills_out, workspace)
        if n_claude:
            print(f"[Plugin] Synced {n_claude} skill(s) to {workspace / '.claude' / 'skills'}")
    elif host.harness_name == 'codex':
        n_codex = sync_workspace_skills_to_codex(skills_out, workspace)
        if n_codex:
            codex_home = os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))
            print(f"[Plugin] Synced {n_codex} skill(s) to {codex_home}/skills and {workspace / '.agents' / 'skills'}")
    elif host.harness_name == 'hermes':
        n_hermes = sync_workspace_skills_to_hermes(skills_out, workspace)
        if n_hermes:
            hermes_home = os.environ.get('HERMES_HOME', str(Path.home() / '.hermes'))
            print(f"[Plugin] Synced {n_hermes} skill(s) to {hermes_home}/skills/skill-adaptor and {workspace / '.hermes' / 'skills' / 'skill-adaptor'}")
    if newly_adopted:
        print(f"[Plugin] Newly adopted this run: {', '.join(newly_adopted)}")
    elif bank_ids:
        print(f'[Plugin] No new adoptions ({len(bank_ids)} skill(s) in final bank; seeds unchanged or all proposals rejected)')
    from runtime.skillnet_bridge import post_adopt_hooks
    sn = post_adopt_hooks(workspace, newly_adopted)
    if sn.get('evaluated'):
        print(f"[Plugin] SkillNet evaluated {len(sn['evaluated'])} skill(s) (SKILLNET_POST_EVAL)")
    if sn.get('analyze') is not None:
        print('[Plugin] SkillNet analyze complete (SKILLNET_POST_ANALYZE)')
    if sn.get('error'):
        print(f"[Plugin] SkillNet hook skipped: {sn['error']}")
    elif sn.get('note'):
        print(f"[Plugin] {sn['note']}")
    if sn.get('report_path'):
        print(f"[Plugin] SkillNet report: {sn['report_path']}")
    if not newly_adopted:
        print('[Plugin] No skills adopted this run (see rejection_history.json and evolution_audit.jsonl).')
    return 0

def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] == 'init':
        return cmd_init(parse_init_args(argv[1:]))
    if argv and argv[0] == 'run':
        return cmd_run(parse_run_args(argv[1:]))
    return cmd_run(parse_run_args(argv))
if __name__ == '__main__':
    raise SystemExit(main())
