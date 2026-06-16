"""Pytest defaults — unit tests must not sleep through LLM/embedding retry backoff."""

from __future__ import annotations

import os
import time

os.environ.setdefault('SkillEvolve_MAX_RETRIES', '1')

def _no_sleep(_seconds: float) -> None:
    return None

time.sleep = _no_sleep
