"""LLM rerank of embedding-retrieved skill candidates (paper Eq. 4 / Appendix C.1).

Pipeline:
  1. Embedding cosine retrieve (threshold + top-10) — SemanticSkillMatcher
  2. Backbone LLM rerank conditioned on task description — this module
  3. Inject top-k

No rule fallback: if the LLM call fails or returns unusable JSON, raise.
Disable only via SkillAdaptor_LLM_RERANK=0 (explicit opt-out).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from .llm_json import parse_llm_json_object
from .llm_params import chat_temperature
from .types import Skill


def llm_rerank_enabled() -> bool:
    raw = os.environ.get('SkillAdaptor_LLM_RERANK', '1').strip().lower()
    return raw not in ('0', 'false', 'no', 'off')


def rerank_skills_with_llm(
    *,
    llm_client: Any,
    model_name: str,
    task_description: str,
    candidates: List[Tuple[Skill, float]],
    top_k: int = 3,
) -> List[Tuple[Skill, float]]:
    """Rerank embedding candidates with the backbone LLM.

    Returns up to ``top_k`` (skill, embed_score) in LLM preference order.
    Preserves original embedding scores; order is LLM-decided.
    """
    if not candidates:
        return []
    if llm_client is None:
        raise RuntimeError('LLM client required for skill rerank (paper S_q).')
    if not model_name:
        raise RuntimeError('model_name required for skill rerank.')

    # Cap prompt size; paper uses top-10 after cosine filter.
    pool = candidates[:10]
    by_id: Dict[str, Tuple[Skill, float]] = {s.id: (s, score) for s, score in pool}
    lines = []
    for i, (skill, score) in enumerate(pool, start=1):
        desc = (skill.description or skill.when_to_apply or '')[:180]
        lines.append(
            f'{i}. id={skill.id}\n'
            f'   title={skill.title}\n'
            f'   embed_cosine={score:.4f}\n'
            f'   when/desc={desc}'
        )
    prompt = (
        '# Skill rerank for agent injection\n\n'
        'You rank which skills are most useful to inject for the task below.\n'
        'Use only the candidate ids listed. Prefer skills that change verifier-visible '
        'behavior for THIS task; demote unrelated skills.\n\n'
        f'## Task\n{task_description[:1200]}\n\n'
        '## Candidates (already filtered by embedding)\n'
        + '\n'.join(lines)
        + '\n\n## Output JSON only\n'
        '{\n'
        '  "ranked_ids": ["id_best", "id_second", ...],\n'
        '  "reason": "one short sentence"\n'
        '}\n'
        f'Return at most {max(top_k, len(pool))} ids, best first. '
        'Every id MUST appear in the candidate list.\n'
    )
    response = llm_client.chat.completions.create(
        model=model_name,
        messages=[{'role': 'user', 'content': prompt}],
        temperature=chat_temperature(model_name, 0.0),
    )
    content = response.choices[0].message.content or ''
    parsed = parse_llm_json_object(content, context='skill LLM rerank')
    if not isinstance(parsed, dict):
        raise ValueError(f'LLM rerank expected JSON object, got {type(parsed).__name__}')
    ranked_ids = parsed.get('ranked_ids')
    if not isinstance(ranked_ids, list) or not ranked_ids:
        raise ValueError('LLM rerank returned empty ranked_ids')

    out: List[Tuple[Skill, float]] = []
    seen: set[str] = set()
    for sid in ranked_ids:
        if not isinstance(sid, str):
            continue
        sid = sid.strip()
        if sid not in by_id or sid in seen:
            continue
        out.append(by_id[sid])
        seen.add(sid)
        if len(out) >= top_k:
            break
    if not out:
        raise ValueError(
            f'LLM rerank ids {[str(x) for x in ranked_ids][:8]} matched none of '
            f'candidates {list(by_id)}'
        )
    return out
