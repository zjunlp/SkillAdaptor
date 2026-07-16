"""Resolve step-level trajectories from agent run artifacts (Claw-Eval, OpenClaw, caches)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from adapters.pinchbench_adapter.trajectory_extractor import extract_trajectory_for_task
from core.trajectory_step_merge import (
    load_cached_trajectory_steps,
    merge_trajectory_steps,
    steps_from_openclaw_trajectory,
)
from core.types import Step


def extract_trace_path_from_stdout(stdout: str) -> Optional[Path]:
    for line in reversed((stdout or '').splitlines()):
        stripped = line.strip()
        if stripped.lower().startswith('trace:'):
            return Path(stripped.split(':', 1)[1].strip())
    return None


def discover_claw_eval_trace(claw_eval_root: Path, task_id: str, *, min_mtime: float = 0.0) -> Optional[Path]:
    traces_root = claw_eval_root / 'traces'
    if not traces_root.exists():
        return None
    candidates: List[Path] = []
    for path in traces_root.rglob('*.jsonl'):
        if task_id not in path.name:
            continue
        if min_mtime and path.stat().st_mtime < min_mtime - 1.0:
            continue
        candidates.append(path)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def parse_jsonl_events(path: Path) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    if not path.exists():
        return events
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _text_from_blocks(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ''
    parts: List[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get('type') == 'text' and block.get('text'):
            parts.append(str(block['text']))
    return '\n'.join(parts).strip()


def steps_from_claw_eval_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert Claw-Eval JSONL trace events to webshop-style steps.

    Observation semantics: state *before* the action. When one assistant turn
    emits multiple parallel ``tool_use`` blocks, every tool step in that turn
    shares the same pre-turn observation (do not clear pending between them).
    Tool results land in ``pending_obs`` for the *next* turn.
    """
    raw_steps: List[Dict[str, Any]] = []
    pending_obs: List[str] = []
    step_idx = 0
    final_score = 0.0
    final_done = False

    for ev in events:
        etype = ev.get('type')
        if etype == 'message':
            msg = ev.get('message') or {}
            role = msg.get('role')
            content = msg.get('content') or []
            blocks = content if isinstance(content, list) else []
            if role == 'user':
                for block in blocks:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get('type')
                    if btype == 'tool_result':
                        txt = _text_from_blocks(block.get('content'))
                        if txt:
                            pending_obs.append(f'[Tool Result] {txt[:500]}')
                    elif btype == 'text' and block.get('text'):
                        text = str(block['text'])
                        if text.strip():
                            pending_obs.append(text[:500])
            elif role == 'assistant':
                pre_obs = '\n'.join(pending_obs) if pending_obs else '(No observation)'
                tool_count = 0
                text_bits: List[str] = []
                for block in blocks:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get('type')
                    if btype == 'tool_use':
                        action = f"{block.get('name')}({json.dumps(block.get('input', {}), ensure_ascii=False)})"
                        raw_steps.append(
                            {
                                'step': step_idx,
                                'type': 'action',
                                'observation': pre_obs,
                                'action': action,
                                'reward': 0.0,
                                'done': False,
                            }
                        )
                        step_idx += 1
                        tool_count += 1
                    elif btype == 'text' and block.get('text'):
                        text_bits.append(f"[Response] {str(block['text'])[:300]}")
                if tool_count:
                    # Results for this turn arrive as tool_dispatch / tool_result next.
                    pending_obs = []
                elif text_bits:
                    observation = '\n'.join(pending_obs + text_bits) if pending_obs else '\n'.join(text_bits)
                    raw_steps.append(
                        {
                            'step': step_idx,
                            'type': 'action',
                            'observation': observation or '(No observation)',
                            'action': '(assistant response)',
                            'reward': 0.0,
                            'done': False,
                        }
                    )
                    step_idx += 1
                    pending_obs = []
                elif pending_obs and not tool_count:
                    observation = '\n'.join(pending_obs)
                    raw_steps.append(
                        {
                            'step': step_idx,
                            'type': 'action',
                            'observation': observation,
                            'action': '(assistant response)',
                            'reward': 0.0,
                            'done': False,
                        }
                    )
                    step_idx += 1
                    pending_obs = []
        elif etype == 'tool_dispatch':
            body = ev.get('response_body')
            if body is not None:
                snippet = json.dumps(body, ensure_ascii=False) if isinstance(body, (dict, list)) else str(body)
                pending_obs.append(f'[Tool Dispatch] {snippet[:500]}')
        elif etype == 'trace_end':
            final_score = float(ev.get('task_score', 0.0) or 0.0)
            final_done = bool(ev.get('passed', final_score >= 1.0))
        elif etype == 'grading_result':
            final_score = float(ev.get('task_score', final_score) or final_score)
            final_done = bool(ev.get('passed', final_done))

    if raw_steps:
        raw_steps[-1]['reward'] = final_score
        raw_steps[-1]['done'] = final_done
    return raw_steps


