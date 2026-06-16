"""Tests for strict LLM JSON parsing."""

from __future__ import annotations
import pytest
from core.llm_json import LLMJSONParseError, parse_llm_json_object

def test_parse_llm_json_object_success() -> None:
    data = parse_llm_json_object('```json\n{"a": 1}\n```')
    assert data == {'a': 1}

def test_parse_llm_json_object_raises_on_invalid() -> None:
    with pytest.raises(LLMJSONParseError, match='failed to parse JSON'):
        parse_llm_json_object('not json at all')
