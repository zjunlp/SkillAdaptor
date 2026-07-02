#!/usr/bin/env python3
"""Thin wrapper: run SkillAdaptor evolution from an Agent Skill session."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _skill_adaptor_root() -> Path:
    env = os.environ.get('SKILL_ADAPTOR_ROOT', '').strip()
    if env:
        return Path(env).resolve()
    # scripts/ -> skill-adaptor/ -> skills/ -> skillnet/ -> plugin/ -> repo root
    here = Path(__file__).resolve()
    candidate = here.parents[5] / 'skill-adaptor'
    if (candidate / 'run_plugin.py').exists():
        return candidate
    raise SystemExit('Set SKILL_ADAPTOR_ROOT to the directory containing run_plugin.py')


def main() -> int:
    parser = argparse.ArgumentParser(description='Run SkillAdaptor run_plugin.py')
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--harness', choices=['openclaw', 'claude-code', 'codex'], default=None)
    parser.add_argument('--max-iterations', type=int, default=2)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--input-trajectories', default=None)
    parser.add_argument('extra', nargs='*', help='Passed through to run_plugin.py')
    args = parser.parse_args()
    root = _skill_adaptor_root()
    cmd = [sys.executable, str(root / 'run_plugin.py'), '--workspace', str(Path(args.workspace).resolve()), '--max-iterations', str(args.max_iterations)]
    if args.harness:
        cmd.extend(['--harness', args.harness])
    if args.dry_run:
        cmd.append('--dry-run')
    if args.input_trajectories:
        cmd.extend(['--input-trajectories', args.input_trajectories])
    cmd.extend(args.extra)
    print('[skill-adaptor] ' + ' '.join(cmd))
    return subprocess.call(cmd, cwd=str(root))


if __name__ == '__main__':
    raise SystemExit(main())
