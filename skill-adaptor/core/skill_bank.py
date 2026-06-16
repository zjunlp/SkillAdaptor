"""Skill Bank Management Module"""

from __future__ import annotations
import json
import re
from typing import Any, Dict, List, Optional, Set
from pathlib import Path
from .types import Skill, SkillBank

def skill_to_text(skill: Skill) -> str:
    return f'- [{skill.title}] {skill.description} (when: {skill.when_to_apply})'

def retrieve_skills(skills: List[Skill], query: str, k: int=3) -> List[Skill]:
    if len(skills) <= k:
        return skills
    query_lower = query.lower()
    query_words = set(query_lower.split())
    scored = []
    for skill in skills:
        skill_text = f'{skill.title} {skill.description} {skill.when_to_apply} {skill.body}'.lower()
        matches = sum((1 for word in query_words if word in skill_text))
        if any((word in skill.title.lower() for word in query_words)):
            matches += 3
        scored.append((matches, skill))
    scored.sort(key=lambda x: -x[0])
    return [skill for _, skill in scored[:k]]

class SkillBankManager:

    def __init__(self, skill_bank: Optional[SkillBank]=None):
        self.bank = skill_bank or SkillBank()

    def add_skill(self, skill: Skill) -> None:
        self.bank.add(skill)

    def get_skill(self, skill_id: str) -> Optional[Skill]:
        return self.bank.get(skill_id)

    def update_skill(self, skill: Skill) -> None:
        self.bank.update(skill)

    def remove_skill(self, skill_id: str) -> bool:
        return self.bank.remove(skill_id)

    def list_skills(self) -> List[Skill]:
        return self.bank.list_all()

    def retrieve_relevant(self, query: str, k: int=3) -> List[Skill]:
        return retrieve_skills(self.list_skills(), query, k)

    def to_dict(self) -> Dict[str, Any]:
        return self.bank.to_dict()

    def save(self, path: str | Path) -> None:
        self.bank.to_json(str(path))

    def load(self, path: str | Path) -> None:
        self.bank = SkillBank.from_json(str(path))

    def deduplicate(self, new_skills: List[Skill], similarity_threshold: float=0.8) -> List[Skill]:
        existing = self.list_skills()
        unique = []
        for new_skill in new_skills:
            is_duplicate = False
            for existing_skill in existing:
                if self._similarity(new_skill, existing_skill) >= similarity_threshold:
                    is_duplicate = True
                    break
            if not is_duplicate:
                for existing_unique in unique:
                    if self._similarity(new_skill, existing_unique) >= similarity_threshold:
                        is_duplicate = True
                        break
            if not is_duplicate:
                unique.append(new_skill)
        return unique

    def _similarity(self, skill1: Skill, skill2: Skill) -> float:
        text1 = f'{skill1.title} {skill1.description} {skill1.body}'.lower()
        text2 = f'{skill2.title} {skill2.description} {skill2.body}'.lower()
        words1 = set(re.findall('\\b[a-z]{3,}\\b', text1))
        words2 = set(re.findall('\\b[a-z]{3,}\\b', text2))
        if not words1 or not words2:
            return 0.0
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        return intersection / union if union > 0 else 0.0

    def bootstrap_from_trajectories(self, trajectories: List[Any], min_success_rate: float=0.8) -> List[Skill]:
        from .types import Trajectory
        skills = []
        success_trajs = [t for t in trajectories if t.success]
        failed_trajs = [t for t in trajectories if not t.success]
        for traj in success_trajs:
            extracted = self._extract_from_success(traj)
            skills.extend(extracted)
        if len(skills) < 3 and failed_trajs:
            for traj in failed_trajs:
                extracted = self._extract_from_failure(traj)
                skills.extend(extracted)
        return skills

    def _extract_from_success(self, trajectory) -> List[Skill]:
        skills = []
        if not trajectory.steps:
            return skills
        skill_id = f'success_{trajectory.task_id}'
        skill = Skill(id=skill_id, title=f'Strategy for {trajectory.task_id}', description='Successful approach extracted from trajectory', body=self._format_success_body(trajectory), created_from=trajectory.task_id)
        skills.append(skill)
        return skills

    def _extract_from_failure(self, trajectory) -> List[Skill]:
        skills = []
        fault_step = trajectory.get_fault_step()
        if not fault_step:
            return skills
        skill_id = f'avoid_{trajectory.task_id}'
        skill = Skill(id=skill_id, title=f'Avoid error in {trajectory.task_id}', description=f'Learned from failure at step {fault_step.index + 1}', body=self._format_failure_body(trajectory, fault_step), created_from=trajectory.task_id)
        skills.append(skill)
        return skills

    def _format_success_body(self, trajectory) -> str:
        steps_str = '\n'.join([f'{i + 1}. {step.action}' for i, step in enumerate(trajectory.steps)])
        return f'# Successful Strategy\n\n## Task\n{trajectory.task_description}\n\n## Approach\n{steps_str}\n\n## Key Points\n- Follow this sequence for similar tasks\n- Adapt based on observation feedback\n'

    def _format_failure_body(self, trajectory, fault_step) -> str:
        return f'# Error Prevention\n\n## Context\nTask: {trajectory.task_description}\n\n## Mistake to Avoid\nAt step {fault_step.index + 1}:\n- Action: {fault_step.action}\n- Observation: {fault_step.observation[:150]}...\n\n## Lesson\nThis action led to failure. Consider alternatives.\n'

    def __len__(self) -> int:
        return len(self.bank.skills)

    def __contains__(self, skill_id: str) -> bool:
        return skill_id in self.bank.skills
