"""Skill-Injecting Executor for Claw-Eval"""

from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.real_llm_client import RealLLMClient, LLMConfigError
from core.skill_tracker import SkillUsageTracker, StepSkillTracker
from core.types import Skill, Step, Trajectory

@dataclass
class ExecutorConfig:
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    timeout: int = 300
    max_steps: int = 50
    top_k_skills: int = 3

class SkillInjectingExecutor:

    def __init__(self, model_key: str, skill_bank: Optional[Dict[str, Skill]]=None, config: Optional[ExecutorConfig]=None):
        self.model_key = model_key
        self.skill_bank = skill_bank or {}
        self.config = config or ExecutorConfig(model=model_key)
        try:
            self.llm_client = RealLLMClient(model=self.config.model, api_key=self.config.api_key, base_url=self.config.base_url)
        except LLMConfigError as e:
            raise LLMConfigError(f'Failed to initialize executor for {model_key}: {e}. Set LLM_API_KEY and LLM_BASE_URL environment variables.') from e
        self.skill_tracker = SkillUsageTracker(self.skill_bank)
        self.step_tracker = StepSkillTracker()
        self.current_trajectory: Optional[Trajectory] = None
        self.step_count = 0

    def load_skill_bank(self, skill_bank: Dict[str, Skill]) -> None:
        self.skill_bank = skill_bank
        self.skill_tracker.load_skills(skill_bank)

    def execute_task(self, task_id: str, task_prompt: str) -> Trajectory:
        self.current_trajectory = Trajectory(task_id=task_id, task_description=task_prompt, steps=[], success=False)
        self.step_count = 0
        self.step_tracker.clear()
        enhanced_prompt = self._prepare_initial_prompt(task_prompt)
        try:
            trajectory = self._execute_with_openclaw(task_id=task_id, prompt=enhanced_prompt)
            return trajectory
        except Exception as e:
            raise RuntimeError(f'Task execution failed for {task_id}: {e}') from e

    def _prepare_initial_prompt(self, task_prompt: str) -> str:
        skills_section = self.skill_tracker.format_skills_for_prompt(query=task_prompt, top_k=self.config.top_k_skills, include_markers=True)
        if not skills_section:
            return task_prompt
        return f'{skills_section}\n\n--- ORIGINAL TASK ---\n\n{task_prompt}\n\nWhen completing this task, USE the skills provided above when appropriate.\nReference skills by their ID in your thinking process.'

    def _execute_with_openclaw(self, task_id: str, prompt: str) -> Trajectory:
        from adapters.pinchbench_adapter.executor import PinchBenchExecutor
        from core.openclaw_hygiene import cleanup_agent_sessions
        agent_id = f'skill-eval-{self.model_key}'
        cleanup_agent_sessions(agent_id)
        executor = PinchBenchExecutor(pinchbench_path=Path(os.environ.get('PINCHBENCH_PATH', '.')), api_key=self.config.api_key, base_url=self.config.base_url, model=self.config.model)
        trajectory = executor.execute_task(task_id, model=self.config.model)
        if trajectory is None:
            return Trajectory(task_id=task_id, task_description=task_prompt, steps=[], success=False)
        return trajectory

    def _parse_transcript_with_skill_tracking(self, transcript: List[Dict[str, Any]], original_prompt: str) -> List[Step]:
        steps = []
        step_index = 0
        last_observation = original_prompt[:2000]
        for entry in transcript:
            if entry.get('type') == 'message':
                msg = entry.get('message', {})
                role = msg.get('role', '')
                content = msg.get('content', '')
                if role == 'assistant':
                    skills_used = self._analyze_skill_usage(content)
                    step = Step(index=step_index, observation=last_observation, action=content[:2000], reward=0.0, skills_used=skills_used)
                    steps.append(step)
                    step_index += 1
                    last_observation = f'Previous: {content[:500]}...'
        return steps

    def _analyze_skill_usage(self, agent_response: str) -> List[str]:
        skills_used = self.skill_tracker.analyze_skill_usage(agent_response)
        for skill_id, skill in self.skill_bank.items():
            if skill_id in skills_used:
                continue
            checks = [skill.title.lower() in agent_response.lower(), any((kw.lower() in agent_response.lower() for kw in skill.description.split()[:5]))]
            if any(checks):
                skills_used.append(skill_id)
        return skills_used

    def execute_with_skill_injection(self, tasks: List[str], task_prompts: Dict[str, str]) -> Dict[str, Trajectory]:
        results = {}
        for task_id in tasks:
            prompt = task_prompts.get(task_id, '')
            print(f'Executing {task_id} with skills...')
            try:
                trajectory = self.execute_task(task_id, prompt)
                results[task_id] = trajectory
                for step in trajectory.steps:
                    if step.skills_used:
                        print(f'  Step {step.index}: used skills {step.skills_used}')
            except Exception as e:
                print(f'  ERROR: {e}')
                raise
        return results

def create_skill_injecting_executor(model_key: str, skill_bank_path: Optional[str]=None) -> SkillInjectingExecutor:
    skill_bank = {}
    if skill_bank_path and Path(skill_bank_path).exists():
        with open(skill_bank_path) as f:
            data = json.load(f)
            for skill_id, skill_data in data.get('skills', {}).items():
                skill_bank[skill_id] = Skill.from_dict(skill_data)
    return SkillInjectingExecutor(model_key=model_key, skill_bank=skill_bank)
