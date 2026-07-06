from __future__ import annotations

import os
from typing import List, Optional

from core.types import Step


def allow_synthetic_trajectory() -> bool:
    return os.environ.get('ALLOW_SYNTHETIC_TRAJECTORY', '').strip().lower() in ('1', 'true', 'yes')


def maybe_synthesize_minimal(
    *,
    task_id: str,
    task_description: str,
    score: float,
    skills_used: List[str],
    step_source: str,
    action: str = '(assistant response)',
) -> Optional[List[Step]]:
    if not allow_synthetic_trajectory():
        return None
    return [
        Step(
            index=0,
            observation=(task_description or task_id)[:500],
            action=action,
            reward=float(score),
            done=True,
            skills_used=list(skills_used),
            metadata={'step_provenance': 'synthetic_minimal', 'step_source': step_source},
        )
    ]
