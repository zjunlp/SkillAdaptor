"""Build retrieval index from manifest JSON + PinchBench task files."""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from core.skill_retrieval import RetrievalPolicy, SkillRetrievalGate
from adapters.pinchbench_adapter.task_category import get_task_category

@dataclass
class TaskRetrievalLabel:
    category: str = ''
    tags: List[str] = field(default_factory=list)

@dataclass
class RetrievalIndex:
    labels: Dict[str, TaskRetrievalLabel] = field(default_factory=dict)
    policy: RetrievalPolicy = field(default_factory=RetrievalPolicy)

    def category_of(self, task_id: str, tasks_dir: Optional[Path]=None) -> str:
        label = self.labels.get(task_id)
        if label and label.category:
            return label.category.lower()
        if tasks_dir is not None:
            return get_task_category(task_id, tasks_dir).lower()
        return get_task_category(task_id, Path('.')).lower()

    def tags_of(self, task_id: str) -> List[str]:
        label = self.labels.get(task_id)
        return list(label.tags) if label else []

    def gate(self, tasks_dir: Optional[Path]=None) -> SkillRetrievalGate:
        td = tasks_dir

        def _cat(tid: str) -> str:
            return self.category_of(tid, td)

        def _tags(tid: str) -> List[str]:
            return self.tags_of(tid)
        return SkillRetrievalGate(task_category_fn=_cat, policy=self.policy, task_tags_fn=_tags)

def _parse_policy(raw: Dict[str, Any]) -> RetrievalPolicy:
    return RetrievalPolicy(same_category_embed_min=float(raw.get('same_category_embed_min', 0.5)), cross_task_embed_min=float(raw.get('cross_task_embed_min', 0.55)), cross_category_embed_min=float(raw.get('cross_category_embed_min', 0.72)), allow_cross_category=bool(raw.get('allow_cross_category', False)), require_category_match=bool(raw.get('require_category_match', True)))

def build_retrieval_index(manifest_data: Optional[Dict[str, Any]], *, tasks_dir: Optional[Path]=None, config=None) -> RetrievalIndex:
    raw = (manifest_data or {}).get('retrieval') or {}
    policy = _parse_policy(raw.get('policy') or {})
    if config is not None:
        policy = RetrievalPolicy(same_category_embed_min=float(getattr(config, 'skill_match_threshold', policy.same_category_embed_min)), cross_task_embed_min=float(getattr(config, 'cross_task_match_threshold', policy.cross_task_embed_min)), cross_category_embed_min=policy.cross_category_embed_min, allow_cross_category=policy.allow_cross_category, require_category_match=policy.require_category_match)
    labels: Dict[str, TaskRetrievalLabel] = {}
    task_labels = raw.get('task_labels') or {}
    for tid, meta in task_labels.items():
        if isinstance(meta, dict):
            labels[tid] = TaskRetrievalLabel(category=str(meta.get('category', '')).lower(), tags=[str(t) for t in meta.get('tags') or []])
        elif isinstance(meta, str):
            labels[tid] = TaskRetrievalLabel(category=meta.lower())
    if tasks_dir and tasks_dir.exists():
        all_ids = set(labels.keys())
        if manifest_data:
            for key in ('input_tasks', 'validation_tasks', 'test_tasks'):
                all_ids.update(manifest_data.get(key) or [])
        for tid in all_ids:
            if tid not in labels or not labels[tid].category:
                cat = get_task_category(tid, tasks_dir)
                prev = labels.get(tid, TaskRetrievalLabel())
                labels[tid] = TaskRetrievalLabel(category=cat or prev.category, tags=prev.tags)
    return RetrievalIndex(labels=labels, policy=policy)
