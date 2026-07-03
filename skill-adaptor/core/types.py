"""Core type definitions for the SkillEvolve framework."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set
import hashlib
import json

class FaultType(Enum):
    SKILL_WRONG = 'skill_wrong'
    SKILL_MISSING = 'skill_missing'
    REASONING_WRONG = 'reasoning_wrong'
    UNKNOWN = 'unknown'

@dataclass
class Skill:
    id: str
    title: str
    description: str
    body: str
    body_sha256: Optional[str] = None
    when_to_apply: str = ''
    created_from: Optional[str] = None
    domain_category: str = ''
    tags: List[str] = field(default_factory=list)
    version: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def __post_init__(self):
        if self.body_sha256 is None and self.body:
            self.body_sha256 = self._compute_hash(self.body)
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
        if self.updated_at is None:
            self.updated_at = self.created_at

    @staticmethod
    def _compute_hash(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {'id': self.id, 'title': self.title, 'description': self.description, 'body': self.body, 'body_sha256': self.body_sha256, 'when_to_apply': self.when_to_apply, 'created_from': self.created_from, 'domain_category': self.domain_category, 'tags': list(self.tags), 'version': self.version, 'created_at': self.created_at, 'updated_at': self.updated_at}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Skill:
        return cls(id=data['id'], title=data['title'], description=data['description'], body=data['body'], body_sha256=data.get('body_sha256'), when_to_apply=data.get('when_to_apply', ''), created_from=data.get('created_from'), domain_category=data.get('domain_category', ''), tags=list(data.get('tags') or []), version=data.get('version', 1), created_at=data.get('created_at'), updated_at=data.get('updated_at'))

    def copy_with_revision(self) -> Skill:
        return Skill(id=self.id, title=self.title, description=self.description, body=self.body, body_sha256=self.body_sha256, when_to_apply=self.when_to_apply, created_from=self.created_from, domain_category=self.domain_category, tags=list(self.tags), version=self.version + 1, created_at=self.created_at)

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Skill):
            return False
        return self.id == other.id

@dataclass
class Step:
    index: int
    observation: str
    action: str
    reward: float = 0.0
    done: bool = False
    skills_used: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {'index': self.index, 'observation': self.observation, 'action': self.action, 'reward': self.reward, 'done': self.done, 'skills_used': self.skills_used, 'metadata': self.metadata}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Step:
        return cls(index=data['index'], observation=data['observation'], action=data['action'], reward=data.get('reward', 0.0), done=data.get('done', False), skills_used=data.get('skills_used', []), metadata=data.get('metadata', {}))

@dataclass
class Trajectory:
    task_id: str
    task_description: str
    steps: List[Step]
    success: bool = False
    total_reward: float = 0.0
    error_step: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_fault_step(self) -> Optional[Step]:
        if self.success:
            return None
        if self.error_step is not None and 0 <= self.error_step < len(self.steps):
            return self.steps[self.error_step]
        if self.steps:
            return self.steps[-1]
        return None

    def get_step_context(self, step_index: int, window: int=3) -> List[Step]:
        start = max(0, step_index - window)
        end = min(len(self.steps), step_index + window + 1)
        return self.steps[start:end]

    def to_dict(self) -> Dict[str, Any]:
        return {'task_id': self.task_id, 'task_description': self.task_description, 'steps': [s.to_dict() for s in self.steps], 'success': self.success, 'total_reward': self.total_reward, 'error_step': self.error_step, 'metadata': self.metadata}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Trajectory:
        return cls(task_id=data['task_id'], task_description=data['task_description'], steps=[Step.from_dict(s) for s in data.get('steps', [])], success=data.get('success', False), total_reward=data.get('total_reward', 0.0), error_step=data.get('error_step'), metadata=data.get('metadata', {}))

@dataclass
class LocalizedFault:
    task_id: str
    step_index: int
    fault_type: FaultType
    observation: str
    wrong_action: str
    skills_at_fault: List[str] = field(default_factory=list)
    improvement_principle: str = ''
    fault_chain: List[int] = field(default_factory=list)
    deliverable_targets: List[str] = field(default_factory=list)
    wrong_artifact_note: str = ''
    rubric_gap: str = ''

    def to_dict(self) -> Dict[str, Any]:
        return {'task_id': self.task_id, 'step_index': self.step_index, 'fault_type': self.fault_type.value, 'observation': self.observation, 'wrong_action': self.wrong_action, 'skills_at_fault': self.skills_at_fault, 'improvement_principle': self.improvement_principle, 'fault_chain': self.fault_chain, 'deliverable_targets': list(self.deliverable_targets), 'wrong_artifact_note': self.wrong_artifact_note, 'rubric_gap': self.rubric_gap}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LocalizedFault:
        return cls(task_id=data['task_id'], step_index=data['step_index'], fault_type=FaultType(data.get('fault_type', 'unknown')), observation=data['observation'], wrong_action=data['wrong_action'], skills_at_fault=data.get('skills_at_fault', []), improvement_principle=data.get('improvement_principle', ''), fault_chain=data.get('fault_chain', []), deliverable_targets=list(data.get('deliverable_targets') or []), wrong_artifact_note=str(data.get('wrong_artifact_note') or ''), rubric_gap=str(data.get('rubric_gap') or ''))

@dataclass
class SkillAttribution:
    skill_id: str
    weight: float
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {'skill_id': self.skill_id, 'weight': self.weight, 'reason': self.reason}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SkillAttribution:
        return cls(skill_id=data['skill_id'], weight=data['weight'], reason=data['reason'])

@dataclass
class ValidationResult:
    skill_id: str
    delta_success: float
    delta_avg_score: float
    regression_detected: bool
    sample_size: int
    baseline_metrics: Dict[str, float] = field(default_factory=dict)
    revised_metrics: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {'skill_id': self.skill_id, 'delta_success': self.delta_success, 'delta_avg_score': self.delta_avg_score, 'regression_detected': self.regression_detected, 'sample_size': self.sample_size, 'baseline_metrics': self.baseline_metrics, 'revised_metrics': self.revised_metrics}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ValidationResult:
        return cls(skill_id=data['skill_id'], delta_success=data['delta_success'], delta_avg_score=data['delta_avg_score'], regression_detected=data['regression_detected'], sample_size=data['sample_size'], baseline_metrics=data.get('baseline_metrics', {}), revised_metrics=data.get('revised_metrics', {}))

@dataclass
class SkillInjection:
    transcript_event_index: int
    step_index: int
    skills: List[Dict[str, Any]]
    source: str = 'SkillEvolve'
    ts_ms: Optional[int] = None

    def __post_init__(self):
        if self.ts_ms is None:
            self.ts_ms = int(datetime.now().timestamp() * 1000)

    def to_dict(self) -> Dict[str, Any]:
        return {'transcript_event_index': self.transcript_event_index, 'step_index': self.step_index, 'skills': self.skills, 'source': self.source, 'ts_ms': self.ts_ms}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SkillInjection:
        return cls(transcript_event_index=data['transcript_event_index'], step_index=data['step_index'], skills=data['skills'], source=data.get('source', 'SkillEvolve'), ts_ms=data.get('ts_ms'))

@dataclass
class SkillBank:
    skills: Dict[str, Skill] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)

    def add(self, skill: Skill) -> None:
        self.skills[skill.id] = skill
        self._record('add', skill)

    def get(self, skill_id: str) -> Optional[Skill]:
        return self.skills.get(skill_id)

    def update(self, skill: Skill) -> None:
        skill.version = self.skills.get(skill.id, skill).version + 1
        skill.updated_at = datetime.now().isoformat()
        self.skills[skill.id] = skill
        self._record('update', skill)

    def remove(self, skill_id: str) -> bool:
        if skill_id in self.skills:
            del self.skills[skill_id]
            self.history.append({'action': 'remove', 'skill_id': skill_id, 'timestamp': datetime.now().isoformat()})
            return True
        return False

    def list_all(self) -> List[Skill]:
        return list(self.skills.values())

    def _record(self, action: str, skill: Skill) -> None:
        self.history.append({'action': action, 'skill_id': skill.id, 'version': skill.version, 'timestamp': datetime.now().isoformat()})

    def to_dict(self) -> Dict[str, Any]:
        return {'skills': {k: v.to_dict() for k, v in self.skills.items()}, 'history': self.history}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SkillBank:
        bank = cls()
        for skill_id, skill_data in data.get('skills', {}).items():
            bank.skills[skill_id] = Skill.from_dict(skill_data)
        bank.history = data.get('history', [])
        return bank

    def to_json(self, path: str) -> None:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, path: str) -> SkillBank:
        with open(path, 'r', encoding='utf-8') as f:
            return cls.from_dict(json.load(f))
