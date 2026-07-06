"""PinchBench Task Executor"""

from __future__ import annotations
import json
import os
import re
import shutil
import subprocess
import sys
import platform
from pathlib import Path
from typing import Any, Dict, List, Optional
from core.types import Trajectory, Step, Skill
from core.api_env import (
    EMBEDDING_MODEL_VAR,
    embedding_key_envs,
    embedding_url_envs,
    first_env,
    inject_benchmark_child_env,
    chat_key_envs,
    chat_url_envs,
    chat_model_envs,
)
from core.openclaw_agent_setup import prepare_openclaw_for_model
from adapters.errors import TaskExecutionError, PlaceholderDeliverableError
from .trajectory_extractor import extract_trajectory_for_task, save_trajectory
from .skill_tracker import create_step_tracker
from core.step_skill_retriever import StepSkillRetriever
from core.skill_matcher import SemanticSkillMatcher
from core.trajectory_step_merge import load_cached_trajectory_steps, merge_trajectory_steps, steps_from_openclaw_trajectory, steps_from_pinchbench_transcript
from runtime.execution_binding import apply_prompt_prefix
from adapters.pinchbench_adapter.score_normalize import resolve_shell_task_score
from runtime.harness import AgentHarness, get_harness
from runtime.harness.openclaw import EVOLVED_SKILL_DIR as OPENCLAW_EVOLVED_SKILL_DIR

