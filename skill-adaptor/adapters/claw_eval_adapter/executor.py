"""Claw-Eval task executor — real runs via claw-eval CLI with step-level trace parsing."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from adapters.errors import TaskExecutionError
from core.agent_trace_resolve import (
    build_steps_from_raw,
    discover_claw_eval_trace,
    extract_trace_path_from_stdout,
    resolve_agent_trajectory_steps,
    save_annotated_trajectory,
)
from core.openclaw_hygiene import openclaw_agent_id
from core.types import Step, Trajectory

class ClawEvalExecutor:
    OPENCLAW_EVOLVED_SKILL_DIR = 'skill-adaptor-evolved'

    def __init__(
        self,
        claw_eval_path: Path | str,
        python_cmd: Optional[Path | str] = None,
        tasks_dir: Path | str = 'tasks',
        results_dir: Path | str = 'results',
        artifact_dir: Optional[Path | str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.claw_eval_path = Path(claw_eval_path)
        self.python_cmd = Path(python_cmd) if python_cmd else None
        self.tasks_dir = self.claw_eval_path / tasks_dir
        self.results_dir = self.claw_eval_path / results_dir
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.artifact_dir = Path(artifact_dir) if artifact_dir else None
        self.api_key = api_key or os.environ.get('SkillEvolve_API_KEY', '')
        self.base_url = base_url or os.environ.get('SkillEvolve_BASE_URL', '')
        self.model = model or os.environ.get('SkillEvolve_MODEL', 'gpt-4.1')
        self._task_skills: Dict[str, str] = {}
        self._task_skill_ids: Dict[str, List[str]] = {}

    def set_task_skills(
        self,
        task_skills: Dict[str, str],
        task_skill_ids: Optional[Dict[str, List[str]]] = None,
        skill_objects: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        self._task_skills = dict(task_skills or {})
        self._task_skill_ids = dict(task_skill_ids or {})

    def clear_task_skills(self) -> None:
        self._task_skills = {}
        self._task_skill_ids = {}

    def _inject_skills_to_task(self, task_id: str) -> None:
        skill_text = self._task_skills.get(task_id, '')
        if not skill_text:
            return
        skill_dir = self.tasks_dir / task_id / '.skill'
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / 'SKILL.md').write_text(skill_text, encoding='utf-8')
        openclaw_dir = Path.home() / '.openclaw' / 'workspace' / 'skills' / self.OPENCLAW_EVOLVED_SKILL_DIR
        openclaw_dir.mkdir(parents=True, exist_ok=True)
        (openclaw_dir / 'SKILL.md').write_text(skill_text, encoding='utf-8')

    def _clear_skills_from_task(self, task_id: str) -> None:
        for path in (
            self.tasks_dir / task_id / '.skill' / 'SKILL.md',
            Path.home() / '.openclaw' / 'workspace' / 'skills' / self.OPENCLAW_EVOLVED_SKILL_DIR / 'SKILL.md',
        ):
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass

    def list_tasks(self) -> List[str]:
        if not self.tasks_dir.exists():
            return []
        ids: List[str] = []
        for task_dir in self.tasks_dir.iterdir():
            if task_dir.is_dir() and (task_dir / 'task.yaml').exists():
                ids.append(task_dir.name)
        return sorted(ids)

    def _python(self) -> str:
        if self.python_cmd and self.python_cmd.exists():
            return str(self.python_cmd)
        venv_py = self.claw_eval_path / '.venv' / 'Scripts' / 'python.exe'
        if venv_py.exists():
            return str(venv_py)
        venv_unix = self.claw_eval_path / '.venv' / 'bin' / 'python'
        if venv_unix.exists():
            return str(venv_unix)
        return sys.executable

    def _env(self) -> Dict[str, str]:
        env = os.environ.copy()
        if self.api_key:
            env['OPENAI_API_KEY'] = self.api_key
            env['CLAW_EVAL_MODEL_API_KEY'] = self.api_key
        if self.base_url:
            env['OPENAI_BASE_URL'] = self.base_url
            env['CLAW_EVAL_MODEL_BASE_URL'] = self.base_url
        if self.model:
            env['CLAW_EVAL_MODEL_ID'] = self.model
        env['no_proxy'] = 'localhost,127.0.0.1'
        env['NO_PROXY'] = 'localhost,127.0.0.1'
        return env

    def _read_task_description(self, task_id: str) -> str:
        task_yaml = self.tasks_dir / task_id / 'task.yaml'
        if task_yaml.exists():
            text = task_yaml.read_text(encoding='utf-8')
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith('prompt:') or stripped.startswith('description:'):
                    return stripped.split(':', 1)[1].strip().strip('"').strip("'")
        return task_id

    def _resolve_trace_path(self, task_id: str, stdout: str, run_started: float) -> Optional[Path]:
        trace_path = extract_trace_path_from_stdout(stdout)
        if trace_path and trace_path.exists():
            return trace_path
        if trace_path and not trace_path.is_absolute():
            candidate = self.claw_eval_path / trace_path
            if candidate.exists():
                return candidate
        return discover_claw_eval_trace(self.claw_eval_path, task_id, min_mtime=run_started)

    def execute_task(self, task_id: str, timeout: int = 1800) -> Trajectory:
        task_dir = self.tasks_dir / task_id
        if not (task_dir / 'task.yaml').exists():
            raise TaskExecutionError(f'Missing task.yaml for Claw-Eval task: {task_id}')
        if self._task_skills.get(task_id):
            self._inject_skills_to_task(task_id)
        else:
            self._clear_skills_from_task(task_id)

        cmd = [self._python(), '-m', 'claw_eval.cli', 'run', '--task', str(task_dir), '--model', self.model, '--no-judge']
        run_started = time.time()
        try:
            result = subprocess.run(
                cmd,
                cwd=self.claw_eval_path,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=self._env(),
            )
        except subprocess.TimeoutExpired as exc:
            raise TaskExecutionError(f'Claw-Eval task {task_id} timed out after {timeout}s') from exc

        if result.returncode != 0:
            stderr_tail = (result.stderr or '')[:500]
            raise TaskExecutionError(f'Claw-Eval task {task_id} failed (exit {result.returncode}): {stderr_tail}')

        trace_path = self._resolve_trace_path(task_id, result.stdout or '', run_started)
        agent_id = openclaw_agent_id(self.model)
        result_data = {'task_id': task_id, 'passed': True}
        raw_steps, merge_label, meta = resolve_agent_trajectory_steps(
            task_id,
            agent_id=agent_id,
            claw_eval_trace=trace_path,
            result_data=result_data,
            artifact_dir=self.artifact_dir,
        )
        skills_used = list(self._task_skill_ids.get(task_id, []))
        steps = build_steps_from_raw(raw_steps, skills_used=skills_used, step_provenance=merge_label)

        if not steps:
            allow_synthetic = os.environ.get('ALLOW_SYNTHETIC_TRAJECTORY', '').strip().lower() in ('1', 'true', 'yes')
            if allow_synthetic:
                steps = [
                    Step(
                        index=0,
                        observation=self._read_task_description(task_id)[:500],
                        action='(claw-eval run)',
                        reward=1.0,
                        done=True,
                        skills_used=skills_used,
                        metadata={'step_provenance': 'synthetic_minimal', 'step_source': 'claw_eval_fallback'},
                    )
                ]
                print(f'[ClawEval] Synthesized minimal trajectory for {task_id} (ALLOW_SYNTHETIC_TRAJECTORY)')
            else:
                hint = f'trace={trace_path}' if trace_path else 'no trace file found'
                raise TaskExecutionError(
                    f'No step-level trajectory for {task_id} ({hint}). '
                    'Ensure claw-eval writes JSONL traces or set ALLOW_SYNTHETIC_TRAJECTORY=1 for probes.'
                )

        success = bool(steps[-1].done and steps[-1].reward >= 1.0) or all(s.reward > 0 for s in steps)
        total_reward = float(steps[-1].reward) if steps else 0.0
        task_description = self._read_task_description(task_id)
        print(
            f'[ClawEval] Trajectory: {len(steps)} steps ({merge_label}) '
            f'claw_eval={meta.get("claw_eval_step_count", 0)} openclaw={meta.get("openclaw_step_count", 0)}'
        )
        save_annotated_trajectory(
            self.artifact_dir,
            task_id=task_id,
            task_description=task_description,
            steps=steps,
            success=success,
        )
        metadata = {
            'source': 'claw-eval',
            'step_provenance': merge_label,
            'trace_path': str(trace_path) if trace_path else '',
            **meta,
        }
        return Trajectory(
            task_id=task_id,
            task_description=task_description,
            steps=steps,
            success=success,
            total_reward=total_reward,
            error_step=None if success else max(0, len(steps) - 1),
            metadata=metadata,
        )

    def execute_tasks(self, task_ids: List[str], model: Optional[str] = None) -> List[Trajectory]:
        if model:
            self.model = model
        return [self.execute_task(task_id) for task_id in task_ids]
