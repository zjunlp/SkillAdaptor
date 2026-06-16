"""Configuration management for the SkillEvolve framework."""

from __future__ import annotations
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional
from core.embedding_config import PRIMARY_EMBEDDING_MODEL

@dataclass
class SkillEvolveConfig:
    api_key: str = ''
    base_url: str = ''
    model: str = ''
    max_tokens: int = 512
    temperature: float = 0.3
    max_retries: int = 5
    retry_delay: float = 1.0
    embedding_api_key: str = ''
    embedding_base_url: str = ''
    embedding_model: str = PRIMARY_EMBEDDING_MODEL
    max_iterations: int = 10
    k_reject_threshold: int = 5
    localization_confidence_threshold: float = 0.6
    attribution_weight_threshold: float = 0.55
    duplication_similarity_threshold: float = 0.95
    skill_match_threshold: float = 0.5
    cross_task_match_threshold: float = 0.55
    success_delta_threshold: float = 0.005
    avg_score_delta_threshold: float = 0.005
    regression_threshold: float = -0.05
    min_sample_size: int = 5
    use_llm_localization: bool = True
    use_llm_attribution: bool = True
    use_llm_revision: bool = True
    use_llm_generation: bool = True
    skill_template: str = 'enhanced'
    output_dir: Path = field(default_factory=lambda: Path('./SkillEvolve_output'))
    artifact_dir: Path = field(default_factory=lambda: Path('./SkillEvolve_artifacts'))
    results_dir: Path = field(default_factory=lambda: Path('./SkillEvolve_results'))
    skills_workspace_dir: Optional[Path] = None
    program_workspace: Optional[Path] = None
    agent_harness: str = 'openclaw'
    program_git_branches: bool = False
    direct_skill_write: bool = True

    def __post_init__(self):
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir)
        if isinstance(self.artifact_dir, str):
            self.artifact_dir = Path(self.artifact_dir)
        if isinstance(self.results_dir, str):
            self.results_dir = Path(self.results_dir)
        if self.skills_workspace_dir is not None and isinstance(self.skills_workspace_dir, str):
            self.skills_workspace_dir = Path(self.skills_workspace_dir)
        if self.program_workspace is not None and isinstance(self.program_workspace, str):
            self.program_workspace = Path(self.program_workspace)

    @classmethod
    def from_env(cls, prefix: str='SkillEvolve_') -> SkillEvolveConfig:

        def get_env(key: str, default: Any=None) -> Any:
            return os.environ.get(f'{prefix}{key}', default)

        def get_env_int(key: str, default: int) -> int:
            val = get_env(key)
            return int(val) if val is not None else default

        def get_env_float(key: str, default: float) -> float:
            val = get_env(key)
            return float(val) if val is not None else default

        def get_env_bool(key: str, default: bool) -> bool:
            val = get_env(key)
            if val is None:
                return default
            return val.lower() in ('true', '1', 'yes', 'on')
        return cls(api_key=get_env('API_KEY', ''), base_url=get_env('BASE_URL', ''), model=get_env('MODEL', ''), max_tokens=get_env_int('MAX_TOKENS', 512), temperature=get_env_float('TEMPERATURE', 0.3), max_retries=get_env_int('MAX_RETRIES', 5), retry_delay=get_env_float('RETRY_DELAY', 1.0), max_iterations=get_env_int('MAX_ITERATIONS', 10), k_reject_threshold=get_env_int('K_REJECT_THRESHOLD', 5), localization_confidence_threshold=get_env_float('LOCALIZATION_CONFIDENCE_THRESHOLD', 0.6), attribution_weight_threshold=get_env_float('ATTRIBUTION_WEIGHT_THRESHOLD', 0.55), duplication_similarity_threshold=get_env_float('DUPLICATION_SIMILARITY_THRESHOLD', 0.95), skill_match_threshold=get_env_float('SKILL_MATCH_THRESHOLD', 0.5), cross_task_match_threshold=get_env_float('CROSS_TASK_MATCH_THRESHOLD', 0.55), success_delta_threshold=get_env_float('SUCCESS_DELTA_THRESHOLD', 0.005), avg_score_delta_threshold=get_env_float('AVG_SCORE_DELTA_THRESHOLD', 0.005), regression_threshold=get_env_float('REGRESSION_THRESHOLD', -0.05), min_sample_size=get_env_int('MIN_SAMPLE_SIZE', 5), use_llm_localization=get_env_bool('USE_LLM_LOCALIZATION', True), use_llm_attribution=get_env_bool('USE_LLM_ATTRIBUTION', True), use_llm_revision=get_env_bool('USE_LLM_REVISION', True), use_llm_generation=get_env_bool('USE_LLM_GENERATION', True), skill_template=get_env('SKILL_TEMPLATE', 'enhanced'), output_dir=Path(get_env('OUTPUT_DIR', './SkillEvolve_output')), artifact_dir=Path(get_env('ARTIFACT_DIR', './SkillEvolve_artifacts')), results_dir=Path(get_env('RESULTS_DIR', './SkillEvolve_results')), skills_workspace_dir=Path(p) if (p := get_env('SKILLS_WORKSPACE_DIR')) else None, program_workspace=Path(p) if (p := get_env('PROGRAM_WORKSPACE')) else None, agent_harness=get_env('HARNESS', get_env('AGENT_HARNESS', 'openclaw')), program_git_branches=get_env_bool('PROGRAM_GIT', False), direct_skill_write=get_env_bool('DIRECT_SKILL_WRITE', True), embedding_api_key=get_env('EMBEDDING_API_KEY', ''), embedding_base_url=get_env('EMBEDDING_BASE_URL', ''), embedding_model=get_env('EMBEDDING_MODEL', PRIMARY_EMBEDDING_MODEL))

    @classmethod
    def from_json(cls, path: str | Path) -> SkillEvolveConfig:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for key in ['output_dir', 'artifact_dir', 'results_dir', 'skills_workspace_dir', 'program_workspace']:
            if key in data and isinstance(data[key], str):
                data[key] = Path(data[key])
        return cls(**data)

    def to_json(self, path: str | Path) -> None:
        data = {'api_key': 'your-api-key-here', 'embedding_api_key': 'your-embedding-api-key-here', 'base_url': self.base_url, 'model': self.model, 'max_tokens': self.max_tokens, 'temperature': self.temperature, 'max_retries': self.max_retries, 'retry_delay': self.retry_delay, 'max_iterations': self.max_iterations, 'k_reject_threshold': self.k_reject_threshold, 'localization_confidence_threshold': self.localization_confidence_threshold, 'attribution_weight_threshold': self.attribution_weight_threshold, 'duplication_similarity_threshold': self.duplication_similarity_threshold, 'success_delta_threshold': self.success_delta_threshold, 'avg_score_delta_threshold': self.avg_score_delta_threshold, 'regression_threshold': self.regression_threshold, 'min_sample_size': self.min_sample_size, 'use_llm_localization': self.use_llm_localization, 'use_llm_attribution': self.use_llm_attribution, 'use_llm_revision': self.use_llm_revision, 'use_llm_generation': self.use_llm_generation, 'skill_template': self.skill_template, 'output_dir': str(self.output_dir), 'artifact_dir': str(self.artifact_dir), 'results_dir': str(self.results_dir)}
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def validate(self) -> list[str]:
        issues = []
        if not self.api_key:
            issues.append('API key is required')
        if not self.model:
            issues.append('Model name is required')
        if self.max_iterations < 1:
            issues.append('max_iterations must be at least 1')
        if self.k_reject_threshold < 1:
            issues.append('k_reject_threshold must be at least 1')
        if not 0 <= self.temperature <= 2:
            issues.append('temperature must be between 0 and 2')
        if self.max_tokens < 1:
            issues.append('max_tokens must be positive')
        if self.skill_template not in {'standard', 'enhanced', 'concise'}:
            issues.append('skill_template must be one of standard/enhanced/concise')
        return issues

    def is_valid(self) -> bool:
        return len(self.validate()) == 0

    def create_directories(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)

