"""Append-only evolution audit log (adopt/reject causal record)."""

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

def audit_path(output_dir: Path) -> Path:
    return Path(output_dir) / 'evolution_audit.jsonl'

def append_audit_record(output_dir: Path, record: Dict[str, Any]) -> None:
    path = audit_path(output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    record.setdefault('ts', datetime.now(timezone.utc).isoformat())
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')

def build_validation_audit(*, skill_id: str, created_from: Optional[str], adopted: bool, adopt_result: Any, scoped_result: Optional[Any]=None, category_result: Optional[Any]=None, detail: str='') -> Dict[str, Any]:

    def _snap(r: Any) -> Optional[Dict[str, Any]]:
        if r is None:
            return None
        return {'delta_success': getattr(r, 'delta_success', None), 'delta_avg_score': getattr(r, 'delta_avg_score', None), 'regression': getattr(r, 'regression_detected', None), 'sample_size': getattr(r, 'sample_size', None)}
    frozen = None
    if adopt_result and getattr(adopt_result, 'revised_metrics', None):
        frozen = (adopt_result.revised_metrics or {}).get('retrieval_frozen_tasks')
    return {'skill_id': skill_id, 'created_from': created_from, 'decision': 'ADOPTED' if adopted else 'REJECTED', 'detail': detail, 'full_q': _snap(adopt_result), 'source': _snap(scoped_result), 'category': _snap(category_result), 'retrieval_frozen_tasks': frozen}
