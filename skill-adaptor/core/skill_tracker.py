"""Skill Usage Tracker - Real-time skill usage tracking during agent execution."""

from __future__ import annotations
import re
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass
from .types import Skill

@dataclass
class TrackedSkill:
    skill: Skill
    injection_marker: str

class SkillUsageTracker:

    def __init__(self, skill_bank: Optional[Dict[str, Skill]]=None):
        self.skill_bank = skill_bank or {}
        self.tracked_skills: Dict[str, TrackedSkill] = {}
        self.current_markers: Dict[str, str] = {}

    def load_skills(self, skill_bank: Dict[str, Skill]) -> None:
        self.skill_bank = skill_bank
        self._prepare_markers()

    def _prepare_markers(self) -> None:
        self.current_markers = {}
        for skill_id, skill in self.skill_bank.items():
            marker = f'[SKILL:{skill_id}]'
            self.current_markers[skill_id] = marker

    def format_skills_for_prompt(self, query: str, top_k: int=3, include_markers: bool=True) -> str:
        if not self.skill_bank:
            return ''
        relevant = self._retrieve_relevant_skills(query, top_k)
        if not relevant:
            return ''
        parts = ['\n=== AVAILABLE SKILLS ===\n']
        parts.append('You have access to the following skills. Use them when appropriate:\n')
        for i, (skill_id, skill) in enumerate(relevant, 1):
            marker = self.current_markers.get(skill_id, '') if include_markers else ''
            skill_ref = f'[SKILL:{skill_id}]' if include_markers else f'[{skill_id}]'
            parts.append(f'\n{i}. {skill_ref} {skill.title}')
            if marker:
                parts.append(f'   Marker: {marker}')
            parts.append(f'   Description: {skill.description}')
            parts.append(f'   When to apply: {skill.when_to_apply}')
            if skill.body:
                body_preview = skill.body[:300].replace('\n', ' ')
                parts.append(f'   Guidance: {body_preview}...')
            parts.append('')
        parts.append('\n=== END SKILLS ===\n')
        parts.append('\nWhen you use a skill, reference it by its ID [skill_id] in your response.\n')
        return '\n'.join(parts)

    def _retrieve_relevant_skills(self, query: str, top_k: int=3) -> List[tuple[str, Skill]]:
        query_lower = query.lower()
        query_words = set(query_lower.split())
        scored = []
        for skill_id, skill in self.skill_bank.items():
            score = 0
            title_words = set(skill.title.lower().split())
            score += len(query_words & title_words) * 3
            desc_words = set(skill.description.lower().split())
            score += len(query_words & desc_words) * 2
            when_words = set(skill.when_to_apply.lower().split())
            score += len(query_words & when_words) * 2
            body_words = set(skill.body.lower().split())
            score += len(query_words & body_words)
            if skill.title.lower() in query_lower:
                score += 10
            if skill.when_to_apply.lower() in query_lower:
                score += 5
            if score > 0:
                scored.append((score, skill_id, skill))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [(sid, skill) for _, sid, skill in scored[:top_k]]

    def analyze_skill_usage(self, agent_response: str) -> List[str]:
        skills_used = []
        for skill_id in self.skill_bank.keys():
            patterns = [f'\\[{re.escape(skill_id)}\\]', f'\\b{re.escape(skill_id)}\\b', f'SKILL:{re.escape(skill_id)}']
            for pattern in patterns:
                if re.search(pattern, agent_response, re.IGNORECASE):
                    skills_used.append(skill_id)
                    break
        return skills_used

    def prepare_step_prompt(self, observation: str, query: str='', top_k: int=3) -> str:
        query = query or observation
        skills_section = self.format_skills_for_prompt(query, top_k)
        if not skills_section:
            return observation
        return f'{skills_section}\n\n--- CURRENT OBSERVATION ---\n\n{observation}'

class StepSkillTracker:

    def __init__(self):
        self.step_skills: Dict[int, List[str]] = {}
        self.current_injected: List[str] = []

    def record_injected_skills(self, skill_ids: List[str]) -> None:
        self.current_injected = skill_ids

    def record_step_usage(self, step_index: int, response: str, skill_bank: Dict[str, Skill]) -> List[str]:
        tracker = SkillUsageTracker(skill_bank)
        skills_used = tracker.analyze_skill_usage(response)
        self.step_skills[step_index] = skills_used
        return skills_used

    def get_step_skills(self, step_index: int) -> List[str]:
        return self.step_skills.get(step_index, [])

    def get_all_tracked_skills(self) -> Dict[int, List[str]]:
        return self.step_skills.copy()

    def clear(self) -> None:
        self.step_skills.clear()
        self.current_injected = []
