"""Semantic Skill Matcher"""

from __future__ import annotations
import json
import os
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from .types import Skill
from .llm_retry import call_with_retries
from .embedding_config import PRIMARY_EMBEDDING_MODEL, format_embedding_error, resolve_embedding_model

class SemanticSkillMatcher:
    DEFAULT_API_MODEL = PRIMARY_EMBEDDING_MODEL
    DEFAULT_THRESHOLD = 0.6

    def __init__(self, model_name: str=DEFAULT_API_MODEL, similarity_threshold: float=DEFAULT_THRESHOLD, embedding_client: Optional[Any]=None, api_key: Optional[str]=None, base_url: Optional[str]=None):
        self.similarity_threshold = similarity_threshold
        self.model_name = resolve_embedding_model(model_name)
        self.embedding_client = embedding_client
        self.api_key = api_key or os.environ.get('SkillEvolve_EMBEDDING_API_KEY', '')
        self.base_url = base_url or os.environ.get('SkillEvolve_EMBEDDING_BASE_URL', '')

    def _embed_via_api(self, texts: List[str]):
        import numpy as np
        if self.embedding_client is not None:
            response = self.embedding_client.embeddings.create(model=self.model_name, input=texts)
            embeddings = [item.embedding for item in response.data]
            return np.array(embeddings)
        api_key = self.api_key
        base_url = self.base_url
        headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
        payload = json.dumps({'model': self.model_name, 'input': texts}).encode('utf-8')
        req = urllib.request.Request(f'{base_url}/embeddings', data=payload, headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode('utf-8'))
            embeddings = [item['embedding'] for item in data['data']]
            return np.array(embeddings)

    def encode(self, texts: List[str]):
        import numpy as np
        if not texts:
            return np.array([])
        if self.embedding_client is None and (not (self.api_key and self.base_url)):
            raise RuntimeError('Embedding API not configured. Set SkillEvolve_EMBEDDING_API_KEY and SkillEvolve_EMBEDDING_BASE_URL, or pass embedding_client.')
        max_retries = int(os.environ.get('SkillEvolve_MAX_RETRIES', os.environ.get('MAX_RETRIES', '5')))
        try:
            return call_with_retries(lambda: self._embed_via_api(texts), max_retries=max_retries, context=f'Embedding API (model={self.model_name!r})')
        except Exception as exc:
            raise RuntimeError(format_embedding_error(self.model_name, exc)) from exc

    def compute_similarity(self, skill_texts: List[str], task_texts: List[str]):
        import numpy as np
        skill_embeddings = self.encode(skill_texts)
        task_embeddings = self.encode(task_texts)
        skill_norms = np.linalg.norm(skill_embeddings, axis=1, keepdims=True)
        task_norms = np.linalg.norm(task_embeddings, axis=1, keepdims=True)
        skill_norms[skill_norms == 0] = 1
        task_norms[task_norms == 0] = 1
        skill_embeddings = skill_embeddings / skill_norms
        task_embeddings = task_embeddings / task_norms
        similarity = skill_embeddings @ task_embeddings.T
        return similarity

    def match_skills_to_task(self, skills: Dict[str, Skill], task_description: str, top_k: int=5) -> List[Tuple[Skill, float]]:
        if not skills:
            return []
        skill_texts = []
        skill_list = []
        for skill in skills.values():
            text = self._build_enhanced_skill_text(skill)
            skill_texts.append(text)
            skill_list.append(skill)
        similarities = self.compute_similarity(skill_texts, [task_description]).flatten()
        matches = []
        for skill, sim in zip(skill_list, similarities):
            if sim >= self.similarity_threshold:
                matches.append((skill, float(sim)))
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[:top_k]

    def rank_skills_for_task(self, skills: Dict[str, Skill], task_description: str, top_k: int=10) -> List[Tuple[Skill, float]]:
        if not skills:
            return []
        skill_texts = [self._build_enhanced_skill_text(s) for s in skills.values()]
        skill_list = list(skills.values())
        similarities = self.compute_similarity(skill_texts, [task_description]).flatten()
        ranked = sorted(((skill, float(sim)) for skill, sim in zip(skill_list, similarities)), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]

    def build_task_description(self, task_id: str, tasks_dir: Optional[Path]=None, goal_text: Optional[str]=None) -> str:
        description_parts = []
        if goal_text:
            description_parts.append(f'Task Goal: {goal_text}')
            description_parts.append('Task Type: WebShop product search and purchase')
            return ' '.join(description_parts)
        if tasks_dir is not None:
            task_file = tasks_dir / f'{task_id}.md'
            if task_file.exists():
                content = task_file.read_text(encoding='utf-8')
                lines = content.split('\n')
                task_type = self._infer_task_type(task_id)
                description_parts.append(f'Task Type: {task_type}')
                desc_lines = []
                for line in lines[:30]:
                    if line.strip() and (not line.startswith('#')):
                        desc_lines.append(line)
                if desc_lines:
                    description_parts.append(f"Task Goal: {' '.join(desc_lines[:3])}")
                domain = self._infer_domain(task_id, ' '.join(desc_lines[:5]) if desc_lines else '')
                if domain:
                    description_parts.append(f'Domain: {domain}')
                return ' '.join(description_parts)
        parts = task_id.replace('task_', '').split('_')[1:]
        task_type = self._infer_task_type(task_id)
        return f"Task Type: {task_type}. Task Goal: {' '.join(parts)}"

    def _infer_task_type(self, task_id: str) -> str:
        task_id_lower = task_id.lower()
        type_hints = {'spreadsheet': 'spreadsheet data processing', 'csv': 'CSV data processing', 'file': 'file system operations', 'api': 'API integration', 'web': 'web scraping or interaction', 'data': 'data analysis', 'test': 'testing and validation', 'script': 'script execution', 'config': 'configuration management', 'docker': 'container operations', 'git': 'version control operations', 'sql': 'database operations', 'doc': 'document processing', 'pdf': 'PDF processing', 'image': 'image processing', 'math': 'mathematical computation', 'chart': 'chart and visualization', 'email': 'email operations', 'search': 'search and retrieval'}
        for hint, task_type in type_hints.items():
            if hint in task_id_lower:
                return task_type
        return 'general task execution'

    def _infer_domain(self, task_id: str, content: str) -> str:
        content_lower = content.lower()
        task_lower = task_id.lower()
        domains = {'data processing': ['csv', 'excel', 'data', 'spreadsheet', 'table', 'row', 'column'], 'web automation': ['browser', 'web', 'html', 'url', 'click', 'page'], 'file operations': ['file', 'directory', 'folder', 'path', 'read', 'write'], 'api integration': ['api', 'endpoint', 'request', 'response', 'json'], 'code execution': ['python', 'script', 'execute', 'run', 'function'], 'text processing': ['text', 'string', 'parse', 'extract', 'regex']}
        for domain, keywords in domains.items():
            if any((kw in content_lower or kw in task_lower for kw in keywords)):
                return domain
        return ''

    def create_skill_bank_for_task(self, skills: Dict[str, Skill], task_id: str, tasks_dir: Optional[Path]=None, min_score: Optional[float]=None) -> Dict[str, Skill]:
        threshold = min_score if min_score is not None else self.similarity_threshold
        task_desc = self.build_task_description(task_id, tasks_dir)
        matches = self.match_skills_to_task(skills, task_desc, top_k=10)
        relevant = {}
        for skill, score in matches:
            if score >= threshold:
                relevant[skill.id] = skill
        return relevant

    def _build_enhanced_skill_text(self, skill: Skill) -> str:
        parts = []
        parts.append(f'Skill: {skill.title}')
        parts.append(f'Purpose: {skill.description}')
        if skill.when_to_apply:
            parts.append(f'When to use: {skill.when_to_apply}')
        body_summary = skill.body[:300] if skill.body else ''
        if body_summary:
            parts.append(f'How: {body_summary}')
        return ' | '.join(parts)

def create_matcher(similarity_threshold: float=0.5, embedding_client: Optional[Any]=None, api_key: Optional[str]=None, base_url: Optional[str]=None, model_name: Optional[str]=None) -> SemanticSkillMatcher:
    return SemanticSkillMatcher(similarity_threshold=similarity_threshold, embedding_client=embedding_client, api_key=api_key, base_url=base_url, model_name=model_name)
