"""Shared LLM call retry — fail after N attempts, no silent fallback."""

from __future__ import annotations
import time
from typing import Callable, TypeVar
T = TypeVar('T')

def call_with_retries(fn: Callable[[], T], *, max_retries: int=5, context: str='LLM') -> T:
    if max_retries < 1:
        raise ValueError('max_retries must be >= 1')
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as exc:
            last_err = exc
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            break
    raise RuntimeError(f'{context} failed after {max_retries} attempts: {last_err}') from last_err
