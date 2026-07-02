"""
Optional SkillNet (skillnet-ai) integration — evaluate/analyze after adopt.

Disabled by default. Set SKILLNET_ENABLED=1 to activate.
Requires: pip install skillnet-ai
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _truthy(name: str, default: str = '0') -> bool:
    return os.environ.get(name, default).strip().lower() in ('1', 'true', 'yes')


def enabled() -> bool:
    return _truthy('SKILLNET_ENABLED')


def is_available() -> bool:
    if not enabled():
        return False
    try:
        import skillnet_ai  # noqa: F401
        return True
    except ImportError:
        return False


def _api_key() -> str:
    return (os.environ.get('API_KEY') or os.environ.get('SkillEvolve_API_KEY') or '').strip()


def _needs_api() -> bool:
    return _truthy('SKILLNET_POST_EVAL') or _truthy('SKILLNET_POST_ANALYZE')


def _client():
    from skillnet_ai import SkillNetClient
    return SkillNetClient(
        api_key=_api_key(),
        base_url=os.environ.get('BASE_URL') or os.environ.get('SkillEvolve_BASE_URL'),
        github_token=os.environ.get('GITHUB_TOKEN'),
    )


def _serialize_eval_result(result: Any) -> Any:
    if result is None:
        return None
    if isinstance(result, dict):
        return result
    for attr in ('model_dump', 'dict', 'to_dict'):
        fn = getattr(result, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                pass
    if hasattr(result, '__dict__'):
        return {k: v for k, v in vars(result).items() if not k.startswith('_')}
    return str(result)


def _write_skillnet_report(workspace: Path, summary: dict[str, Any]) -> Path | None:
    if not summary.get('evaluated') and summary.get('analyze') is None:
        return None
    out_dir = workspace / '.skill-adaptor' / 'skillnet'
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / 'post_adopt_report.json'
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    return path


def post_adopt_hooks(workspace: Path, adopted_ids: list[str]) -> dict[str, Any]:
    """Optional skillnet evaluate/analyze after SkillAdaptor export. Never raises."""
    summary: dict[str, Any] = {'enabled': enabled(), 'evaluated': [], 'analyze': None}
    if not enabled():
        return summary
    if not adopted_ids:
        return summary
    if _needs_api() and not _api_key():
        summary['error'] = 'API_KEY or SkillEvolve_API_KEY required for SKILLNET_POST_EVAL / SKILLNET_POST_ANALYZE'
        return summary
    if not is_available():
        summary['error'] = 'skillnet-ai not installed (pip install skillnet-ai)'
        return summary
    if not _truthy('SKILLNET_POST_EVAL') and not _truthy('SKILLNET_POST_ANALYZE'):
        summary['note'] = 'SKILLNET_ENABLED=1 but no SKILLNET_POST_EVAL or SKILLNET_POST_ANALYZE; no-op'
        return summary
    skills_root = workspace / 'skills'
    try:
        client = _client()
        if _truthy('SKILLNET_POST_EVAL'):
            for sid in adopted_ids:
                target = skills_root / sid
                if not target.is_dir():
                    continue
                raw = client.evaluate(target=str(target))
                summary['evaluated'].append({'skill_id': sid, 'result': _serialize_eval_result(raw)})
        if _truthy('SKILLNET_POST_ANALYZE') and skills_root.is_dir():
            raw = client.analyze(skills_dir=str(skills_root))
            summary['analyze'] = _serialize_eval_result(raw)
        report = _write_skillnet_report(workspace, summary)
        if report:
            summary['report_path'] = str(report)
    except Exception as exc:
        summary['error'] = str(exc)
    return summary
