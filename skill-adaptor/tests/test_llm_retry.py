"""LLM retry helper — fail after N attempts."""

from __future__ import annotations
import pytest
from core.llm_retry import call_with_retries

def test_call_with_retries_raises_after_exhaustion():
    calls = {'n': 0}

    def fail():
        calls['n'] += 1
        raise ValueError('boom')
    with pytest.raises(RuntimeError, match='after 3 attempts'):
        call_with_retries(fail, max_retries=3, context='test')
    assert calls['n'] == 3

def test_call_with_retries_succeeds_on_second_try():
    calls = {'n': 0}

    def flaky():
        calls['n'] += 1
        if calls['n'] < 2:
            raise ValueError('transient')
        return 'ok'
    assert call_with_retries(flaky, max_retries=5) == 'ok'
    assert calls['n'] == 2
