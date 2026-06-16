"""Claw-Eval task executor — real runs via claw-eval CLI (task.yaml format)."""

from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from core.types import Step, Trajectory
from adapters.errors import TaskExecutionError

class ClawEvalExecutor:
    OPENCLAW_EVOLVED_SKILL_DIR = 'skill-adaptor-evolved'

    def __init__(self, claw_eval_path: Path | str, python_cmd: Optional[Path | str]=None, tasks_dir: Path | str='tasks', results_dir: Path | str='results', api_key: Optional[str]=None, base_url: Optional[str]=None, model: Optional[str]=None):
        self.claw_eval_path = Path(claw_eval_path)
        self.python_cmd = Path(python_cmd) if python_cmd else None
        self.tasks_dir = self.claw_eval_path / tasks_dir
        self.results_dir = self.claw_eval_path / results_dir
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.api_key = api_key or os.environ.get('SkillEvolve_API_KEY', '')
        self.base_url = base_url or os.environ.get('SkillEvolve_BASE_URL', '')
        self.model = model or os.environ.get('SkillEvolve_MODEL', 'gpt-4.1')
        self._task_skills: Dict[str, str] = {}

    def set_task_skills(self, task_skills: Dict[str, str], task_skill_ids: Optional[Dict[str, List[str]]]=None, skill_objects: Optional[Dict[str, Dict[str, Any]]]=None) -> None:
        self._task_skills = dict(task_skills or {})

    def clear_task_skills(self) -> None:
        self._task_skills = {}

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
        for path in (self.tasks_dir / task_id / '.skill' / 'SKILL.md', Path.home() / '.openclaw' / 'workspace' / 'skills' / self.OPENCLAW_EVOLVED_SKILL_DIR / 'SKILL.md'):
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

    def execute_task(self, task_id: str, timeout: int=1800) -> Trajectory:
        task_dir = self.tasks_dir / task_id
        if not (task_dir / 'task.yaml').exists():
            raise TaskExecutionError(f'Missing task.yaml for Claw-Eval task: {task_id}')
        if self._task_skills.get(task_id):
            self._inject_skills_to_task(task_id)
        else:
            self._clear_skills_from_task(task_id)
        cmd = [self._python(), '-m', 'claw_eval.cli', 'run', '--task', str(task_dir), '--model', self.model, '--no-judge']
        try:
            result = subprocess.run(cmd, cwd=self.claw_eval_path, capture_output=True, text=True, timeout=timeout, env=self._env())
        except subprocess.TimeoutExpired as exc:
            raise TaskExecutionError(f'Claw-Eval task {task_id} timed out after {timeout}s') from exc
        success = result.returncode == 0
        if not success:
            stderr_tail = (result.stderr or '')[:500]
            raise TaskExecutionError(f'Claw-Eval task {task_id} failed (exit {result.returncode}): {stderr_tail}')
        return Trajectory(task_id=task_id, task_description=task_id, steps=[Step(index=0, observation='', action='claw-eval run', reward=1.0 if success else 0.0, done=True)], success=success, total_reward=1.0 if success else 0.0, metadata={'source': 'claw-eval', 'stdout_tail': (result.stdout or '')[-2000:]})

    def execute_tasks(self, task_ids: List[str], model: Optional[str]=None) -> List[Trajectory]:
        if model:
            self.model = model
        return [self.execute_task(task_id) for task_id in task_ids]