class PinchBenchExecutor:

    def __init__(self, pinchbench_path: Path | str, python_cmd: Optional[Path | str]=None, tasks_dir: Path | str='tasks', results_dir: Path | str='results', artifact_dir: Optional[Path | str]=None, api_key: Optional[str]=None, base_url: Optional[str]=None, model: Optional[str]=None, llm_client: Optional[Any]=None, harness: Optional[AgentHarness]=None):
        self.pinchbench_path = Path(pinchbench_path)
        env_py = os.environ.get('PINCHBENCH_PYTHON')
        if python_cmd:
            self.python_cmd = Path(python_cmd)
        elif env_py and Path(env_py).exists():
            self.python_cmd = Path(env_py)
        else:
            self.python_cmd = None
        self.tasks_dir = self.pinchbench_path / tasks_dir
        self.results_dir = self.pinchbench_path / results_dir
        self.artifact_dir = Path(artifact_dir) if artifact_dir else None
        self.api_key = api_key or first_env(*chat_key_envs()) or os.environ.get('ANTHROPIC_API_KEY', '')
        self.base_url = base_url or first_env(*chat_url_envs())
        self.model = model
        self._llm_client = llm_client
        self.harness = harness or get_harness()
        self._task_skills: Dict[str, str] = {}
        self._task_skill_ids: Dict[str, List[str]] = {}
        self._task_skill_objects: Dict[str, Dict[str, Any]] = {}
        self._task_prompt_prefixes: Dict[str, str] = {}
        self._step_retriever: Optional[StepSkillRetriever] = None
        self._skill_bank_dict: Dict[str, Skill] = {}
        self._step_top_k: int = 3

    def set_skill_bank(self, skill_bank: Dict[str, Skill], *, top_k: int=3, api_key: Optional[str]=None, base_url: Optional[str]=None, embedding_model: Optional[str]=None) -> None:
        if not skill_bank:
            self._step_retriever = None
            self._skill_bank_dict = {}
            return
        matcher = SemanticSkillMatcher(
            model_name=embedding_model or first_env(EMBEDDING_MODEL_VAR),
            api_key=api_key or first_env(*embedding_key_envs()),
            base_url=base_url or first_env(*embedding_url_envs()),
            similarity_threshold=0.35,
        )
        self._step_retriever = StepSkillRetriever(matcher, top_k=top_k)
        self._skill_bank_dict = dict(skill_bank)
        self._step_top_k = top_k

    def clear_skill_bank(self) -> None:
        self._step_retriever = None
        self._skill_bank_dict = {}

    def list_tasks(self) -> List[str]:
        tasks = []
        if self.tasks_dir.exists():
            for task_file in self.tasks_dir.glob('task_*.md'):
                tasks.append(task_file.stem)
            for task_dir in self.tasks_dir.iterdir():
                if task_dir.is_dir() and task_dir.name.startswith('T') and (task_dir / 'task.yaml').exists():
                    tasks.append(task_dir.name)
        return sorted(set(tasks))

    def set_task_skills(self, task_skills: Dict[str, str], task_skill_ids: Optional[Dict[str, List[str]]]=None, skill_objects: Optional[Dict[str, Dict[str, Any]]]=None) -> None:
        self._task_skills = task_skills
        self._task_skill_ids = task_skill_ids or {}
        self._task_skill_objects = skill_objects or {}

    def set_task_prompt_prefixes(self, prefixes: Dict[str, str]) -> None:
        self._task_prompt_prefixes = {k: v for k, v in (prefixes or {}).items() if v and v.strip()}
    OPENCLAW_EVOLVED_SKILL_DIR = OPENCLAW_EVOLVED_SKILL_DIR

    def _inject_skills_to_task(self, task_id: str) -> None:
        if task_id not in self._task_skills:
            return
        skill_text = self._task_skills[task_id]
        if not skill_text:
            return
        self.harness.inject_skill_text(skill_text, benchmark_root=self.pinchbench_path, task_id=task_id)

    def _clear_skills_from_task(self, task_id: str) -> None:
        self.harness.clear_skill_injection(benchmark_root=self.pinchbench_path, task_id=task_id)

    def clear_task_skills(self) -> None:
        self._task_skills = {}
        self._task_skill_ids = {}
        self._task_skill_objects = {}
        self._task_prompt_prefixes = {}
        self.clear_skill_bank()
        self.purge_all_skill_injections()

    def purge_all_skill_injections(self) -> None:
        self.harness.purge_all_injections(benchmark_root=self.pinchbench_path)

    def _get_python_cmd(self) -> Path:
        env_py = os.environ.get('PINCHBENCH_PYTHON')
        if env_py and Path(env_py).exists():
            return Path(env_py)
        if self.python_cmd and self.python_cmd.exists():
            return self.python_cmd
        if platform.system() == 'Windows':
            for candidate in (Path('C:\\Python312\\python.exe'), Path(sys.executable)):
                if candidate.exists():
                    return candidate
        return Path(sys.executable)

    def _benchmark_cmd_prefix(self) -> List[str]:
        pyproject = self.pinchbench_path / 'pyproject.toml'
        python_cmd = self._get_python_cmd()
        if pyproject.exists():
            return [str(python_cmd), '-m', 'uv', 'run']
        return [str(python_cmd)]

    def _setup_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        env['PYTHONPATH'] = str(self.pinchbench_path)
        model = self.model or first_env(*chat_model_envs())
        inject_benchmark_child_env(env, api_key=self.api_key, base_url=self.base_url, model=model)
        env['PINCHBENCH_TIMEOUT'] = '1200'
        return env

    def _load_task_description(self, task_id: str) -> str:
        task_md = self.tasks_dir / f'{task_id}.md'
        if not task_md.exists():
            raise FileNotFoundError(f'Task markdown not found: {task_md}')
        text = task_md.read_text(encoding='utf-8', errors='replace')
        if '## Prompt' in text:
            section = text.split('## Prompt', 1)[1]
            for marker in ('## Expected', '## Grading', '## Automated'):
                if marker in section:
                    section = section.split(marker, 1)[0]
            body = section.strip()
            if body:
                return body
        raise TaskExecutionError(
            f'Task {task_id}: missing or empty ## Prompt section in {task_md}'
        )

    def _ensure_agent_auth(self, agent_id: str, effective_model: str) -> None:
        prepare_openclaw_for_model(
            effective_model,
            api_key=self.api_key,
            base_url=self.base_url,
            fix_main_auth=True,
        )

    def _verify_task_prompt_loaded(self, task_id: str) -> str:
        prompt = self._load_task_description(task_id)
        if len(prompt.strip()) < 20:
            raise TaskExecutionError(
                f'Task {task_id}: prompt text missing or too short ({len(prompt)} chars). '
                f'Check {self.tasks_dir / f"{task_id}.md"}'
            )
        return prompt

    def _check_trajectory_fidelity(self, trajectory: Trajectory, task_id: str) -> None:
        from core.prompt_fidelity import check_trajectory_fidelity

        if not trajectory.task_description or len(trajectory.task_description.strip()) < 20:
            trajectory.task_description = self._verify_task_prompt_loaded(task_id)
        report = check_trajectory_fidelity(trajectory)
        if not report.ok:
            raise PlaceholderDeliverableError(
                f'Task {task_id} fidelity check failed after run: {report.summary()}'
            )

    def _execute_task_once(self, task_id: str, model: Optional[str], timeout: int, timeout_multiplier: float, effective_model: str) -> Optional[Trajectory]:
        if task_id in self._task_skills and self._task_skills.get(task_id):
            self._inject_skills_to_task(task_id)
        else:
            self._clear_skills_from_task(task_id)
        cmd = [*self._benchmark_cmd_prefix(), 'scripts/benchmark.py', '--model', effective_model, '--suite', task_id, '--no-upload', '--timeout-multiplier', str(timeout_multiplier)]
        if self.base_url:
            cmd.extend(['--base-url', self.base_url])
        env = self._setup_env()
        env = apply_prompt_prefix(env, task_id, self._task_prompt_prefixes)
        result = subprocess.run(cmd, cwd=self.pinchbench_path, capture_output=True, text=True, timeout=timeout, env=env)
        if result.returncode != 0:
            stderr = (result.stderr or '')[:500]
            raise TaskExecutionError(f'Task {task_id} failed (exit {result.returncode}). stderr: {stderr}')
        trajectory_result = self._parse_task_result(task_id, effective_model)
        if trajectory_result and 'openclaw_trajectory_steps' in trajectory_result.metadata:
            steps = trajectory_result.metadata['openclaw_trajectory_steps']
            print(f'[Executor] Trajectory extracted: {steps} steps from OpenClaw')
        return trajectory_result

    def execute_task(self, task_id: str, model: Optional[str]=None, timeout: int=600, timeout_multiplier: float=2.0) -> Optional[Trajectory]:
        from core.prompt_fidelity import exec_max_retries

        effective_model = model or self.model or first_env(*chat_model_envs()) or 'default'
        if timeout == 600:
            timeout = int(os.environ.get('PINCHBENCH_EXECUTE_TIMEOUT', '1200'))
        full_agent_id = openclaw_agent_id(effective_model)
        self._ensure_agent_auth(full_agent_id, effective_model)
        expected_prompt = self._verify_task_prompt_loaded(task_id)
        max_attempts = exec_max_retries()
        last_err: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            try:
                cleanup_agent_sessions(full_agent_id)
                require_gateway_running(max_wait_s=20.0)
                if attempt > 1:
                    print(f'[Executor] Retry {attempt}/{max_attempts} for {task_id} (prior: {last_err})')
                trajectory_result = self._execute_task_once(task_id, model, timeout, timeout_multiplier, effective_model)
                if trajectory_result is None:
                    raise TaskExecutionError(f'Task {task_id} returned no trajectory')
                if not trajectory_result.task_description or len(trajectory_result.task_description.strip()) < 20:
                    trajectory_result.task_description = expected_prompt
                self._check_trajectory_fidelity(trajectory_result, task_id)
                if attempt > 1:
                    trajectory_result.metadata = dict(trajectory_result.metadata or {})
                    trajectory_result.metadata['fidelity_retries'] = attempt - 1
                return trajectory_result
            except PlaceholderDeliverableError as exc:
                last_err = exc
                if attempt >= max_attempts:
                    raise TaskExecutionError(
                        f'Task {task_id} failed fidelity after {max_attempts} attempt(s): {exc}'
                    ) from exc
            except subprocess.TimeoutExpired as exc:
                raise TaskExecutionError(f'Task {task_id} timed out after {timeout}s') from exc
            except TaskExecutionError:
                raise
            except Exception as exc:
                raise TaskExecutionError(f'Error executing {task_id}: {exc}') from exc
        return None

    def execute_tasks(self, task_ids: List[str], model: str='default', parallel: bool=False) -> List[Trajectory]:
        trajectories = []
        for task_id in task_ids:
            print(f'Executing {task_id}...')
            traj = self.execute_task(task_id, model)
            if traj:
                trajectories.append(traj)
        return trajectories

    def _parse_task_result(self, task_id: str, model: Optional[str]=None) -> Optional[Trajectory]:
        result_files = list(self.results_dir.glob(f'{task_id}_*.json'))
        if not result_files:
            all_json = list(self.results_dir.glob('*.json'))
            matching_files = []
            for f in all_json:
                try:
                    with open(f, encoding='utf-8') as fp:
                        data = json.load(fp)
                    if data.get('suite') == task_id:
                        matching_files.append(f)
                    elif 'tasks' in data:
                        for task in data['tasks']:
                            if task.get('task_id') == task_id:
                                matching_files.append(f)
                                break
                except Exception:
                    continue
            result_files = matching_files
        if not result_files:
            raise TaskExecutionError(f'No PinchBench result file found for {task_id}')
        result_file = max(result_files, key=lambda p: p.stat().st_mtime)
        try:
            with open(result_file, encoding='utf-8') as f:
                data = json.load(f)
            return self._convert_to_trajectory(task_id, data, model)
        except (json.JSONDecodeError, OSError, KeyError, TypeError) as exc:
            raise TaskExecutionError(f'Error parsing PinchBench result for {task_id} from {result_file}: {exc}') from exc

    def _convert_to_trajectory(self, task_id: str, data: Dict[str, Any], model: Optional[str]=None) -> Trajectory:
        task_data = data
        if 'tasks' in data and isinstance(data['tasks'], list):
            for t in data['tasks']:
                if t.get('task_id') == task_id:
                    task_data = t
                    break
        effective_model = model or os.environ.get('MODEL', 'default')
        full_agent_id = openclaw_agent_id(effective_model)
        openclaw_traj = extract_trajectory_for_task(full_agent_id, task_id, data)
        cached_aux_steps = load_cached_trajectory_steps(self.artifact_dir, task_id)
        if self.artifact_dir and openclaw_traj:
            traj_dir = Path(self.artifact_dir) / 'trajectories'
            save_trajectory(openclaw_traj, traj_dir, format='both')
            print(f'[Executor] Saved OpenClaw trajectory to {traj_dir}')
        skills_used_in_task = self._task_skill_ids.get(task_id, [])
        skill_objects_for_task = self._task_skill_objects.get(task_id, {})
        step_tracker = None
        if skill_objects_for_task and self._llm_client:
            try:
                step_tracker = create_step_tracker(
                    skills=skill_objects_for_task,
                    llm_client=self._llm_client,
                    model=self.model or effective_model,
                )
            except RuntimeError as e:
                print(f'[Warning] Failed to create step tracker: {e}')
                step_tracker = None
        transcript = task_data.get('transcript', [])
        native_steps = steps_from_pinchbench_transcript(transcript)
        openclaw_steps = steps_from_openclaw_trajectory(openclaw_traj or [])
        if not openclaw_steps and cached_aux_steps:
            openclaw_steps = cached_aux_steps
            print(f'[Executor] Using cached auxiliary trajectory ({len(cached_aux_steps)} steps)')
        raw_steps, step_provenance = merge_trajectory_steps(native_steps, openclaw_steps)
        print(f'[Executor] Step merge: native={len(native_steps)} extracted={len(openclaw_steps)} -> merged={len(raw_steps)} ({step_provenance})')
        task_description = task_data.get('task_description') or task_data.get('prompt')
        if not task_description:
            task_description = self._load_task_description(task_id)
        steps_for_annotation = [{'observation': rs['observation'], 'action': rs['action'], 'type': 'action', 'skills_used': list(rs.get('skills_used') or [])} for rs in raw_steps]
        enriched_steps = steps_for_annotation
        if self._step_retriever and self._skill_bank_dict:
            emb_annotated = self._step_retriever.annotate_trajectory_steps(task_description, steps_for_annotation, self._skill_bank_dict)
            enriched_steps = []
            for i, emb_step in enumerate(emb_annotated):
                native_ids = steps_for_annotation[i].get('skills_used') or []
                emb_ids = emb_step.get('skills_used') or []
                merged = dict(emb_step)
                merged['skills_used'] = native_ids if native_ids else emb_ids
                enriched_steps.append(merged)
            print(f'[Executor] Per-step Top-{self._step_top_k} skills_used via embedding ({len(self._skill_bank_dict)} skills in bank)')
        use_llm_step_tracker = step_tracker and enriched_steps and (not self._step_retriever)
        if use_llm_step_tracker:
            llm_enriched = step_tracker.track_trajectory_skills(enriched_steps)
            for i, step_dict in enumerate(llm_enriched):
                native_ids = enriched_steps[i].get('skills_used') or []
                llm_ids = step_dict.get('skills_used') or []
                enriched_steps[i]['skills_used'] = native_ids if native_ids else llm_ids
        elif step_tracker and self._step_retriever:
            print('[Executor] Skipping LLM step tracker (embedding annotation already applied)')
        steps = []
        for i, rs in enumerate(raw_steps):
            step_skills = enriched_steps[i].get('skills_used', skills_used_in_task) if i < len(enriched_steps) else skills_used_in_task
            if not step_skills:
                step_skills = skills_used_in_task
            step = Step(index=rs['index'], observation=rs['observation'], action=rs['action'], reward=rs['reward'], done=rs['done'], skills_used=step_skills, metadata={'step_provenance': rs.get('step_provenance', step_provenance), 'step_source': rs.get('source', 'merged')})
            steps.append(step)
        if not steps:
            score_preview = task_data.get('score', 0)
            if not score_preview and isinstance(task_data.get('grading'), dict):
                score_preview = task_data['grading'].get('mean', 0)
            response_text = (task_data.get('response') or task_data.get('output') or '').strip()
            if not response_text and transcript:
                for row in reversed(transcript):
                    if isinstance(row, dict):
                        content = row.get('content') or row.get('text') or ''
                        if isinstance(content, str) and content.strip():
                            response_text = content.strip()[:500]
                            break
            if score_preview > 0 or response_text:
                allow_synthetic = os.environ.get('ALLOW_SYNTHETIC_TRAJECTORY', '').strip().lower() in ('1', 'true', 'yes')
                if allow_synthetic:
                    steps = [
                        Step(
                            index=0,
                            observation=(task_description or task_id)[:500],
                            action='(assistant response)',
                            reward=float(score_preview or 0),
                            done=True,
                            skills_used=skills_used_in_task,
                            metadata={'step_provenance': 'synthetic_minimal', 'step_source': 'pinchbench_transcript_fallback'},
                        )
                    ]
                    print(f'[Executor] Synthesized minimal trajectory ({len(steps)} step) for {task_id}')
        if not steps:
            raise TaskExecutionError(f'No trajectory steps captured for {task_id}. OpenClaw/PinchBench transcript extraction returned empty steps.')
        score = resolve_shell_task_score(task_id, task_data, steps, task_description or '')
        if self.artifact_dir and steps:
            annotated_path = Path(self.artifact_dir) / 'trajectories' / f'{task_id}_annotated.json'
            annotated_path.parent.mkdir(parents=True, exist_ok=True)
            annotated_path.write_text(json.dumps({'task_id': task_id, 'task_description': task_description, 'steps': [s.to_dict() for s in steps], 'success': score >= 1.0}, ensure_ascii=False, indent=2), encoding='utf-8')
        success = score >= 1.0
        error_step = None
        if not success and steps:
            for i, step in enumerate(steps):
                if step.done and step.reward == 0:
                    error_step = max(0, i - 1)
                    break
        metadata = {'source': 'pinchbench', 'step_provenance': step_provenance, 'native_step_count': len(native_steps), 'extracted_step_count': len(openclaw_steps), 'result_file': str(data.get('file', ''))}
        if openclaw_traj:
            metadata['openclaw_trajectory_steps'] = len(openclaw_traj)
        return Trajectory(task_id=task_id, task_description=task_description, steps=steps, success=success, total_reward=score, error_step=error_step, metadata=metadata)

    def evaluate_with_skills(self, tasks: List[str], skill_bank: Dict[str, Any], model: str='default') -> Dict[str, Any]:
        trajectories = self.execute_tasks(tasks, model)
        if not trajectories:
            return {'success_rate': 0.0, 'avg_score': 0.0, 'sample_size': 0}
        success_count = sum((1 for t in trajectories if t.success))
        total_score = sum((t.total_reward for t in trajectories))
        return {'success_rate': success_count / len(trajectories), 'avg_score': total_score / len(trajectories), 'sample_size': len(trajectories), 'task_results': {t.task_id: {'success': t.success, 'score': t.total_reward} for t in trajectories}}
