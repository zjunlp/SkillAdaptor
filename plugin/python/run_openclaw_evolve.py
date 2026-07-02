#!/usr/bin/env python3
"""OpenClaw TypeScript plugin bridge → SkillAdaptor ``run_plugin.py``."""

from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='OpenClaw SkillAdaptor bridge')
    parser.add_argument('--workspace-dir', required=True)
    parser.add_argument('--state-dir', required=True)
    parser.add_argument('--skill-adaptor-root', required=True)
    parser.add_argument('--env', choices=['pinchbench', 'claw-eval', 'webshop', 'auto'], default='auto')
    parser.add_argument('--max-iterations', type=int, default=3)
    parser.add_argument('--all-as-test', choices=['true', 'false'], default='false')
    parser.add_argument('--input-skills', default='')
    parser.add_argument('--input-trajectories', default='')
    parser.add_argument('--provider', default=None)
    parser.add_argument('--model', default=None)
    return parser.parse_args()

def _sync_input_tasks(workspace_dir: Path, state_dir: Path) -> list[str]:
    input_dir = workspace_dir / 'input_task'
    input_dir.mkdir(parents=True, exist_ok=True)
    task_ids: list[str] = []
    manifest_path = state_dir / 'task_manifest.json'
    if manifest_path.exists():
        data = json.loads(manifest_path.read_text(encoding='utf-8'))
        task_ids = list(data.get('input_tasks') or data.get('tasks') or [])
    if not task_ids:
        for path in sorted(input_dir.iterdir()):
            if path.suffix == '.md':
                task_ids.append(path.stem)
    for tid in task_ids:
        brief_path = input_dir / f'{tid}.md'
        if not brief_path.exists():
            brief_path.write_text(
                f'# {tid}\n\nAdd task brief content or set PINCHBENCH_PATH.\n',
                encoding='utf-8',
            )
    return task_ids

def _bootstrap_trajectories(workspace_dir: Path, trajectories_path: str, skill_root: Path) -> None:
    sys.path.insert(0, str(skill_root))
    from runtime.trajectory_bootstrap import bootstrap_trajectories
    try:
        dest = bootstrap_trajectories(workspace_dir, trajectories_path)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    print(f'[Bridge] Bootstrapped trajectories → {dest}')

def _latest_run_record(runs_dir: Path) -> Path | None:
    if not runs_dir.exists():
        return None
    records = sorted(runs_dir.glob('run_*.json'), key=lambda p: p.stat().st_mtime)
    return records[-1] if records else None

def _write_evolution_result(workspace_dir: Path, *, env: str, all_as_test: bool, bank_path: Path, run_record: Path | None, exit_code: int) -> Path:
    output_dir = workspace_dir / '.skill-adaptor' / 'evolution_output'
    output_dir.mkdir(parents=True, exist_ok=True)
    bank_data: dict = {}
    if bank_path.exists():
        bank_data = json.loads(bank_path.read_text(encoding='utf-8'))
    run_summary: dict = {}
    manifest_name = workspace_dir.name
    if run_record and run_record.exists():
        run_summary = json.loads(run_record.read_text(encoding='utf-8'))
        manifest_name = (run_summary.get('manifest') or {}).get('name', manifest_name)
    skill_ids = sorted((bank_data.get('skills') or {}).keys())
    payload = {'result': {'success': exit_code == 0, 'final_skill_count': len(skill_ids), 'adopted_skill_ids': skill_ids, 'iterations': (run_summary.get('result_summary') or {}).get('iterations'), 'held_out_test': (run_summary.get('result_summary') or {}).get('held_out_test')}, 'final_skill_bank_path': str(bank_path.resolve()), 'task_count': len((run_summary.get('manifest') or {}).get('input_tasks') or []), 'mode': env, 'all_as_test': all_as_test, 'run_record': str(run_record.resolve()) if run_record else None, 'timestamp': datetime.now(timezone.utc).isoformat()}
    output_file = output_dir / 'plugin_evolution_result.json'
    output_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return output_file

def main() -> int:
    args = parse_args()
    workspace_dir = Path(args.workspace_dir).resolve()
    state_dir = Path(args.state_dir).resolve()
    skill_root = Path(args.skill_adaptor_root).resolve()
    run_plugin = skill_root / 'run_plugin.py'
    if not run_plugin.exists():
        print(f'run_plugin.py not found under {skill_root}', file=sys.stderr)
        return 1
    if args.input_skills:
        skills_path = Path(args.input_skills)
        if not skills_path.exists():
            print(f'input-skills not found: {skills_path}', file=sys.stderr)
            return 1
    if args.input_trajectories:
        _bootstrap_trajectories(workspace_dir, args.input_trajectories, skill_root)
    task_ids = _sync_input_tasks(workspace_dir, state_dir)
    manifest_out = workspace_dir / '.skill-adaptor' / 'active_manifest.json'
    if args.all_as_test == 'true':
        print('[PROBE] all_as_test=true — disjoint splits disabled; not for paper eval', file=sys.stderr)
        manifest = {'name': workspace_dir.name, 'benchmark': args.env if args.env != 'auto' else 'pinchbench', 'input_tasks': task_ids, 'validation_tasks': task_ids[:max(1, min(5, len(task_ids)))], 'test_tasks': task_ids, 'allow_train_val_overlap': True, 'probe_mode': True}
        manifest_out.parent.mkdir(parents=True, exist_ok=True)
        manifest_out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    elif state_dir.joinpath('task_manifest.json').exists() and (not manifest_out.exists()):
        data = json.loads(state_dir.joinpath('task_manifest.json').read_text(encoding='utf-8'))
        manifest_out.parent.mkdir(parents=True, exist_ok=True)
        manifest_out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    cmd = [sys.executable, str(run_plugin), '--workspace', str(workspace_dir), '--max-iterations', str(args.max_iterations)]
    env_name = args.env if args.env != 'auto' else os.environ.get('SkillAdaptor_BENCHMARK_ENV', 'pinchbench')
    cmd.extend(['--env', env_name])
    if manifest_out.exists():
        cmd.extend(['--manifest', str(manifest_out)])
    if args.input_skills:
        cmd.extend(['--skills', args.input_skills])
    if args.provider:
        cmd.extend(['--provider', args.provider])
    if args.model:
        cmd.extend(['--model', args.model])
    print(f"[Bridge] Running: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(skill_root), env=os.environ.copy())
    exit_code = int(proc.returncode or 0)
    bank_path = workspace_dir / '.skill-adaptor' / 'evolution_output' / 'skill_bank_final.json'
    run_record = _latest_run_record(workspace_dir / '.skill-adaptor' / 'runs')
    if bank_path.exists() and exit_code == 0:
        sys.path.insert(0, str(skill_root))
        from runtime.skill_export import export_skills_to_workspace
        exported = export_skills_to_workspace(bank_path, workspace_dir / 'skills')
        print(f"[Bridge] Exported {exported} skill(s) to {workspace_dir / 'skills'}")
    output_file = _write_evolution_result(workspace_dir, env=env_name, all_as_test=args.all_as_test == 'true', bank_path=bank_path, run_record=run_record, exit_code=exit_code)
    print(f'EVOLVE_OUTPUT_FILE={output_file.resolve()}')
    return exit_code
if __name__ == '__main__':
    raise SystemExit(main())
