"""PinchBench Transcript Parser"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from core.types import Trajectory, Step

class TranscriptParser:

    def __init__(self, transcripts_dir: Path | str):
        self.transcripts_dir = Path(transcripts_dir)

    def parse_transcript(self, transcript_path: Path | str) -> Optional[Trajectory]:
        path = Path(transcript_path)
        if not path.exists():
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return self._convert_transcript(data, path.stem)
        except (json.JSONDecodeError, KeyError) as e:
            print(f'Error parsing {path}: {e}')
            return None

    def parse_all_transcripts(self) -> List[Trajectory]:
        trajectories = []
        if not self.transcripts_dir.exists():
            return trajectories
        for transcript_file in self.transcripts_dir.glob('*_transcript.json'):
            traj = self.parse_transcript(transcript_file)
            if traj:
                trajectories.append(traj)
        return trajectories

    def _convert_transcript(self, data: Dict[str, Any], task_id: str) -> Trajectory:
        events = data.get('events', [])
        steps = []
        for i, event in enumerate(events):
            step = self._convert_event(event, i)
            steps.append(step)
        success = False
        total_reward = 0.0
        error_step = None
        if events:
            final_event = events[-1]
            total_reward = final_event.get('score', 0)
            success = total_reward >= 1.0
            if not success:
                for i, event in enumerate(events):
                    if event.get('error') or event.get('type') == 'error':
                        error_step = max(0, i - 1)
                        break
        return Trajectory(task_id=task_id, task_description=data.get('task_description', task_id), steps=steps, success=success, total_reward=total_reward, error_step=error_step, metadata={'source': 'pinchbench_transcript', 'transcript_path': str(data.get('path', ''))})

    def _convert_event(self, event: Dict[str, Any], index: int) -> Step:
        return Step(index=index, observation=event.get('observation', ''), action=event.get('action', ''), reward=event.get('reward', 0.0), done=event.get('done', False), skills_used=event.get('skills', []), metadata={'event_type': event.get('type', 'unknown'), 'timestamp': event.get('timestamp')})

    def extract_failure_patterns(self, trajectories: List[Trajectory]) -> List[Dict[str, Any]]:
        patterns = []
        for traj in trajectories:
            if traj.success:
                continue
            fault_step = traj.get_fault_step()
            if not fault_step:
                continue
            pattern = {'task_id': traj.task_id, 'step_index': fault_step.index, 'observation': fault_step.observation[:200], 'action': fault_step.action, 'observation_keywords': self._extract_keywords(fault_step.observation)}
            patterns.append(pattern)
        return patterns

    def _extract_keywords(self, text: str) -> List[str]:
        import re
        words = re.findall('\\b[a-zA-Z]{4,}\\b', text.lower())
        stopwords = {'with', 'from', 'they', 'have', 'this', 'that', 'will', 'your', 'been', 'were', 'said', 'each'}
        keywords = [w for w in words if w not in stopwords]
        seen = set()
        unique = []
        for k in keywords:
            if k not in seen:
                seen.add(k)
                unique.append(k)
        return unique[:10]
