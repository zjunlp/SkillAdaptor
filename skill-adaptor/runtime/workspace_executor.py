from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from adapters.errors import TaskExecutionError
from core.agent_trace_resolve import build_steps_from_raw, save_annotated_trajectory
from core.api_env import chat_key_envs, chat_url_envs, first_env
from core.openclaw_hygiene import openclaw_agent_id
from core.step_trace_gate import require_actionable_trace
from core.synthetic_trajectory import maybe_synthesize_minimal
from core.types import Step, Trajectory
from runtime.execution_binding import read_task_markdown
from runtime.harness import AgentHarness, get_harness
from runtime.harness_runners import HarnessRunner, OpenClawHarnessRunner, get_harness_runner
from runtime.workspace_grade import extract_prompt_section, grade_workspace_task
from runtime.workspace_trace import resolve_workspace_trajectory_steps


class WorkspaceExecutor:
    def __init__(
        self,
        workspace: Path | str,
        *,
        artifact_dir: Optional[Path | str] = None,
        harness_name: str = 'openclaw',
        harness: Optional[AgentHarness] = None,
        runner: Optional[HarnessRunner] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.workspace = Path(workspace)
        self.tasks_dir = self.workspace / 'input_task'
        self.artifact_dir = Path(artifact_dir) if artifact_dir else self.workspace / '.skill-adaptor' / 'artifacts'
        self.harness_name = harness_name or os.environ.get('SkillAdaptor_HARNESS', 'openclaw')
        self.harness = harness or get_harness(self.harness_name, project_root=self.workspace)
        self.runner = runner or get_harness_runner(self.harness_name, api_key=api_key, base_url=base_url)
        self.api_key = api_key or first_env(*chat_key_envs())
        self.base_url = base_url or first_env(*chat_url_envs())
        self.model = model or os.environ.get('SkillEvolve_MODEL', 'gpt-4.1')
        self._task_skills: Dict[str, str] = {}
        self._task_skill_ids: Dict[str, List[str]] = {}
        self._task_prompt_prefixes: Dict[str, str] = {}

    def list_tasks(self) -> List[str]:
        if not self.tasks_dir.exists():
            return []
        ids: List[str] = []
        for path in sorted(self.tasks_dir.iterdir()):
            if path.suffix == '.md' and not path.name.startswith('.'):
                ids.append(path.stem)
        return ids

    def set_task_skills(
        self,
        task_skills: Dict[str, str],
        task_skill_ids: Optional[Dict[str, List[str]]] = None,
        skill_objects: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        self._task_skills = dict(task_skills or {})
        self._task_skill_ids = dict(task_skill_ids or {})

    def set_task_prompt_prefixes(self, prefixes: Dict[str, str]) -> None:
        self._task_prompt_prefixes = {k: v for k, v in (prefixes or {}).items() if v and v.strip()}

    def clear_task_skills(self) -> None:
        self._task_skills = {}
        self._task_skill_ids = {}
        self._task_prompt_prefixes = {}
        self.harness.purge_all_injections(benchmark_root=self.workspace)

    def _inject_skills(self, task_id: str) -> None:
        skill_text = self._task_skills.get(task_id, '')
        if skill_text:
            self.harness.inject_skill_text(skill_text, benchmark_root=self.workspace, task_id=task_id)
        else:
            self.harness.clear_skill_injection(benchmark_root=self.workspace, task_id=task_id)

    def _read_task(self, task_id: str) -> tuple[str, str]:
        task_md = read_task_markdown(self.tasks_dir, task_id)
        if not task_md.strip():
            raise TaskExecutionError(f'Missing task brief: {self.tasks_dir / f"{task_id}.md"}')
        prompt = extract_prompt_section(task_md)
        if len(prompt.strip()) < 10:
            raise TaskExecutionError(f'Task {task_id}: prompt too short in {self.tasks_dir / f"{task_id}.md"}')
        prefix = (self._task_prompt_prefixes.get(task_id) or '').strip()
        if prefix:
            prompt = f'{prefix}\n\n{prompt}'
        return task_md, prompt

    def _resolve_agent_id(self, model: str) -> str:
        if os.environ.get('SKILLADAPTOR_SKIP_LIVE_RUN', '').strip().lower() in ('1', 'true', 'yes'):
            return openclaw_agent_id(model, prefix='ws')
        if isinstance(self.runner, OpenClawHarnessRunner):
            return self.runner.ensure_agent(self.workspace, model)
        return openclaw_agent_id(model, prefix='ws')

    def execute_task(self, task_id: str, model: Optional[str] = None, timeout: int = 1200) -> Trajectory:
        effective_model = model or self.model
        task_md, prompt = self._read_task(task_id)
        self._inject_skills(task_id)
        agent_id = self._resolve_agent_id(effective_model)
        run_started = time.time()
        if os.environ.get('SKILLADAPTOR_SKIP_LIVE_RUN', '').strip().lower() not in ('1', 'true', 'yes'):
            run_started = self.runner.run_task(
                task_id=task_id,
                prompt=prompt,
                workspace=self.workspace,
                model=effective_model,
                agent_id=agent_id,
                timeout=timeout,
            )
        raw_steps, merge_label, meta = resolve_workspace_trajectory_steps(
            task_id,
            agent_id=agent_id,
            artifact_dir=self.artifact_dir,
            min_mtime=run_started,
            result_data={'task_id': task_id},
        )
        skills_used = list(self._task_skill_ids.get(task_id, []))
        steps: List[Step] = []
        if raw_steps:
            require_actionable_trace(raw_steps, task_id=task_id, require_tool=True)
            steps = build_steps_from_raw(raw_steps, skills_used=skills_used, step_provenance=merge_label)
        if not steps:
            score_guess = grade_workspace_task(self.workspace, task_id, task_md, [])
            synthetic = maybe_synthesize_minimal(
                task_id=task_id,
                task_description=prompt,
                score=score_guess,
                skills_used=skills_used,
                step_source='workspace_fallback',
            )
            if synthetic:
                steps = synthetic
                merge_label = 'synthetic_minimal'
                print(f'[Workspace] Synthesized minimal trajectory for {task_id} (ALLOW_SYNTHETIC_TRAJECTORY)')
            else:
                hint = meta.get('openclaw_source', 'no trace')
                raise TaskExecutionError(
                    f'No step-level trajectory for {task_id} ({hint}). '
                    'Ensure the agent run emits tool-level steps or set ALLOW_SYNTHETIC_TRAJECTORY=1 for probes.'
                )
        score = grade_workspace_task(self.workspace, task_id, task_md, steps)
        if steps:
            steps[-1].reward = score
            steps[-1].done = True
        success = score >= 1.0
        save_annotated_trajectory(
            self.artifact_dir,
            task_id=task_id,
            task_description=prompt,
            steps=steps,
            success=success,
        )
        print(
            f'[Workspace] Trajectory: {len(steps)} steps ({merge_label}) '
            f'openclaw={meta.get("openclaw_step_count", 0)} cached={meta.get("cached_step_count", 0)}'
        )
        metadata = {
            'source': 'workspace',
            'harness': self.harness_name,
            'step_provenance': merge_label,
            'agent_id': agent_id,
            **meta,
        }
        error_step = None
        if not success and steps:
            error_step = max(0, len(steps) - 1)
        return Trajectory(
            task_id=task_id,
            task_description=prompt,
            steps=steps,
            success=success,
            total_reward=score,
            error_step=error_step,
            metadata=metadata,
        )

    def execute_tasks(self, task_ids: List[str], model: Optional[str] = None) -> List[Trajectory]:
        out: List[Trajectory] = []
        for task_id in task_ids:
            out.append(self.execute_task(task_id, model=model))
        return out
