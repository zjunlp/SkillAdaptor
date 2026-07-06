from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from adapters.pinchbench_adapter.trajectory_extractor import (
    convert_to_webshop_format,
    extract_trajectory_for_task,
    parse_openclaw_transcript,
)
from core.agent_trace_resolve import steps_from_claw_eval_jsonl
from core.trajectory_step_merge import (
    load_cached_trajectory_steps,
    merge_trajectory_steps,
    steps_from_openclaw_trajectory,
)


def discover_latest_openclaw_session(agent_id: str, *, min_mtime: float = 0.0) -> Optional[Path]:
    sessions_dir = Path.home() / '.openclaw' / 'agents' / agent_id / 'sessions'
    if not sessions_dir.exists():
        normalized = Path.home() / '.openclaw' / 'agents' / agent_id.replace(':', '-') / 'sessions'
        if normalized.exists():
            sessions_dir = normalized
        else:
            return None
    candidates: List[Path] = []
    for pattern in ('*.jsonl', '*.trajectory.jsonl'):
        for path in sessions_dir.glob(pattern):
            if min_mtime and path.stat().st_mtime < min_mtime - 1.0:
                continue
            if path.name.endswith('.lock'):
                continue
            candidates.append(path)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def steps_from_session_file(path: Path, task_id: str) -> List[Dict[str, Any]]:
    if path.suffix == '.jsonl' and 'claw' in path.name.lower():
        try:
            claw_steps = steps_from_claw_eval_jsonl(path)
            if claw_steps:
                return steps_from_openclaw_trajectory(claw_steps)
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    events = parse_openclaw_transcript(path)
    if not events:
        return []
    traj = convert_to_webshop_format(events, {'task_id': task_id})
    return steps_from_openclaw_trajectory(traj)


def resolve_workspace_trajectory_steps(
    task_id: str,
    *,
    agent_id: str,
    artifact_dir: Optional[Path] = None,
    min_mtime: float = 0.0,
    result_data: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], str, Dict[str, Any]]:
    meta: Dict[str, Any] = {'task_id': task_id}
    native_steps: List[Dict[str, Any]] = []
    auxiliary_steps: List[Dict[str, Any]] = []

    openclaw_traj = extract_trajectory_for_task(agent_id, task_id, result_data)
    if openclaw_traj:
        native_steps = steps_from_openclaw_trajectory(openclaw_traj)
        meta['openclaw_step_count'] = len(native_steps)
        meta['openclaw_source'] = 'task_id_match'

    if not native_steps:
        latest = discover_latest_openclaw_session(agent_id, min_mtime=min_mtime)
        if latest:
            native_steps = steps_from_session_file(latest, task_id)
            meta['openclaw_step_count'] = len(native_steps)
            meta['openclaw_source'] = str(latest)
            if artifact_dir and native_steps:
                traj_dir = Path(artifact_dir) / 'trajectories'
                traj_dir.mkdir(parents=True, exist_ok=True)
                dest = traj_dir / f'{task_id}_trajectory.jsonl'
                if not dest.exists():
                    with dest.open('w', encoding='utf-8') as fh:
                        for row in native_steps:
                            fh.write(json.dumps(row, ensure_ascii=False) + '\n')

    cached = load_cached_trajectory_steps(artifact_dir, task_id)
    if cached:
        meta['cached_step_count'] = len(cached)
        if not native_steps:
            native_steps = cached
        else:
            auxiliary_steps = cached

    raw_steps, label = merge_trajectory_steps(native_steps, auxiliary_steps)
    meta['merge_label'] = label
    return raw_steps, label, meta
