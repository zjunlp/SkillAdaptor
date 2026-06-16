"""Unified skill–task retrieval gate (manifest labels + category + embedding)."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Optional
from core.types import Skill

@dataclass(frozen=True)
class RetrievalPolicy:
    same_category_embed_min: float = 0.5
    cross_task_embed_min: float = 0.55
    cross_category_embed_min: float = 0.72
    allow_cross_category: bool = False
    require_category_match: bool = True

@dataclass(frozen=True)
class InjectionDecision:
    inject: bool
    score: float
    reason: str

class SkillRetrievalGate:

    def __init__(self, *, task_category_fn: Callable[[str], str], policy: Optional[RetrievalPolicy]=None, task_tags_fn: Optional[Callable[[str], list[str]]]=None):
        self.task_category_fn = task_category_fn
        self.task_tags_fn = task_tags_fn or (lambda _tid: [])
        self.policy = policy or RetrievalPolicy()

    def skill_category(self, skill: Skill) -> str:
        cat = (getattr(skill, 'domain_category', None) or '').strip().lower()
        if cat:
            return cat
        origin = getattr(skill, 'created_from', None)
        if origin:
            return self.task_category_fn(origin).lower()
        return ''

    def evaluate(self, task_id: str, skill: Skill, embed_score: float) -> InjectionDecision:
        origin = getattr(skill, 'created_from', None)
        if origin and origin == task_id:
            return InjectionDecision(True, 1.0, 'provenance')
        task_cat = self.task_category_fn(task_id).lower()
        skill_cat = self.skill_category(skill)
        if self.policy.require_category_match and skill_cat and task_cat and (skill_cat != task_cat):
            if self.policy.allow_cross_category and embed_score >= self.policy.cross_category_embed_min:
                return InjectionDecision(True, embed_score, f'cross_category_embed>={self.policy.cross_category_embed_min:.2f}')
            return InjectionDecision(False, embed_score, f'skip:category {skill_cat}!={task_cat}')
        threshold = self.policy.same_category_embed_min
        if origin and origin != task_id:
            threshold = max(threshold, self.policy.cross_task_embed_min)
        if embed_score >= threshold:
            return InjectionDecision(True, embed_score, f'embed>={threshold:.2f}')
        return InjectionDecision(False, embed_score, f'skip:embed<{threshold:.2f}')
