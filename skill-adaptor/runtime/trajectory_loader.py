"""Trajectory loading for OpenClaw / Claude Code plugin workspaces."""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from core.trajectory_step_merge import load_cached_trajectory_steps, merge_trajectory_steps, steps_from_openclaw_trajectory, steps_from_pinchbench_transcript

def build_merged_raw_steps(*, transcript: Optional[List[Dict[str, Any]]]=None, openclaw_traj: Optional[List[Dict[str, Any]]]=None, artifact_dir: Optional[Path]=None, task_id: str='') -> Tuple[List[Dict[str, Any]], str]:
    native = steps_from_pinchbench_transcript(transcript or [])
    auxiliary = steps_from_openclaw_trajectory(openclaw_traj or [])
    if not auxiliary and artifact_dir and task_id:
        auxiliary = load_cached_trajectory_steps(artifact_dir, task_id)
    return merge_trajectory_steps(native, auxiliary)
__all__ = ['build_merged_raw_steps', 'load_cached_trajectory_steps', 'merge_trajectory_steps', 'steps_from_openclaw_trajectory', 'steps_from_pinchbench_transcript']