def steps_from_claw_eval_jsonl(path: Path) -> List[Dict[str, Any]]:
    return steps_from_claw_eval_events(parse_jsonl_events(path))


def extract_claw_eval_score(trace_path: Optional[Path]) -> Dict[str, Any]:
    """Read official grader score from a Claw-Eval JSONL trace.

    ``found=True`` when a grading event actually carried score/passed fields
    (including legitimate zeros). Callers must not treat found=False the same
    as score=0.
    """
    out: Dict[str, Any] = {'task_score': 0.0, 'passed': False, 'found': False}
    if not trace_path or not Path(trace_path).exists():
        return out
    events = parse_jsonl_events(Path(trace_path))
    for ev in events:
        etype = ev.get('type')
        if etype in ('trace_end', 'grading_result'):
            has_score = 'task_score' in ev
            has_passed = 'passed' in ev
            if not has_score and not has_passed:
                continue
            out['found'] = True
            if has_score:
                out['task_score'] = float(ev.get('task_score') or 0.0)
            if has_passed:
                out['passed'] = bool(ev.get('passed'))
            elif float(out['task_score']) >= 1.0:
                out['passed'] = True
    return out


def resolve_agent_trajectory_steps(
    task_id: str,
    *,
    agent_id: str,
    claw_eval_trace: Optional[Path] = None,
    result_data: Optional[Dict[str, Any]] = None,
    artifact_dir: Optional[Path] = None,
) -> Tuple[List[Dict[str, Any]], str, Dict[str, Any]]:
    """Merge Claw-Eval trace, OpenClaw session extract, and cached steps into raw step dicts."""
    native_steps: List[Dict[str, Any]] = []
    auxiliary_steps: List[Dict[str, Any]] = []
    meta: Dict[str, Any] = {'task_id': task_id}

    if claw_eval_trace and claw_eval_trace.exists():
        claw_webshop = steps_from_claw_eval_jsonl(claw_eval_trace)
        native_steps = steps_from_openclaw_trajectory(claw_webshop)
        meta['claw_eval_trace'] = str(claw_eval_trace)
        meta['claw_eval_step_count'] = len(native_steps)

    openclaw_traj = extract_trajectory_for_task(agent_id, task_id, result_data)
    if openclaw_traj:
        oc_steps = steps_from_openclaw_trajectory(openclaw_traj)
        meta['openclaw_step_count'] = len(oc_steps)
        if native_steps:
            auxiliary_steps = oc_steps
        else:
            native_steps = oc_steps

    cached = load_cached_trajectory_steps(artifact_dir, task_id)
    if cached:
        meta['cached_step_count'] = len(cached)
        if not native_steps:
            native_steps = cached
        elif not auxiliary_steps:
            auxiliary_steps = cached

    raw_steps, label = merge_trajectory_steps(native_steps, auxiliary_steps)
    meta['merge_label'] = label
    return raw_steps, label, meta


def build_steps_from_raw(
    raw_steps: List[Dict[str, Any]],
    *,
    skills_used: List[str],
    step_provenance: str,
) -> List[Step]:
    """Build ``Step`` objects; prefer per-step ``skills_used`` when present on raw rows."""
    steps: List[Step] = []
    for i, rs in enumerate(raw_steps):
        step_skills = rs.get('skills_used')
        if step_skills:
            resolved_skills = list(step_skills)
        else:
            resolved_skills = list(skills_used)
        steps.append(
            Step(
                index=int(rs.get('index', i)),
                observation=str(rs.get('observation', '')),
                action=str(rs.get('action', '')),
                reward=float(rs.get('reward', 0.0) or 0.0),
                done=bool(rs.get('done', False)),
                skills_used=resolved_skills,
                metadata={
                    'step_provenance': rs.get('step_provenance', step_provenance),
                    'step_source': rs.get('source', 'merged'),
                },
            )
        )
    return steps


def save_annotated_trajectory(
    artifact_dir: Optional[Path],
    *,
    task_id: str,
    task_description: str,
    steps: List[Step],
    success: bool,
) -> None:
    if not artifact_dir or not steps:
        return
    out = Path(artifact_dir) / 'trajectories' / f'{task_id}_annotated.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'task_id': task_id,
        'task_description': task_description,
        'steps': [s.to_dict() for s in steps],
        'success': success,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
