"""Claw-Eval judge resolution — **submitted path is always the official judge**.

Official (claw-eval ``config_general.yaml``):

  model_id: google/gemini-3-flash-preview
  base_url:  https://openrouter.ai/api/v1   # or any OpenAI-compatible endpoint
  api_key:   CLAW_EVAL_JUDGE_API_KEY / OPENROUTER_API_KEY

Same interface for any endpoint that serves the official model id:
  CLAW_EVAL_JUDGE_API_KEY + CLAW_EVAL_JUDGE_BASE_URL (+ optional CLAW_EVAL_JUDGE_MODEL
  only when CLAW_EVAL_ALLOW_NONOFFICIAL_JUDGE=1 for local wiring).

Local testing when Gemini is unreachable: use
  ``adapters.claw_eval_adapter.wiring_judge`` / ``scripts/claw_eval_wiring_judge.py``
  — never bake fallback into the production executor path.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Locked to claw-eval config_general.yaml — do not change for paper runs.
OFFICIAL_JUDGE_MODEL = 'google/gemini-3-flash-preview'
OFFICIAL_JUDGE_BASE_URL = 'https://openrouter.ai/api/v1'


def _first_env(*names: str) -> Optional[str]:
    for name in names:
        val = os.environ.get(name, '').strip()
        if val:
            return val
    return None


def allow_nonofficial_judge() -> bool:
    return os.environ.get('CLAW_EVAL_ALLOW_NONOFFICIAL_JUDGE', '').strip().lower() in (
        '1',
        'true',
        'yes',
    )


def resolve_official_judge(
    *,
    agent_api_key: Optional[str] = None,
    agent_base_url: Optional[str] = None,
) -> Tuple[Dict[str, Any], list[str]]:
    """Return judge config for runs. Model id is official unless wiring allow-flag is set.

    Credential priority (URL + key — same interface everywhere):
      1. CLAW_EVAL_JUDGE_API_KEY + CLAW_EVAL_JUDGE_BASE_URL
      2. OPENROUTER_API_KEY → base defaults to OpenRouter
      3. Agent chat key/url as last-resort *credentials only* (model id stays official)
    """
    warnings: list[str] = []
    model_id = OFFICIAL_JUDGE_MODEL
    override = _first_env('CLAW_EVAL_JUDGE_MODEL')
    if override and override != OFFICIAL_JUDGE_MODEL:
        if allow_nonofficial_judge():
            model_id = override
            warnings.append(
                f'NON-OFFICIAL judge model_id={model_id} '
                f'(CLAW_EVAL_ALLOW_NONOFFICIAL_JUDGE=1) — NOT paper-comparable'
            )
        else:
            warnings.append(
                f'Ignoring CLAW_EVAL_JUDGE_MODEL={override}; '
                f'production uses {OFFICIAL_JUDGE_MODEL}. '
                'Local wiring only: set CLAW_EVAL_ALLOW_NONOFFICIAL_JUDGE=1 '
                'via scripts/claw_eval_wiring_judge.py'
            )

    api_key = _first_env('CLAW_EVAL_JUDGE_API_KEY', 'OPENROUTER_API_KEY')
    base_url = _first_env('CLAW_EVAL_JUDGE_BASE_URL')

    if api_key and not base_url:
        if _first_env('OPENROUTER_API_KEY') and not _first_env('CLAW_EVAL_JUDGE_API_KEY'):
            base_url = OFFICIAL_JUDGE_BASE_URL
        elif api_key == (agent_api_key or '').strip():
            base_url = (agent_base_url or '').strip() or OFFICIAL_JUDGE_BASE_URL
        else:
            base_url = OFFICIAL_JUDGE_BASE_URL

    if not api_key:
        api_key = (agent_api_key or '').strip() or None
        base_url = (agent_base_url or '').strip() or OFFICIAL_JUDGE_BASE_URL
        if api_key:
            warnings.append(
                'Judge credentials fell back to agent chat API key/url; '
                f'model_id={model_id} (still official unless wiring allow-flag)'
            )

    if not api_key:
        warnings.append(
            'No judge API key: set CLAW_EVAL_JUDGE_API_KEY (+ CLAW_EVAL_JUDGE_BASE_URL) '
            'or OPENROUTER_API_KEY for official google/gemini-3-flash-preview'
        )

    return (
        {
            'api_key': api_key or '',
            'base_url': (base_url or OFFICIAL_JUDGE_BASE_URL).rstrip('/'),
            'model_id': model_id,
            'enabled': True,
        },
        warnings,
    )


def load_base_config_dict(claw_eval_path: Path) -> Dict[str, Any]:
    """Load official YAML if present (config_general.yaml preferred)."""
    candidates = [
        claw_eval_path / 'config_general.yaml',
        claw_eval_path / 'config.yaml',
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            import yaml  # type: ignore

            raw = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
            if isinstance(raw, dict):
                raw['_source'] = str(path)
                return raw
        except Exception:
            continue
    return {'_source': 'defaults'}


def build_run_config_payload(
    *,
    claw_eval_path: Path,
    agent_api_key: Optional[str],
    agent_base_url: Optional[str],
    agent_model: Optional[str],
    skill_text: str = '',
    skill_rel_path: str = 'skills/skill-adaptor-evolved/SKILL.md',
    system_prompt_prefix: str = '',
    judge_enabled: bool = True,
) -> Tuple[Dict[str, Any], list[str]]:
    """Merge official base + agent overrides + skill injection + official judge."""
    base = load_base_config_dict(claw_eval_path)
    warnings: list[str] = []
    source = base.pop('_source', 'defaults')
    warnings.append(f'config base: {source}')

    judge, judge_warnings = resolve_official_judge(
        agent_api_key=agent_api_key,
        agent_base_url=agent_base_url,
    )
    warnings.extend(judge_warnings)
    judge['enabled'] = bool(judge_enabled)

    # If base YAML has a different official-era judge id, prefer our constant
    # unless wiring override is active.
    if isinstance(base.get('judge'), dict) and not allow_nonofficial_judge():
        base_judge_model = (base['judge'].get('model_id') or '').strip()
        if base_judge_model and base_judge_model != OFFICIAL_JUDGE_MODEL:
            warnings.append(
                f'config_general judge.model_id={base_judge_model} noted; '
                f'SkillAdaptor locks submitted runs to {OFFICIAL_JUDGE_MODEL}'
            )

    prompt_block: Dict[str, Any] = {
        'enabled': True,
        'skills': {
            'default': (
                [
                    {
                        'name': 'skill-adaptor-evolved',
                        'description': 'SkillAdaptor evolved skill for this task',
                        'path': skill_rel_path,
                    }
                ]
                if skill_text.strip()
                else []
            ),
            'load_via_tool_call': False,
            'read_tool_name': 'read',
        },
    }
    if isinstance(base.get('prompt'), dict):
        for key, val in base['prompt'].items():
            if key not in prompt_block:
                prompt_block[key] = val

    model_block: Dict[str, Any] = {
        'api_key': agent_api_key or '',
        'base_url': agent_base_url or '',
        'model_id': agent_model or 'gpt-4.1',
        'temperature': 0.0,
    }
    if isinstance(base.get('model'), dict):
        for key in ('context_window', 'extra_body', 'reasoning_effort'):
            if key in base['model'] and key not in model_block:
                model_block[key] = base['model'][key]
    if system_prompt_prefix.strip():
        model_block['system_prompt_prefix'] = system_prompt_prefix.strip()

    defaults = {'trace_dir': 'traces', 'tasks_dir': 'tasks'}
    if isinstance(base.get('defaults'), dict):
        defaults = {**defaults, **base['defaults']}

    payload: Dict[str, Any] = {
        'model': model_block,
        'judge': judge,
        'defaults': defaults,
        'prompt': prompt_block,
    }
    for key in ('sandbox', 'media', 'user_agent_model'):
        if key in base:
            payload[key] = base[key]
    return payload, warnings


def write_run_config_yaml(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import yaml  # type: ignore

        path.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
            encoding='utf-8',
        )
    except Exception:
        judge = payload.get('judge') or {}
        model = payload.get('model') or {}
        path.write_text(
            'model:\n'
            f'  api_key: "{model.get("api_key", "")}"\n'
            f'  base_url: "{model.get("base_url", "")}"\n'
            f'  model_id: "{model.get("model_id", "gpt-4.1")}"\n'
            'judge:\n'
            f'  api_key: "{judge.get("api_key", "")}"\n'
            f'  base_url: "{judge.get("base_url", "")}"\n'
            f'  model_id: "{judge.get("model_id", OFFICIAL_JUDGE_MODEL)}"\n'
            f'  enabled: {str(bool(judge.get("enabled", True))).lower()}\n',
            encoding='utf-8',
        )


def probe_judge_reachable(judge: Dict[str, Any], *, timeout_s: float = 45.0) -> Tuple[bool, str]:
    """Cheap chat completion against the configured judge endpoint."""
    api_key = (judge.get('api_key') or '').strip()
    base_url = (judge.get('base_url') or '').rstrip('/')
    model_id = (judge.get('model_id') or OFFICIAL_JUDGE_MODEL).strip()
    if not api_key:
        return False, 'missing judge api_key'
    if not base_url:
        return False, 'missing judge base_url'
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout_s)
        resp = client.chat.completions.create(
            model=model_id,
            messages=[{'role': 'user', 'content': 'Reply with exactly: OK'}],
            max_tokens=8,
            temperature=0,
        )
        text = (resp.choices[0].message.content or '').strip()
        return True, f'ok model={model_id} reply={text[:40]!r}'
    except Exception as exc:
        return False, f'{type(exc).__name__}: {exc}'