def load_config(env_prefix: str='SkillEvolve_', config_path: Optional[str | Path]=None, use_env: bool=True) -> SkillEvolveConfig:
    config = SkillEvolveConfig()
    if config_path and Path(config_path).exists():
        file_config = SkillEvolveConfig.from_json(config_path)
        for field_name in SkillEvolveConfig.__dataclass_fields__:
            setattr(config, field_name, getattr(file_config, field_name))
    if use_env:
        env_config = SkillEvolveConfig.from_env(env_prefix)
        for field_name in SkillEvolveConfig.__dataclass_fields__:
            env_val = getattr(env_config, field_name)
            if env_val != getattr(SkillEvolveConfig(), field_name):
                setattr(config, field_name, env_val)
    if isinstance(config.output_dir, str):
        config.output_dir = Path(config.output_dir)
    if isinstance(config.artifact_dir, str):
        config.artifact_dir = Path(config.artifact_dir)
    if isinstance(config.results_dir, str):
        config.results_dir = Path(config.results_dir)
    return config

def get_llm_config_for_provider(provider: str) -> Dict[str, str]:
    providers = {'kimi': {'base_url': '', 'model': 'kimi-k2.5'}, 'glm': {'base_url': '', 'model': 'glm-5'}, 'gpt': {'base_url': '', 'model': 'gpt-4o'}, 'openai': {'base_url': '', 'model': 'gpt-4o'}, 'local': {'base_url': 'http://localhost:8000/v1', 'model': ''}}
    return providers.get(provider.lower(), {})
