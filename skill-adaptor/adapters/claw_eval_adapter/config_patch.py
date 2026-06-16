"""Claw-Eval Config Patch"""

from core.config import SkillEvolveConfig
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

@dataclass
class ClawEvalConfig(SkillEvolveConfig):
    success_delta_threshold: float = 0.01
    avg_score_delta_threshold: float = 0.01
    k_reject_threshold: int = 3
    output_dir: Path = field(default_factory=lambda: Path('./claw_eval_output'))
    results_dir: Path = field(default_factory=lambda: Path('./claw_eval_results'))

    @classmethod
    def from_base(cls, base_config: SkillEvolveConfig) -> 'ClawEvalConfig':
        import copy
        config_dict = {field.name: getattr(base_config, field.name) for field in base_config.__dataclass_fields__.values()}
        config_dict['success_delta_threshold'] = 0.01
        config_dict['avg_score_delta_threshold'] = 0.01
        config_dict['k_reject_threshold'] = 3
        return cls(**config_dict)

    def to_summary(self) -> dict:
        return {'success_delta_threshold': self.success_delta_threshold, 'avg_score_delta_threshold': self.avg_score_delta_threshold, 'k_reject_threshold': self.k_reject_threshold, 'output_dir': str(self.output_dir), 'note': 'Claw-eval optimized settings'}
