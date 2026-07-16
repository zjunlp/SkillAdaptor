"""Claw-Eval executor — OpenClaw harness inject + official claw-eval loop/judge.

Architecture (paper-aligned, do not collapse these layers):

1. **Harness (OpenClaw / Claude / Codex / …)** — prepare runtime, inject SKILL.md
   into OpenClaw workspace (and harness-specific mirrors). This is the SkillAdaptor
   skill-injection surface shared with PinchBench.
2. **claw-eval official agent loop** (`python -m claw_eval.cli run`) — OpenClaw-
   compatible runner that starts mock HTTP services and emits `tool_dispatch`
   traces. Official graders **require** this format; bare OpenClaw npm sessions
   alone cannot score Claw-Eval tasks.
3. **Official judge** — `google/gemini-3-flash-preview` from claw-eval
   `config_general.yaml` (never silently replace with the chat/agent model).
4. **Step pipeline** — JSONL (+ optional OpenClaw session merge) → per-step
   `skills_used` via StepSkillRetriever → Localizer `skills_at_fault`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from adapters.errors import TaskExecutionError
from core.api_env import (
    EMBEDDING_MODEL_VAR,
    chat_key_envs,
    chat_url_envs,
    chat_model_envs,
    embedding_key_envs,
    embedding_url_envs,
    first_env,
    inject_benchmark_child_env,
)
from core.agent_trace_resolve import (
    build_steps_from_raw,
    discover_claw_eval_trace,
    extract_claw_eval_score,
    extract_trace_path_from_stdout,
    resolve_agent_trajectory_steps,
    save_annotated_trajectory,
)
from core.openclaw_agent_setup import prepare_openclaw_for_model
from core.openclaw_hygiene import cleanup_agent_sessions, openclaw_agent_id, require_gateway_running
from core.skill_matcher import SemanticSkillMatcher
from core.step_skill_retriever import StepSkillRetriever
from core.step_trace_gate import require_actionable_trace
from core.types import Skill, Step, Trajectory
from runtime.execution_binding import apply_prompt_prefix
from runtime.harness import AgentHarness, get_harness

from .action_extractor import extract_action_content
from .official_config import (
    OFFICIAL_JUDGE_MODEL,
    build_run_config_payload,
    probe_judge_reachable,
    write_run_config_yaml,
)
from .task_io import read_claw_eval_prompt


class ClawEvalExecutor:
    """OpenClaw-harness skill inject + claw-eval official run/grade + step attribution.

    Skill visibility (harness-first, then claw-eval prompt.skills):
      1. ~/.openclaw/workspace/skills/skill-adaptor-evolved/SKILL.md  (OpenClaw)
      2. <CLAW_EVAL_PATH>/skills/skill-adaptor-evolved/SKILL.md       (claw-eval)
      3. <CLAW_EVAL_PATH>/.skill/SKILL.md + per-task mirror

    Step-level attribution: after JSONL/OpenClaw merge, StepSkillRetriever annotates
    each step's skills_used; Localizer uses skills_at_fault = steps[t*].skills_used.
    """

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
        harness: Optional[AgentHarness] = None,
    ):
        self.claw_eval_path = Path(claw_eval_path)
        self.python_cmd = Path(python_cmd) if python_cmd else None
        self.tasks_dir = self.claw_eval_path / tasks_dir
        self.results_dir = self.claw_eval_path / results_dir
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.artifact_dir = Path(artifact_dir) if artifact_dir else None
        self.api_key = api_key or first_env(*chat_key_envs())
        self.base_url = base_url or first_env(*chat_url_envs())
        self.model = model or first_env(*chat_model_envs()) or 'gpt-4.1'
        self.harness = harness or get_harness('openclaw', project_root=self.claw_eval_path)
        self._task_skills: Dict[str, str] = {}
        self._task_skill_ids: Dict[str, List[str]] = {}
        self._task_skill_objects: Dict[str, Dict[str, Any]] = {}
        self._task_prompt_prefixes: Dict[str, str] = {}
        self._step_retriever: Optional[StepSkillRetriever] = None
        self._skill_bank_dict: Dict[str, Skill] = {}
        self._step_top_k: int = 3

    def set_skill_bank(
        self,
        skill_bank: Dict[str, Skill],
        *,
        top_k: int = 3,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        embedding_model: Optional[str] = None,
    ) -> None:
        """Enable per-step Top-k skill attribution (paper S_t)."""
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

    def set_task_skills(
        self,
        task_skills: Dict[str, str],
        task_skill_ids: Optional[Dict[str, List[str]]] = None,
        skill_objects: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        self._task_skills = dict(task_skills or {})
        self._task_skill_ids = dict(task_skill_ids or {})
        self._task_skill_objects = dict(skill_objects or {})

    def set_task_prompt_prefixes(self, prefixes: Dict[str, str]) -> None:
        self._task_prompt_prefixes = {k: v for k, v in (prefixes or {}).items() if v and v.strip()}

    def clear_task_skills(self) -> None:
        self._task_skills = {}
        self._task_skill_ids = {}
        self._task_skill_objects = {}
        self._task_prompt_prefixes = {}
        self.clear_skill_bank()
        self.purge_all_skill_injections()

    def purge_all_skill_injections(self) -> None:
        self.harness.purge_all_injections(benchmark_root=self.claw_eval_path)
        if self.tasks_dir.exists():
            for skill_md in self.tasks_dir.glob('*/.skill/SKILL.md'):
                try:
                    skill_md.unlink()
                except OSError:
                    pass

    def _skill_md_paths(self, task_id: str) -> list[Path]:
        return [
            self.claw_eval_path / '.skill' / 'SKILL.md',
            self.claw_eval_path / 'skills' / self.OPENCLAW_EVOLVED_SKILL_DIR / 'SKILL.md',
            self.tasks_dir / task_id / '.skill' / 'SKILL.md',
        ]

    def _inject_skills_to_task(self, task_id: str) -> None:
        """Harness-first skill inject, then claw-eval SKILL.md mirrors for prompt.skills."""
        skill_text = self._task_skills.get(task_id, '')
        if not skill_text:
            return
        # Primary: OpenClaw / Claude / Codex harness surface (same as PinchBench).
        try:
            if hasattr(self.harness, 'prepare_runtime'):
                self.harness.prepare_runtime(
                    model=self.model or 'gpt-4.1',
                    api_key=self.api_key,
                    base_url=self.base_url,
                )
            self.harness.inject_skill_text(
                skill_text, benchmark_root=self.claw_eval_path, task_id=task_id
            )
            print(f'[ClawEval] Harness inject ok ({getattr(self.harness, "name", type(self.harness).__name__)})')
        except Exception as exc:
            raise TaskExecutionError(
                f'Harness skill injection failed for {task_id}: {exc}. '
                'OpenClaw gateway must be up; or set agent_harness / fix harness.'
            ) from exc
        for path in self._skill_md_paths(task_id):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(skill_text, encoding='utf-8')

    def _clear_skills_from_task(self, task_id: str) -> None:
        for path in self._skill_md_paths(task_id):
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass
        try:
            self.harness.clear_skill_injection(benchmark_root=self.claw_eval_path, task_id=task_id)
        except Exception:
            pass

    def _write_run_config(self, task_id: str) -> Path:
        """Emit run YAML: agent = SkillAdaptor chat; judge = official claw-eval judge."""
        cfg_dir = self.claw_eval_path / '.skill-adaptor-configs'
        cfg_dir.mkdir(parents=True, exist_ok=True)
        cfg_path = cfg_dir / f'{task_id}_run.yaml'
        skill_text = (self._task_skills.get(task_id) or '').strip()
        skill_rel = 'skills/skill-adaptor-evolved/SKILL.md'
        prefix_parts: list[str] = []
        if self._task_prompt_prefixes.get(task_id):
            prefix_parts.append(self._task_prompt_prefixes[task_id].strip())
        if skill_text:
            body = skill_text[:4500]
            prefix_parts.append(
                '# SkillAdaptor evolved skills (mandatory when relevant)\n'
                'Follow the procedures below. Prefer these over ad-hoc guesses.\n\n'
                f'{body}\n'
            )
        payload, warnings = build_run_config_payload(
            claw_eval_path=self.claw_eval_path,
            agent_api_key=self.api_key,
            agent_base_url=self.base_url,
            agent_model=self.model,
            skill_text=skill_text,
            skill_rel_path=skill_rel,
            system_prompt_prefix='\n\n'.join(prefix_parts),
            judge_enabled=self._use_judge(),
        )
        for w in warnings:
            print(f'[ClawEval] config: {w}')
        judge = payload.get('judge') or {}
        print(
            f'[ClawEval] judge model_id={judge.get("model_id")} '
            f'enabled={judge.get("enabled")} '
            f'(official default={OFFICIAL_JUDGE_MODEL})'
        )
        write_run_config_yaml(cfg_path, payload)
        return cfg_path

    def _skip_openclaw(self) -> bool:
        """Paper path requires OpenClaw gateway. Opt-out only for offline probes."""
        return os.environ.get('CLAW_EVAL_SKIP_OPENCLAW', '').strip().lower() in ('1', 'true', 'yes')

    def _strict_judge(self) -> bool:
        """Refuse to run when official judge endpoint is unreachable (default on)."""
        return os.environ.get('CLAW_EVAL_STRICT_JUDGE', '1').strip().lower() not in (
            '0',
            'false',
            'no',
        )

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

    def _env(self, task_id: str) -> Dict[str, str]:
        env = os.environ.copy()
        inject_benchmark_child_env(env, api_key=self.api_key, base_url=self.base_url, model=self.model)
        if self.api_key:
            env['CLAW_EVAL_MODEL_API_KEY'] = self.api_key
        if self.base_url:
            env['CLAW_EVAL_MODEL_BASE_URL'] = self.base_url
        if self.model:
            env['CLAW_EVAL_MODEL_ID'] = self.model
        env['no_proxy'] = 'localhost,127.0.0.1'
        env['NO_PROXY'] = 'localhost,127.0.0.1'
        # Shared env key with PinchBench (consumed when the child harness reads it).
        env = apply_prompt_prefix(env, task_id, self._task_prompt_prefixes)
        return env

    def _read_task_description(self, task_id: str) -> str:
        prompt = read_claw_eval_prompt(self.tasks_dir, task_id)
        return prompt if prompt else task_id

    def _resolve_trace_path(self, task_id: str, stdout: str, run_started: float) -> Optional[Path]:
        trace_path = extract_trace_path_from_stdout(stdout)
        if trace_path and trace_path.exists():
            return trace_path
        if trace_path and not trace_path.is_absolute():
            candidate = self.claw_eval_path / trace_path
            if candidate.exists():
                return candidate
        return discover_claw_eval_trace(self.claw_eval_path, task_id, min_mtime=run_started)

    def _annotate_step_skills(
        self,
        task_id: str,
        task_description: str,
        raw_steps: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Per-step Top-k skills_used (paper S_t); fall back to task injection list."""
        task_level = list(self._task_skill_ids.get(task_id, []))
        steps_for_annotation = []
        for rs in raw_steps:
            action = extract_action_content(rs.get('action', ''))
            if action == '[thinking]':
                action = str(rs.get('action', ''))
            steps_for_annotation.append(
                {
                    'observation': rs.get('observation', ''),
                    'action': action,
                    'type': 'action',
                    'skills_used': list(rs.get('skills_used') or []),
                }
            )
        enriched = steps_for_annotation
        if self._step_retriever and self._skill_bank_dict and steps_for_annotation:
            emb_annotated = self._step_retriever.annotate_trajectory_steps(
                task_description, steps_for_annotation, self._skill_bank_dict
            )
            enriched = []
            for i, emb_step in enumerate(emb_annotated):
                native_ids = steps_for_annotation[i].get('skills_used') or []
                emb_ids = emb_step.get('skills_used') or []
                merged = dict(emb_step)
                merged['skills_used'] = native_ids if native_ids else emb_ids
                enriched.append(merged)
            print(
                f'[ClawEval] Per-step Top-{self._step_top_k} skills_used via embedding '
                f'({len(self._skill_bank_dict)} skills in bank)'
            )
        out: List[Dict[str, Any]] = []
        for i, rs in enumerate(raw_steps):
            copy = dict(rs)
            cleaned = extract_action_content(rs.get('action', ''))
            if cleaned and cleaned != '[thinking]':
                copy['action'] = cleaned
            step_skills = enriched[i].get('skills_used', task_level) if i < len(enriched) else task_level
            if not step_skills:
                step_skills = task_level
            copy['skills_used'] = list(step_skills)
            out.append(copy)
        return out

    def _save_raw_trace_artifact(
        self,
        task_id: str,
        *,
        raw_steps: List[Dict[str, Any]],
        merge_label: str,
        meta: Dict[str, Any],
        score: float,
        passed: bool,
    ) -> None:
        if not self.artifact_dir:
            return
        out_dir = Path(self.artifact_dir) / 'trajectories'
        out_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            'task_id': task_id,
            'merge_label': merge_label,
            'score': score,
            'passed': passed,
            'meta': meta,
            'raw_steps': raw_steps,
        }
        (out_dir / f'{task_id}_raw_steps.json').write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8'
        )

    def _allow_synthetic(self) -> bool:
        return os.environ.get('ALLOW_SYNTHETIC_TRAJECTORY', '').strip().lower() in ('1', 'true', 'yes')

    def _use_judge(self) -> bool:
        # Paper path requires the claw-eval grader. Opt-out only for offline probes.
        return os.environ.get('CLAW_EVAL_NO_JUDGE', '').strip().lower() not in ('1', 'true', 'yes')

    def _parse_scores_from_stdout(self, stdout: str) -> Dict[str, Any]:
        """claw-eval ``cli run`` prints scores but often does not append grading_result."""
        import re

        out: Dict[str, Any] = {'found': False}
        if not stdout:
            return out
        m = re.search(r'task_score:\s*([0-9.]+)', stdout)
        if m:
            out['task_score'] = float(m.group(1))
            out['found'] = True
        m = re.search(r'passed:\s*(True|False|true|false)', stdout)
        if m:
            out['passed'] = m.group(1).lower() == 'true'
            out['found'] = True
        return out

    def _ensure_grading_result(
        self,
        task_id: str,
        trace_path: Optional[Path],
        run_cfg: Path,
        stdout: str,
    ) -> Dict[str, Any]:
        """Prefer grading_result in JSONL; else parse stdout; else re-run ``cli grade``.

        Stock claw-eval local ``cli run`` grades in-process and prints scores but does
        not always append ``grading_result`` to the JSONL (unlike sandbox mode).

        Important: an official score of 0.0 / passed=False is valid and must be kept
        (``found=True``); do not treat it as "missing grade".
        """
        score_info = (
            extract_claw_eval_score(trace_path)
            if trace_path
            else {'task_score': 0.0, 'passed': False, 'found': False}
        )
        if score_info.get('found'):
            return {
                'task_score': float(score_info.get('task_score', 0.0) or 0.0),
                'passed': bool(score_info.get('passed', False)),
                'source': 'jsonl',
                'found': True,
            }

        parsed = self._parse_scores_from_stdout(stdout or '')
        if parsed.get('found'):
            task_score = float(parsed.get('task_score', 0.0) or 0.0)
            passed = bool(parsed.get('passed', False))
            print(
                f'[ClawEval] score from run stdout: '
                f'task_score={task_score} passed={passed} '
                '(JSONL missing grading_result — claw-eval local run quirk)'
            )
            if trace_path and trace_path.exists():
                self._append_grading_result(trace_path, task_id, task_score, passed)
            return {
                'task_score': task_score,
                'passed': passed,
                'source': 'stdout',
                'found': True,
            }

        if not self._use_judge() or not trace_path or not trace_path.exists():
            return {
                'task_score': float(score_info.get('task_score', 0.0) or 0.0),
                'passed': bool(score_info.get('passed', False)),
                'source': 'missing',
                'found': False,
            }
        task_dir = self.tasks_dir / task_id
        grade_cmd = [
            self._python(),
            '-m',
            'claw_eval.cli',
            'grade',
            '--trace',
            str(trace_path),
            '--task',
            str(task_dir),
            '--config',
            str(run_cfg),
        ]
        print(f'[ClawEval] re-grade via claw_eval.cli grade → {trace_path.name}')
        try:
            grade_result = subprocess.run(
                grade_cmd,
                cwd=self.claw_eval_path,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=600,
                env=self._env(task_id),
            )
        except subprocess.TimeoutExpired:
            print('[ClawEval] WARNING: re-grade timed out')
            return {'task_score': 0.0, 'passed': False, 'source': 'regrade_timeout', 'found': False}

        score_info = extract_claw_eval_score(trace_path)
        if score_info.get('found'):
            task_score = float(score_info.get('task_score', 0.0) or 0.0)
            passed = bool(score_info.get('passed', False))
            self._append_grading_result(trace_path, task_id, task_score, passed)
            return {
                'task_score': task_score,
                'passed': passed,
                'source': 'regrade',
                'found': True,
            }
        parsed = self._parse_scores_from_stdout(
            (grade_result.stdout or '') + '\n' + (grade_result.stderr or '')
        )
        if parsed.get('found'):
            task_score = float(parsed.get('task_score', 0.0) or 0.0)
            passed = bool(parsed.get('passed', False))
            self._append_grading_result(trace_path, task_id, task_score, passed)
            return {
                'task_score': task_score,
                'passed': passed,
                'source': 'regrade_stdout',
                'found': True,
            }
        return {'task_score': 0.0, 'passed': False, 'source': 'regrade_empty', 'found': False}

    def _append_grading_result(
        self,
        trace_path: Path,
        task_id: str,
        task_score: float,
        passed: bool,
    ) -> None:
        """Persist score into JSONL when claw-eval CLI only printed it."""
        try:
            existing = extract_claw_eval_score(trace_path)
            if existing.get('found'):
                return
            # Prefer grading_result event shape used by claw-eval.
            import uuid

            events = []
            for line in trace_path.read_text(encoding='utf-8').splitlines():
                if line.strip():
                    events.append(json.loads(line))
            trace_id = ''
            for ev in events:
                if ev.get('type') == 'trace_start':
                    trace_id = str(ev.get('trace_id') or '')
                    break
            payload = {
                'type': 'grading_result',
                'trace_id': trace_id or str(uuid.uuid4()),
                'task_id': task_id,
                'task_score': task_score,
                'passed': passed,
                'scores': {
                    'completion': task_score,
                    'robustness': 0.0,
                    'communication': 0.0,
                    'safety': 1.0,
                },
                'source': 'skill-adaptor-regrade',
            }
            with trace_path.open('a', encoding='utf-8') as fh:
                fh.write(json.dumps(payload, ensure_ascii=False) + '\n')
            print(f'[ClawEval] appended grading_result task_score={task_score:.3f} passed={passed}')
        except Exception as exc:
            print(f'[ClawEval] WARNING: could not append grading_result: {exc}')

    def execute_task(self, task_id: str, timeout: int = 1800) -> Trajectory:
        task_dir = self.tasks_dir / task_id
        if not (task_dir / 'task.yaml').exists():
            raise TaskExecutionError(f'Missing task.yaml for Claw-Eval task: {task_id}')

        effective_model = self.model
        agent_id = openclaw_agent_id(effective_model)
        # Paper path: OpenClaw gateway + harness. Opt-out: CLAW_EVAL_SKIP_OPENCLAW=1.
        if not self._skip_openclaw():
            prepare_openclaw_for_model(
                effective_model,
                api_key=self.api_key,
                base_url=self.base_url,
                fix_main_auth=True,
            )
            require_gateway_running(max_wait_s=20.0)
            cleanup_agent_sessions(agent_id)
            print('[ClawEval] OpenClaw gateway ready (harness base)')
        else:
            print('[ClawEval] WARNING: CLAW_EVAL_SKIP_OPENCLAW=1 — harness gateway skipped')

        if self._task_skills.get(task_id):
            self._inject_skills_to_task(task_id)
        else:
            self._clear_skills_from_task(task_id)

        run_cfg = self._write_run_config(task_id)
        if self._use_judge() and self._strict_judge():
            try:
                import yaml  # type: ignore

                payload = yaml.safe_load(run_cfg.read_text(encoding='utf-8')) or {}
            except Exception:
                payload = {}
            judge = payload.get('judge') or {}
            ok, detail = probe_judge_reachable(judge)
            if not ok:
                raise TaskExecutionError(
                    f'Official judge unreachable ({judge.get("model_id")}): {detail}. '
                    'Set CLAW_EVAL_JUDGE_API_KEY + CLAW_EVAL_JUDGE_BASE_URL (or OPENROUTER_API_KEY) '
                    f'to an endpoint that serves {OFFICIAL_JUDGE_MODEL}. '
                    'Do not silently substitute the chat model. '
                    'Debug only: CLAW_EVAL_STRICT_JUDGE=0 or CLAW_EVAL_NO_JUDGE=1.'
                )
            print(f'[ClawEval] official judge probe: {detail}')

        cmd = [
            self._python(),
            '-m',
            'claw_eval.cli',
            'run',
            '--task',
            str(task_dir),
            '--model',
            effective_model,
            '--config',
            str(run_cfg),
        ]
        # Paper Table 1 uses Pass@3 → CLAW_EVAL_TRIALS=3. Micro/local stays 1 (default).
        trials_raw = (os.environ.get('CLAW_EVAL_TRIALS') or '1').strip()
        try:
            trials = max(1, int(trials_raw))
        except ValueError:
            trials = 1
        if trials > 1:
            cmd.extend(['--trials', str(trials)])
            print(
                f'[ClawEval] trials={trials} — claw-eval runs Pass@{trials}; '
                'SkillAdaptor evolution uses the graded score from this run '
                '(aggregate Pass@k separately via adapters.claw_eval_adapter.pass_at_k). '
                'Prefer CLAW_EVAL_TRIALS=1 while evolving skills.'
            )
        if self.api_key:
            cmd.extend(['--api-key', self.api_key])
        if self.base_url:
            cmd.extend(['--base-url', self.base_url])
        if not self._use_judge():
            cmd.append('--no-judge')
            print('[ClawEval] WARNING: CLAW_EVAL_NO_JUDGE=1 — scores incomplete (debug only)')
        print(f'[ClawEval] config={run_cfg.name} skills_injected={bool(self._task_skills.get(task_id))}')

        run_started = time.time()
        try:
            result = subprocess.run(
                cmd,
                cwd=self.claw_eval_path,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=timeout,
                env=self._env(task_id),
            )
        except subprocess.TimeoutExpired as exc:
            raise TaskExecutionError(f'Claw-Eval task {task_id} timed out after {timeout}s') from exc

        if result.returncode != 0:
            # Never echo raw argv (may contain --api-key); keep stderr tail only.
            stderr_tail = (result.stderr or '')[:500]
            raise TaskExecutionError(
                f'Claw-Eval task {task_id} failed (exit {result.returncode}): {stderr_tail}'
            )

        trace_path = self._resolve_trace_path(task_id, result.stdout or '', run_started)
        score_info = self._ensure_grading_result(
            task_id, trace_path, run_cfg, result.stdout or ''
        )
        task_score = float(score_info.get('task_score', 0.0) or 0.0)
        passed = bool(score_info.get('passed', False))
        print(
            f'[ClawEval] score source={score_info.get("source")} '
            f'task_score={task_score:.3f} passed={passed}'
        )
        result_data = {
            'task_id': task_id,
            'passed': passed,
            'task_score': task_score,
            'stdout_tail': (result.stdout or '')[-800:],
        }
        raw_steps, merge_label, meta = resolve_agent_trajectory_steps(
            task_id,
            agent_id=agent_id,
            claw_eval_trace=trace_path,
            result_data=result_data,
            artifact_dir=self.artifact_dir,
        )
        task_description = self._read_task_description(task_id)
        if len(task_description.strip()) < 10:
            raise TaskExecutionError(
                f'Task {task_id}: prompt missing or too short after task.yaml parse '
                f'({len(task_description)} chars). Check nested prompt.text.'
            )

        task_level_skills = list(self._task_skill_ids.get(task_id, []))
        grading_found = bool(score_info.get('found')) or self._use_judge()
        if raw_steps:
            require_actionable_trace(raw_steps, task_id=task_id, require_tool=True)
            raw_steps = self._annotate_step_skills(task_id, task_description, raw_steps)
            # Always stamp official grader score on the final step when grade is available
            # (including legitimate 0.0 / passed=False).
            if raw_steps and grading_found:
                raw_steps[-1]['reward'] = task_score
                raw_steps[-1]['done'] = True

        self._save_raw_trace_artifact(
            task_id,
            raw_steps=raw_steps,
            merge_label=merge_label,
            meta={**meta, 'task_score': task_score, 'passed': passed, 'trace_path': str(trace_path or '')},
            score=task_score,
            passed=passed,
        )

        steps = build_steps_from_raw(raw_steps, skills_used=task_level_skills, step_provenance=merge_label)

        if not steps:
            if self._allow_synthetic():
                # Probe-only path: never mark synthetic as success for paper metrics.
                steps = [
                    Step(
                        index=0,
                        observation=task_description[:500],
                        action='(claw-eval run)',
                        reward=0.0,
                        done=True,
                        skills_used=task_level_skills,
                        metadata={'step_provenance': 'synthetic_minimal', 'step_source': 'claw_eval_fallback'},
                    )
                ]
                print(f'[ClawEval] Synthesized minimal trajectory for {task_id} (ALLOW_SYNTHETIC_TRAJECTORY)')
            else:
                hint = f'trace={trace_path}' if trace_path else 'no trace file found'
                raise TaskExecutionError(
                    f'No step-level trajectory for {task_id} ({hint}). '
                    'Ensure claw-eval writes JSONL traces with tool calls.'
                )

        # Official grader is authoritative whenever judge ran / score was found
        # (including score=0). Never let heuristic step rewards invent success.
        if grading_found:
            total_reward = task_score
            success = bool(passed) or task_score >= 1.0
            steps[-1].reward = total_reward
            steps[-1].done = True
        else:
            # CLAW_EVAL_NO_JUDGE debug only
            total_reward = float(steps[-1].reward) if steps else 0.0
            success = bool(steps[-1].done and total_reward >= 1.0)
            print('[ClawEval] WARNING: no official grade found — using step heuristic (debug)')

        print(
            f'[ClawEval] Trajectory: {len(steps)} steps ({merge_label}) '
            f'score={total_reward:.3f} passed={success} '
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
            'task_score': total_reward,
            'passed': success,
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
