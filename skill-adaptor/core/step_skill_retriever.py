"""Per-step Top-k skill retrieval (TGWS S_t)."""

from __future__ import annotations
from typing import Dict, List, Optional, Tuple
from .types import Skill
from .skill_matcher import SemanticSkillMatcher

class StepSkillRetriever:

    def __init__(self, matcher: SemanticSkillMatcher, top_k: int=3, min_score: float=0.0):
        self.matcher = matcher
        self.top_k = top_k
        self.min_score = min_score

    def retrieve_for_step(self, task_description: str, observation: str, action: str, skill_bank: Dict[str, Skill]) -> List[str]:
        if not skill_bank:
            return []
        query = ' '.join([task_description[:300], observation[:400], action[:200]]).strip()
        matches: List[Tuple[Skill, float]] = self.matcher.match_skills_to_task(skill_bank, query, top_k=self.top_k)
        ids: List[str] = []
        for skill, score in matches:
            if score >= self.min_score:
                ids.append(skill.id)
        return ids

    def annotate_trajectory_steps(self, task_description: str, steps: List[dict], skill_bank: Dict[str, Skill]) -> List[dict]:
        annotated: List[dict] = []
        for step in steps:
            copy = dict(step)
            if copy.get('type') in (None, 'action', 'observation'):
                copy['skills_used'] = self.retrieve_for_step(task_description, copy.get('observation', ''), copy.get('action', ''), skill_bank)
            else:
                copy['skills_used'] = copy.get('skills_used', [])
            annotated.append(copy)
        return annotated
