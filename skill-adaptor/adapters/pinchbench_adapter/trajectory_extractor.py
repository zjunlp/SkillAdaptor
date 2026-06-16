"""OpenClaw Trajectory Extractor for PinchBench."""

from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

def parse_openclaw_transcript(jsonl_path: Path) -> List[Dict]:
    events = []
    if not jsonl_path.exists():
        return events
    with open(jsonl_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                events.append(event)
            except json.JSONDecodeError:
                continue
    return events

def _content_items(msg: Dict) -> List[Dict]:
    content = msg.get('content', [])
    if isinstance(content, str):
        text = content.strip()
        return [{'type': 'text', 'text': text}] if text else []
    if isinstance(content, list):
        return content
    return []

def convert_to_webshop_format(events: List[Dict], task_info: Optional[Dict]=None) -> List[Dict]:
    steps = []
    session_info = {}
    for e in events:
        if e.get('type') == 'session':
            session_info = e
            break
    task_description = ''
    for e in events:
        if e.get('type') == 'message' and e.get('message', {}).get('role') == 'user':
            content = e.get('message', {}).get('content', [])
            if content and isinstance(content[0], dict):
                text = content[0].get('text', '')
                if text and len(text) > 10:
                    task_description = text
                    break
    steps.append({'step': 0, 'type': 'metadata', 'model': task_info.get('model', 'unknown') if task_info else 'unknown', 'task': task_info.get('task_id', 'unknown') if task_info else 'unknown', 'timestamp': session_info.get('timestamp', datetime.now().isoformat()), 'goal': task_description[:500] if task_description else ''})
    current_step = 1
    pending_observation: List[str] = []
    for event in events:
        if event.get('type') != 'message':
            continue
        msg = event.get('message', {})
        role = msg.get('role')
        if role == 'user':
            content = _content_items(msg)
            if content and isinstance(content[0], dict):
                text = content[0].get('text', '')
                if text:
                    pending_observation.append(f'Instruction: {text}')
        elif role == 'assistant':
            content = _content_items(msg)
            tool_calls_in_turn = 0
            for item in content:
                item_type = item.get('type')
                if item_type == 'thinking':
                    thinking = item.get('thinking', '')[:200]
                    if thinking:
                        pending_observation.append(f'[Thinking] {thinking}...')
                elif item_type == 'text':
                    text = item.get('text', '')
                    if text:
                        pending_observation.append(f'[Response] {text[:300]}...')
                elif item_type == 'toolCall':
                    tool_name = item.get('name', '')
                    tool_args = item.get('arguments', {})
                    action = f'{tool_name}({json.dumps(tool_args, ensure_ascii=False)})'
                    observation_text = '\n'.join(pending_observation) if pending_observation else '(No observation)'
                    steps.append({'step': current_step, 'type': 'action', 'observation': observation_text, 'available_actions': {'has_search_bar': False, 'clickables': []}, 'action': action, 'reward': 0.0, 'done': False})
                    current_step += 1
                    pending_observation = []
                    tool_calls_in_turn += 1
            if tool_calls_in_turn == 0 and pending_observation:
                observation_text = '\n'.join(pending_observation)
                steps.append({'step': current_step, 'type': 'action', 'observation': observation_text, 'available_actions': {'has_search_bar': False, 'clickables': []}, 'action': '(assistant response)', 'reward': 0.0, 'done': False})
                current_step += 1
                pending_observation = []
        elif role == 'toolResult':
            content = _content_items(msg)
            if content and isinstance(content[0], dict):
                result_text = content[0].get('text', '')
                if result_text:
                    pending_observation.append(f'[Tool Result] {result_text[:500]}...')
    if steps:
        score = task_info.get('grading', {}).get('mean', 0) if task_info else 0
        steps.append({'step': current_step, 'type': 'final', 'observation': 'Task completed', 'action': '(End)', 'reward': score, 'done': True})
    return steps

def _extract_from_agent_sessions(agent_id: str, task_id: str, result_data: Optional[Dict]=None) -> Optional[List[Dict]]:
    sessions_dir = Path.home() / '.openclaw' / 'agents' / agent_id / 'sessions'
    if not sessions_dir.exists():
        return None
    jsonl_files = sorted(list(sessions_dir.glob(f'{task_id}_*.jsonl')) + list(sessions_dir.glob(f'*{task_id}*.jsonl')), key=lambda p: p.stat().st_mtime, reverse=True)
    for jsonl_file in jsonl_files:
        events = parse_openclaw_transcript(jsonl_file)
        task_info = None
        if result_data:
            if result_data.get('task_id') == task_id:
                task_info = result_data
            else:
                for task in result_data.get('tasks', []):
                    if task.get('task_id') == task_id:
                        task_info = task
                        break
            if task_info is None:
                task_info = result_data
        trajectory = convert_to_webshop_format(events, task_info)
        action_count = len([s for s in trajectory if s.get('type') == 'action'])
        if action_count > 0:
            return trajectory
    return None

def discover_agent_ids_for_task(task_id: str, primary_agent_id: str) -> List[str]:
    ids: List[str] = [primary_agent_id]
    agents_root = Path.home() / '.openclaw' / 'agents'
    if agents_root.exists():
        for agent_dir in agents_root.iterdir():
            if not agent_dir.is_dir():
                continue
            sessions = agent_dir / 'sessions'
            if not sessions.exists():
                continue
            if any(sessions.glob(f'{task_id}_*.jsonl')) or any(sessions.glob(f'*{task_id}*.jsonl')):
                aid = agent_dir.name
                if aid not in ids:
                    ids.append(aid)
    return ids

def extract_trajectory_for_task(agent_id: str, task_id: str, result_data: Optional[Dict]=None) -> Optional[List[Dict]]:
    for aid in discover_agent_ids_for_task(task_id, agent_id):
        trajectory = _extract_from_agent_sessions(aid, task_id, result_data)
        if trajectory:
            return trajectory
    return None

def extract_failure_steps(trajectory: List[Dict]) -> List[int]:
    if not trajectory:
        return []
    failure_steps = []
    for i, step in enumerate(trajectory):
        if step.get('type') != 'action':
            continue
        observation = step.get('observation', '')
        error_indicators = ['error', 'failed', 'failure', 'not found', 'permission denied', 'exit code', 'exception']
        if any((indicator in observation.lower() for indicator in error_indicators)):
            failure_steps.append(i)
    return failure_steps

def save_trajectory(trajectory: List[Dict], output_path: Path, format: str='both') -> None:
    output_path.mkdir(parents=True, exist_ok=True)
    task_id = trajectory[0].get('task', 'unknown') if trajectory else 'unknown'
    if format in ('json', 'both'):
        json_file = output_path / f'{task_id}_trajectory.json'
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(trajectory, f, indent=2, ensure_ascii=False)
    if format in ('jsonl', 'both'):
        jsonl_file = output_path / f'{task_id}_trajectory.jsonl'
        with open(jsonl_file, 'w', encoding='utf-8') as f:
            for step in trajectory:
                f.write(json.dumps(step, ensure_ascii=False) + '\n')
