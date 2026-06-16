"""Strict JSON extraction from LLM outputs — no silent parse fallback."""

from __future__ import annotations

import json
import re
from typing import Any, Dict


class LLMJSONParseError(ValueError):
    pass


def parse_llm_json_object(content: str, *, context: str = "LLM response") -> Dict[str, Any]:
    if not content or not content.strip():
        raise LLMJSONParseError(f"{context}: empty content")
    candidates: list[str] = []
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1).strip())
    candidates.append(content.strip())
    start = content.find("{")
    end = content.rfind("}")
    if start >= 0 and end > start:
        candidates.append(content[start : end + 1])
    for match in re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", content, re.DOTALL):
        candidates.append(match.group(0))
    seen: set[str] = set()
    errors: list[str] = []
    for cand in candidates:
        if cand in seen:
            continue
        seen.add(cand)
        try:
            data = json.loads(cand)
        except json.JSONDecodeError as exc:
            errors.append(str(exc))
            continue
        if isinstance(data, dict):
            return data
        errors.append(f"expected object, got {type(data).__name__}")
    preview = content[:300].replace("\n", " ")
    raise LLMJSONParseError(
        f"{context}: failed to parse JSON object. Preview: {preview!r}. Errors: {errors[:3]}"
    )
