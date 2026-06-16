"""Merge native benchmark steps with self-extracted OpenClaw / artifact steps."""

from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

def _is_placeholder_action(action: str) -> bool:
    a = (action or '').strip().lower()
    return a in {'', '(no action)', '(end)', '(no transcript captured)'}

def _action_key(action: str) -> str:
    a = (action or '').strip().lower()
    a = re.sub('\\s+', '', a)
    return a[:120]

def steps_from_pinchbench_transcript(transcript: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    raw: List[Dict[str, Any]] = []
    for i, event in enumerate(transcript or []):
        action = event.get('action', '')
        observation = event.get('observation', '')
        if not action and (not observation):
            continue
        skills = event.get('skills') or event.get('skills_used') or []
        raw.append({'index': i, 'observation': observation, 'action': action, 'reward': float(event.get('reward', 0.0) or 0.0), 'done': bool(event.get('done', False)), 'skills_used': list(skills) if skills else [], 'source': 'native_transcript', 'transcript_event': event})
    return raw

def steps_from_openclaw_trajectory(openclaw_traj: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    raw: List[Dict[str, Any]] = []
    step_idx = 0
    for oc_step in openclaw_traj or []:
        if oc_step.get('type') in ('metadata', 'final'):
            continue
        action = oc_step.get('action', '')
        observation = oc_step.get('observation', '')
        if _is_placeholder_action(action) and (not observation):
            continue
        raw.append({'index': step_idx, 'observation': observation, 'action': action, 'reward': float(oc_step.get('reward', 0.0) or 0.0), 'done': bool(oc_step.get('done', False)), 'skills_used': list(oc_step.get('skills_used') or []), 'source': 'openclaw_extracted', 'openclaw_step': oc_step})
        step_idx += 1
    return raw

def load_cached_trajectory_steps(artifact_dir: Optional[Path], task_id: str) -> List[Dict[str, Any]]:
    if not artifact_dir:
        return []
    traj_dir = Path(artifact_dir) / 'trajectories'
    if not traj_dir.exists():
        return []
    candidates = [traj_dir / f'{task_id}_annotated.json', traj_dir / f'{task_id}_trajectory.json', traj_dir / f'{task_id}_trajectory.jsonl']
    for path in candidates:
        if not path.exists():
            continue
        try:
            if path.suffix == '.jsonl':
                rows = []
                for line in path.read_text(encoding='utf-8').splitlines():
                    line = line.strip()
                    if line:
                        rows.append(json.loads(line))
                data = rows
            else:
                data = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(data, dict) and 'steps' in data:
                steps_payload = data['steps']
            elif isinstance(data, list):
                steps_payload = data
            else:
                continue
            if not steps_payload:
                continue
            if isinstance(steps_payload[0], dict) and 'index' in steps_payload[0]:
                return [{'index': s.get('index', i), 'observation': s.get('observation', ''), 'action': s.get('action', ''), 'reward': float(s.get('reward', 0.0) or 0.0), 'done': bool(s.get('done', False)), 'skills_used': list(s.get('skills_used') or []), 'source': 'cached_annotated'} for i, s in enumerate(steps_payload)]
            return steps_from_openclaw_trajectory(steps_payload)
        except (json.JSONDecodeError, OSError, KeyError, TypeError):
            continue
    return []

def _count_actionable(steps: List[Dict[str, Any]]) -> int:
    return sum((1 for s in steps if not _is_placeholder_action(s.get('action', ''))))

def _enrich_observation(native_obs: str, aux_obs: str) -> str:
    n = (native_obs or '').strip()
    a = (aux_obs or '').strip()
    if not a:
        return n
    if not n:
        return a
    if a in n or n in a:
        return n if len(n) >= len(a) else a
    return f'{n}\n---\n[extracted detail]\n{a}'

def _align_auxiliary(native_step: Dict[str, Any], auxiliary: List[Dict[str, Any]], used_aux: set) -> Optional[Dict[str, Any]]:
    key = _action_key(native_step.get('action', ''))
    if not key:
        return None
    best: Optional[Dict[str, Any]] = None
    best_score = 0.0
    for j, aux in enumerate(auxiliary):
        if j in used_aux:
            continue
        aux_key = _action_key(aux.get('action', ''))
        if not aux_key:
            continue
        if key == aux_key:
            return aux
        if key in aux_key or aux_key in key:
            score = min(len(key), len(aux_key)) / max(len(key), len(aux_key))
            if score > best_score:
                best_score = score
                best = aux
    return best

def merge_trajectory_steps(native_steps: List[Dict[str, Any]], auxiliary_steps: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str]:
    native_n = _count_actionable(native_steps)
    aux_n = _count_actionable(auxiliary_steps)
    if native_n == 0 and aux_n == 0:
        return ([], 'empty')
    if native_n == 0:
        merged = [{**s, 'step_provenance': 'extracted_primary'} for s in auxiliary_steps]
        return (merged, 'extracted_primary')
    if aux_n == 0:
        merged = [{**s, 'step_provenance': 'native_primary'} for s in native_steps]
        return (merged, 'native_primary')
    if native_n >= 2:
        used_aux: set = set()
        merged: List[Dict[str, Any]] = []
        for ns in native_steps:
            row = dict(ns)
            row['step_provenance'] = 'native_primary'
            aux = _align_auxiliary(ns, auxiliary_steps, used_aux)
            if aux is not None:
                used_aux.add(auxiliary_steps.index(aux))
                row['observation'] = _enrich_observation(row.get('observation', ''), aux.get('observation', ''))
                row['step_provenance'] = 'native+extracted'
                if not row.get('skills_used') and aux.get('skills_used'):
                    row['skills_used'] = list(aux['skills_used'])
            merged.append(row)
        return (merged, 'native_primary_enriched')
    if native_n <= 1 and aux_n > native_n:
        final_reward = native_steps[-1].get('reward', 0.0) if native_steps else 0.0
        final_done = native_steps[-1].get('done', False) if native_steps else False
        merged = []
        for s in auxiliary_steps:
            row = dict(s)
            row['step_provenance'] = 'extracted_primary_sparse_native'
            merged.append(row)
        if merged:
            merged[-1]['reward'] = final_reward
            merged[-1]['done'] = final_done
        return (merged, 'extracted_primary_sparse_native')
    used_aux: set = set()
    merged = []
    for ns in native_steps:
        row = dict(ns)
        row['step_provenance'] = 'native_primary'
        aux = _align_auxiliary(ns, auxiliary_steps, used_aux)
        if aux is not None:
            row['observation'] = _enrich_observation(row.get('observation', ''), aux.get('observation', ''))
            row['step_provenance'] = 'native+extracted'
        merged.append(row)
    return (merged, 'native_primary_enriched')
