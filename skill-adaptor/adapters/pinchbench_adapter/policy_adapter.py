"""PinchBench policy adapter."""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, TYPE_CHECKING
import re 
from core.types import Skill
from core.skill_matcher import create_matcher
from core.skill_retrieval import SkillRetrievalGate
from core.skill_body_utils import pinchbench_deliverable_banner, resolve_immediate_shell_action, task_mentions_command_deliverable
from .constraint_provider import PinchBenchConstraintProvider
if TYPE_CHECKING:
    from runtime.retrieval_index import RetrievalIndex

@dataclass
class BenchmarkArgs:
    suite: str
    artifact_dir: str
    timeout_multiplier: float = 2.0
    no_upload: bool = True

class PinchBenchPolicyAdapter:

    def __init__(self, artifact_dir: Path | str, embedding_client=None, api_key: str='', base_url: str='', embedding_model: str='', similarity_threshold: float=0.5, cross_task_threshold: float=0.55, retrieval_index: Optional['RetrievalIndex']=None):
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.similarity_threshold = similarity_threshold
        self.cross_task_threshold = cross_task_threshold
        self.retrieval_index = retrieval_index
        self.matcher = create_matcher(similarity_threshold=similarity_threshold, embedding_client=embedding_client, api_key=api_key, base_url=base_url, model_name=embedding_model or None)

    def _retrieval_gate(self, tasks_dir: Optional[Path]) -> SkillRetrievalGate:
        if self.retrieval_index is not None:
            return self.retrieval_index.gate(tasks_dir)
        if tasks_dir is None:
            raise RuntimeError('Skill retrieval requires tasks_dir or manifest retrieval_index; refusing unscoped (global) skill injection.')
        from core.skill_retrieval import RetrievalPolicy
        from adapters.pinchbench_adapter.task_category import get_task_category

        def _cat(tid: str) -> str:
            return get_task_category(tid, tasks_dir)
        return SkillRetrievalGate(task_category_fn=_cat, policy=RetrievalPolicy(same_category_embed_min=self.similarity_threshold, cross_task_embed_min=self.cross_task_threshold, require_category_match=True))

    def _select_skills_for_task(self, task_id: str, skill_bank: Dict[str, Skill], tasks_dir: Optional[Path], top_k: int) -> List[tuple[Skill, float, str]]:
        gate = self._retrieval_gate(tasks_dir)
        task_desc = self.matcher.build_task_description(task_id, tasks_dir=tasks_dir)
        ranked = self.matcher.rank_skills_for_task(skill_bank, task_desc, top_k=10)
        selected: List[tuple[Skill, float, str]] = []
        seen: set[str] = set()
        for skill, score in ranked:
            if skill.id in seen:
                continue
            decision = gate.evaluate(task_id, skill, score)
            if not decision.inject:
                continue
            selected.append((skill, decision.score, decision.reason))
            seen.add(skill.id)
            if len(selected) >= top_k:
                break
        return selected[:top_k]

    def _normalize_text(self, text: str) -> str:
        text = text.lower()
        text = re.sub('task[_\\-\\s]*\\d+[a-z0-9_\\-]*', ' ', text)
        text = re.sub('[^a-z0-9\\s]', ' ', text)
        text = re.sub('\\s+', ' ', text).strip()
        return text

    def _task_content(self, task_id: str, tasks_dir: Optional[Path]) -> str:
        if tasks_dir is not None:
            task_file = tasks_dir / f'{task_id}.md'
            if task_file.exists():
                raw = task_file.read_text(encoding='utf-8')
                lines = [ln.strip() for ln in raw.splitlines() if ln.strip() and (not ln.strip().startswith('#'))]
                return self._normalize_text(' '.join(lines[:40]))
        return self._normalize_text(task_id.replace('_', ' '))

    def build_skill_text(self, skill: Skill, template: str='enhanced', model: Optional[str]=None) -> str:
        template = template.lower()
        model_lower = (model or '').lower()
        model_rules = ''
        if 'kimi' in model_lower:
            model_rules = '## MODEL-SPECIFIC RULES (Kimi)\n- Follow strict step ordering; avoid open-ended retries\n- Max exec calls: 5 unless task explicitly requires more\n\n'
        elif 'glm' in model_lower:
            model_rules = (
                '## MODEL-SPECIFIC RULES (GLM)\n'
                '- PinchBench runs on **bash/sh** (Linux). **Never** use PowerShell (`Get-ChildItem`, `Select-String`, `pwsh`).\n'
                '- When a canonical command is given below, copy it **verbatim** into the deliverable file.\n'
                '- Keep actions concise; first tool call must implement the deliverable.\n\n'
            )
        elif 'gpt' in model_lower or 'openai' in model_lower:
            model_rules = '## MODEL-SPECIFIC RULES (GPT)\n- Use structured reasoning with clear step-by-step approach\n- Prefer explicit over implicit; document assumptions\n- Validate intermediate results before proceeding\n\n'
        if template == 'standard':
            return f'# {skill.title}\n\n## Objective\n{skill.description}\n\n{model_rules}## Steps\n{skill.body}\n'
        if template == 'concise':
            return f'# {skill.title}\n\n## CRITICAL CONSTRAINTS\n- DO NOT install new packages\n\n{model_rules}## Strategy\n{skill.body}\n'
        return f'# {skill.title}\n\n## CRITICAL CONSTRAINTS\n- DO NOT create virtual environments\n- DO NOT install packages in runtime\n\n{model_rules}## When to Use\n{skill.when_to_apply or skill.description}\n\n## Strategy\n{skill.body}\n'

    def map_tasks_to_skills(self, task_ids: Iterable[str], skill_bank: Dict[str, Skill], tasks_dir: Optional[Path]=None, top_k: int=3) -> Dict[str, List[Skill]]:
        mapped: Dict[str, List[Skill]] = {}
        for task_id in task_ids:
            mapped[task_id] = [s for s, _score, _reason in self._select_skills_for_task(task_id, skill_bank, tasks_dir, top_k)]
        return mapped

    def map_tasks_to_skills_with_scores(self, task_ids: Iterable[str], skill_bank: Dict[str, Skill], tasks_dir: Optional[Path]=None, top_k: int=3) -> Dict[str, List[tuple[Skill, float, str]]]:
        mapped: Dict[str, List[tuple[Skill, float, str]]] = {}
        for task_id in task_ids:
            mapped[task_id] = self._select_skills_for_task(task_id, skill_bank, tasks_dir, top_k)
        return mapped

    def tasks_receiving_skill(self, task_ids: Iterable[str], skill_bank: Dict[str, Skill], skill_id: str, tasks_dir: Optional[Path]=None) -> set[str]:
        audit = self.map_tasks_to_skills_with_scores(task_ids, skill_bank, tasks_dir=tasks_dir, top_k=3)
        hit: set[str] = set()
        for tid, entries in audit.items():
            if any((s.id == skill_id for s, _score, _reason in entries)):
                hit.add(tid)
        return hit

    def build_benchmark_args(self, tasks: Iterable[str], timeout_multiplier: float=2.0) -> BenchmarkArgs:
        return BenchmarkArgs(suite=','.join(tasks), artifact_dir=str(self.artifact_dir), timeout_multiplier=timeout_multiplier, no_upload=True)

    def _read_task_md(self, task_id: str, tasks_dir: Optional[Path]) -> str:
        if tasks_dir is not None:
            task_file = tasks_dir / f'{task_id}.md'
            if task_file.exists():
                return task_file.read_text(encoding='utf-8')
        return ''

    def build_combined_skill_text(self, skills: List[Skill], template: str='enhanced', model: Optional[str]=None, global_prior: str='', task_id: Optional[str]=None, tasks_dir: Optional[Path]=None) -> str:
        prior_block = ''
        if global_prior and global_prior.strip():
            prior_block = f'## Global Prior (π)\n\n{global_prior.strip()}\n\n---\n\n'
        banner = ''
        task_md = ''
        if task_id and tasks_dir is not None:
            task_md = self._read_task_md(task_id, tasks_dir)
            banner = pinchbench_deliverable_banner(task_id, task_md)
        immediate_block = ''
        resolved_action = ''
        if task_md and task_mentions_command_deliverable(task_md):
            for skill in skills:
                resolved_action = resolve_immediate_shell_action(skill.body, task_md)
                if resolved_action:
                    break
            if not resolved_action:
                resolved_action = resolve_immediate_shell_action('', task_md)
        if resolved_action:
            immediate_block = (
                '## STOP — WRITE THIS COMMAND FIRST\n'
                'Environment: **bash/sh only** (not PowerShell).\n'
                'Your **first** tool action must `write` path=`command.txt` (relative path in workspace root, '
                'never `C:\\\\...` absolute paths) with **only** this single line '
                '(plain text, one line, no markdown fence, no trailing newline):\n\n'
                f'```text\n{resolved_action}\n```\n\n'
                'Copy the line inside the fence **exactly**. Do not substitute `find`-only, PowerShell, or placeholders.\n\n'
                '## IMMEDIATE ACTION (execute first)\n'
                f'write path=command.txt content={resolved_action}\n\n---\n\n'
            )
        if not skills and (not prior_block) and (not banner):
            return ''
        skill_sections = []
        for i, skill in enumerate(skills, 1):
            skill_text = self.build_skill_text(skill, template=template, model=model)
            skill_sections.append(f'## Skill {i}: {skill.title}\n\n{skill_text}')
        combined = banner + immediate_block + prior_block + '# SKILLS\n\n'
        if skill_sections:
            combined += 'Use the following skills to complete the task:\n\n---\n\n'
            combined += '\n\n'.join(skill_sections[:3])
        elif prior_block:
            combined += 'Apply the global prior above when executing this task.\n'
        elif banner:
            combined += 'Follow the mandatory deliverable constraints above; do not invent alternate scenarios.\n'
        if combined and not combined.lstrip().startswith('---'):
            combined = (
                '---\n'
                'name: skill-adaptor-evolved\n'
                'description: PinchBench evolved skill — follow STOP / IMMEDIATE ACTION blocks first.\n'
                '---\n\n'
                + combined
            )
        max_chars = 5000
        if len(combined) > max_chars:
            combined = combined[:max_chars] + '\n\n<!-- truncated for agent context -->\n'
        return combined

    @staticmethod
    def get_revision_constraints() -> str:
        return PinchBenchConstraintProvider.get_constraints()

    @staticmethod
    def validate_skill(skill_text: str) -> tuple[bool, List[str]]:
        return PinchBenchConstraintProvider.validate_skill_text(skill_text)
